"""Terminal engine: framebuffer, ANSI encoder, braille canvas, audio analysis and audio clock."""
import json
import math
import os
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata

import numpy as np

BPM = 240.0
BEAT = 60.0 / BPM
BEAT0 = 0.08          # first detected beat (s)
BAR0 = 0.33           # first detected downbeat (s)
SONG_END = 290.13

BLACK = (0, 0, 0)
TEAL = (57, 197, 187)
TEAL_D = (16, 74, 70)
TEAL_B = (150, 255, 238)
WHITE = (228, 238, 238)
GRAY = (86, 98, 102)
DIM = (38, 46, 50)
RED = (255, 38, 72)
RED_D = (104, 12, 28)
PINK = (255, 92, 170)
AMBER = (255, 176, 48)


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def mix(c1, c2, t):
    t = clamp(t)
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def scale(c, k):
    return (min(255, max(0, int(c[0] * k))),
            min(255, max(0, int(c[1] * k))),
            min(255, max(0, int(c[2] * k))))


def h01(a, b=0, c=0):
    """Deterministic hash of up to three ints -> [0, 1)."""
    x = (int(a) * 374761393 + int(b) * 668265263 + int(c) * 2246822519 + 0x9E3779B9) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
    x ^= x >> 16
    return (x & 0xFFFFFF) / 16777216.0


def h01v(a, b=0, c=0):
    a = np.asarray(a, np.uint64)
    x = (a * np.uint64(374761393) + np.uint64(int(b) & 0xFFFFFFFF) * np.uint64(668265263)
         + np.uint64(int(c) & 0xFFFFFFFF) * np.uint64(2246822519) + np.uint64(0x9E3779B9)) & np.uint64(0xFFFFFFFF)
    x = ((x ^ (x >> np.uint64(13))) * np.uint64(1274126177)) & np.uint64(0xFFFFFFFF)
    x ^= x >> np.uint64(16)
    return (x & np.uint64(0xFFFFFF)).astype(np.float64) / 16777216.0


_WIDE = {}


def is_wide(c):
    if c < '\u1100':
        return False
    w = _WIDE.get(c)
    if w is None:
        w = unicodedata.east_asian_width(c) in ('W', 'F')
        _WIDE[c] = w
    return w


def str_width(s):
    return sum(2 if is_wide(c) else 1 for c in s)


def all_narrow(s):
    return all(not is_wide(c) for c in s)


def palette(entries, base=BLACK):
    """Build a 256-entry color lookup from {index: color} or {(lo, hi): (c_lo, c_hi)} gradients."""
    p = np.zeros((256, 3), np.uint8)
    p[:] = base
    for k, v in entries.items():
        if isinstance(k, tuple):
            lo, hi = k
            c0, c1 = v
            for i in range(lo, hi + 1):
                p[i] = mix(c0, c1, (i - lo) / max(1, hi - lo))
        else:
            p[k] = v
    return p


class Frame:
    """Character grid with per-cell fg/bg colors. Wide glyphs occupy two cells; the second holds ''."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.ch = np.full((h, w), ' ', dtype='<U1')
        self.fg = np.zeros((h, w, 3), np.uint8)
        self.bg = np.zeros((h, w, 3), np.uint8)

    def clear(self, bg=BLACK):
        self.ch.fill(' ')
        self.fg.fill(0)
        self.bg[:] = bg

    def put(self, x, y, s, fg=WHITE, bg=None):
        y = int(y)
        x = int(x)
        if y < 0 or y >= self.h or not s:
            return x + str_width(s)
        if s.isascii() or all_narrow(s):
            n = len(s)
            a, b = max(0, x), min(self.w, x + n)
            if a < b:
                if a > 0 and self.ch[y, a] == '':
                    self.ch[y, a - 1] = ' '
                self.ch[y, a:b] = list(s[a - x:b - x])
                self.fg[y, a:b] = fg
                if bg is not None:
                    self.bg[y, a:b] = bg
            return x + n
        for c in s:
            wd = 2 if is_wide(c) else 1
            if x >= self.w:
                break
            if x >= 0 and x + wd <= self.w:
                if x > 0 and self.ch[y, x] == '':
                    self.ch[y, x - 1] = ' '
                self.ch[y, x] = c
                self.fg[y, x] = fg
                if bg is not None:
                    self.bg[y, x] = bg
                if wd == 2:
                    self.ch[y, x + 1] = ''
                    self.fg[y, x + 1] = fg
                    if bg is not None:
                        self.bg[y, x + 1] = bg
            x += wd
        return x

    def put_center(self, y, s, fg=WHITE, bg=None, cx=None):
        cx = self.w // 2 if cx is None else cx
        return self.put(cx - str_width(s) // 2, y, s, fg, bg)

    def fill(self, x, y, w, h, c=' ', fg=WHITE, bg=None):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(self.w, int(x + w)), min(self.h, int(y + h))
        if x0 >= x1 or y0 >= y1:
            return
        self.ch[y0:y1, x0:x1] = c
        self.fg[y0:y1, x0:x1] = fg
        if bg is not None:
            self.bg[y0:y1, x0:x1] = bg

    def dim(self, k):
        np.multiply(self.fg, k, out=self.fg, casting='unsafe')


BRAILLE = np.array([chr(0x2800 + i) for i in range(256)], dtype='<U1')


class Braille:
    """Sub-cell canvas: 2x4 dots per cell. Each dot stores a layer value; the cell takes the max."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.dw, self.dh = w * 2, h * 4
        self.dots = np.zeros((self.dh, self.dw), np.uint8)

    def clear(self):
        self.dots.fill(0)

    def points(self, xs, ys, v=1):
        xs = np.asarray(xs, np.float64)
        xi = np.rint(xs).astype(np.int64).ravel()
        yi = np.rint(np.asarray(ys, np.float64)).astype(np.int64).ravel()
        m = (xi >= 0) & (xi < self.dw) & (yi >= 0) & (yi < self.dh)
        if not m.any():
            return
        if np.ndim(v):
            vv = np.broadcast_to(np.asarray(v, np.uint8), xs.shape).ravel()[m]
        else:
            vv = np.uint8(v)
        xi, yi = xi[m], yi[m]
        self.dots[yi, xi] = np.maximum(self.dots[yi, xi], vv)

    def lines(self, x0, y0, x1, y1, v=1):
        x0, y0, x1, y1 = (np.atleast_1d(np.asarray(a, np.float64)).ravel() for a in (x0, y0, x1, y1))
        if x0.size == 0:
            return
        L = np.maximum(np.abs(x1 - x0), np.abs(y1 - y0))
        n = int(min(np.max(L), 3 * (self.dw + self.dh))) + 2
        t = np.linspace(0.0, 1.0, n)[None, :]
        xs = x0[:, None] + (x1 - x0)[:, None] * t
        ys = y0[:, None] + (y1 - y0)[:, None] * t
        if np.ndim(v):
            v = np.repeat(np.asarray(v, np.uint8).ravel()[:, None], n, 1)
        self.points(xs, ys, v)

    def polyline(self, xs, ys, v=1, closed=False):
        xs = np.asarray(xs, np.float64)
        ys = np.asarray(ys, np.float64)
        if closed:
            self.lines(xs, ys, np.roll(xs, -1), np.roll(ys, -1), v)
        else:
            self.lines(xs[:-1], ys[:-1], xs[1:], ys[1:], v)

    def blit(self, fb, pal, x0=0, y0=0):
        d = self.dots.reshape(self.h, 4, self.w, 2)
        b = (d > 0).astype(np.uint8)
        code = (b[:, 0, :, 0] | (b[:, 1, :, 0] << 1) | (b[:, 2, :, 0] << 2) | (b[:, 0, :, 1] << 3)
                | (b[:, 1, :, 1] << 4) | (b[:, 2, :, 1] << 5) | (b[:, 3, :, 0] << 6) | (b[:, 3, :, 1] << 7))
        vmax = d.max(axis=(1, 3))
        h = min(self.h, fb.h - y0)
        w = min(self.w, fb.w - x0)
        if h <= 0 or w <= 0:
            return
        code = code[:h, :w]
        vmax = vmax[:h, :w]
        nz = code > 0
        fb.ch[y0:y0 + h, x0:x0 + w][nz] = BRAILLE[code[nz]]
        fb.fg[y0:y0 + h, x0:x0 + w][nz] = pal[vmax[nz]]


def _pack(a):
    a = a.astype(np.int64)
    return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]


def _q256(a):
    v = a.astype(np.int64)
    q = np.where(v < 48, 0, np.where(v < 115, 1, (v - 35) // 40))
    return 16 + 36 * q[..., 0] + 6 * q[..., 1] + q[..., 2]


class Encoder:
    def __init__(self, truecolor=True):
        self.tc = truecolor
        self._sgr = {}

    def sgr(self, k):
        s = self._sgr.get(k)
        if s is None:
            f, b = k >> 24, k & 0xFFFFFF
            if self.tc:
                s = f'\x1b[38;2;{f >> 16};{(f >> 8) & 255};{f & 255};48;2;{b >> 16};{(b >> 8) & 255};{b & 255}m'
            else:
                s = f'\x1b[38;5;{f};48;5;{b}m'
            self._sgr[k] = s
        return s

    def encode(self, fb):
        if self.tc:
            fgp, bgp = _pack(fb.fg), _pack(fb.bg)
        else:
            fgp, bgp = _q256(fb.fg), _q256(fb.bg)
        keys = ((fgp << 24) | bgp).tolist()
        bgl = bgp.tolist()
        chs = fb.ch.tolist()
        out = ['\x1b[?2026h']
        ap = out.append
        sgr = self.sgr
        cur = -1
        W = fb.w
        for y in range(fb.h):
            ap(f'\x1b[{y + 1};1H')
            rc, rk, rb = chs[y], keys[y], bgl[y]
            skip = False
            for x in range(W):
                if skip:
                    skip = False
                    continue
                c = rc[x]
                if c == ' ' or c == '':
                    if cur >= 0 and (cur & 0xFFFFFF) == rb[x]:
                        ap(' ')
                        continue
                    cur = rk[x]
                    ap(sgr(cur))
                    ap(' ')
                    continue
                if c >= '\u1100' and is_wide(c):
                    if x == W - 1:
                        c = ' '
                    else:
                        skip = True
                k = rk[x]
                if k != cur:
                    cur = k
                    ap(sgr(k))
                ap(c)
        ap('\x1b[0m\x1b[?2026l')
        return ''.join(out).encode('utf-8')


class Terminal:
    def __init__(self):
        self.out = sys.stdout.buffer
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        self._old = None

    def __enter__(self):
        if self.fd is not None:
            import termios
            import tty
            self._old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        self.write(b'\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[0m\x1b[2J')
        return self

    def __exit__(self, *exc):
        self.write(b'\x1b[0m\x1b[2J\x1b[H\x1b[?7h\x1b[?25h\x1b[?1049l')
        if self._old is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old)

    def write(self, data):
        self.out.write(data)
        self.out.flush()

    def size(self):
        s = shutil.get_terminal_size((100, 32))
        return max(20, s.columns), max(10, s.lines)

    def key(self):
        if self.fd is None:
            return None
        r, _, _ = select.select([self.fd], [], [], 0)
        if r:
            return os.read(self.fd, 16).decode(errors='ignore')
        return None


# ----------------------------------------------------------------------------------------- audio

def decode_audio(path, sr):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.float32).copy()


class Audio:
    """Pre-analysed audio features, sampled at FPS frames per second."""
    FPS = 50
    NB = 48
    SR = 22050

    def __init__(self, path):
        self.ok = False
        self.samples = None
        if path and os.path.exists(path) and shutil.which('ffmpeg'):
            try:
                self.samples = decode_audio(path, self.SR)
                self._analyze(path)
                self.ok = True
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'audio analysis failed: {e}\n')
        if not self.ok:
            self._synthetic()
        self.syl_t = self.syl_s = self.syl_c = np.zeros(0, np.float32)
        vpath = os.path.join(os.path.dirname(path), 'vocal.npz') if path else None
        if vpath and os.path.exists(vpath):
            z = np.load(vpath)
            self.syl_t, self.syl_s, self.syl_c = z['syl_t'], z['syl_s'], z['syl_c']

    def syllables_upto(self, t):
        """Number of syllable onsets at or before t."""
        return int(np.searchsorted(self.syl_t, t, side='right'))

    def _analyze(self, path):
        st = os.stat(path)
        key = f'{st.st_size}-{int(st.st_mtime)}-v2'
        cache = os.path.splitext(path)[0] + '.analysis.npz'
        if os.path.exists(cache):
            try:
                z = np.load(cache)
                if str(z['key']) == key:
                    self.env_, self.bands_ = z['env'], z['bands']
                    return
            except Exception:  # noqa: BLE001
                pass
        x, sr, fps = self.samples, self.SR, self.FPS
        hop, n_fft = sr // fps, 2048
        pad = np.pad(x, (n_fft // 2, n_fft // 2))
        nfr = len(x) // hop
        win = np.hanning(n_fft).astype(np.float32)
        freqs = np.fft.rfftfreq(n_fft, 1 / sr)
        edges = np.geomspace(40, 11000, self.NB + 1)
        M = np.zeros((len(freqs), self.NB), np.float32)
        for i in range(self.NB):
            sel = np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
            if sel.size == 0:
                sel = [int(np.argmin(np.abs(freqs - math.sqrt(edges[i] * edges[i + 1]))))]
            M[sel, i] = 1.0 / len(sel)
        bands = np.empty((nfr, self.NB), np.float32)
        for s in range(0, nfr, 1024):
            e = min(nfr, s + 1024)
            idx = (np.arange(s, e) * hop)[:, None] + np.arange(n_fft)[None, :]
            spec = np.abs(np.fft.rfft(pad[idx] * win, axis=1)).astype(np.float32)
            bands[s:e] = spec @ M
        L = np.log1p(bands * 20.0)
        Bn = np.clip(L / (np.percentile(L, 97, axis=0) + 1e-6), 0, 1.25)
        fc = np.sqrt(edges[:-1] * edges[1:])
        low = Bn[:, fc < 150].mean(1)
        mid = Bn[:, (fc >= 250) & (fc < 3000)].mean(1)
        high = Bn[:, fc >= 5000].mean(1)

        def local(sig, secs):
            k = int(secs * fps)
            m = np.convolve(sig, np.ones(k) / k, 'same')
            return sig / (m * 2.2 + 1e-3)

        flux = np.r_[0, np.maximum(0, np.diff(L, axis=0)).sum(1)]
        lflux = np.r_[0, np.maximum(0, np.diff(L[:, fc < 160], axis=0)).sum(1)]
        env = np.stack([low, mid, high, local(flux, 3.0), local(lflux, 3.0)], 1)
        env = np.clip(env / (np.percentile(env, 98, axis=0) + 1e-6), 0, 1).astype(np.float32)
        self.env_, self.bands_ = env, np.clip(Bn, 0, 1).astype(np.float32)
        try:
            np.savez_compressed(cache, key=key, env=self.env_, bands=self.bands_)
        except OSError:
            pass

    def _synthetic(self):
        n = int(SONG_END * self.FPS) + 1
        t = np.arange(n) / self.FPS
        ph = ((t - BEAT0) / BEAT) % 1.0
        kick = np.exp(-ph * 6)
        on = ((t > 27.3) & ~((t > 139.3) & (t < 147.3)) & (t < 276)).astype(np.float32)
        low = on * (0.55 + 0.4 * kick)
        mid = 0.25 + on * 0.5
        high = 0.2 + on * 0.6
        self.env_ = np.stack([low, mid, high, kick * on, kick * on], 1).astype(np.float32)
        rng = np.random.default_rng(39)
        base = np.linspace(1, 0.4, self.NB)[None, :]
        self.bands_ = np.clip(base * (0.4 + 0.6 * rng.random((n, self.NB))) * (0.3 + 0.7 * on[:, None]),
                              0, 1).astype(np.float32)

    def env(self, t):
        i = int(clamp(t * self.FPS, 0, len(self.env_) - 1))
        return self.env_[i]

    def bands(self, t):
        """Spectrum with contrast stretched for display (the master is heavily compressed)."""
        i = int(clamp(t * self.FPS, 0, len(self.bands_) - 1))
        return np.clip((self.bands_[i] - 0.55) / 0.45, 0, 1)

    def wave(self, t, n=1024, step=2):
        if self.samples is None:
            x = np.linspace(0, 1, n)
            return (0.25 * np.sin(2 * np.pi * (x * 6 + t * 3)) + 0.1 * np.sin(2 * np.pi * x * 23)).astype(np.float32)
        c = int(t * self.SR)
        a = c - n * step // 2
        idx = a + np.arange(n) * step
        idx = np.clip(idx, 0, len(self.samples) - 1)
        return self.samples[idx]


class Player:
    """Plays the song through an external player and exposes the playback clock."""

    def __init__(self, path, start=0.0, backend='auto', offset=0.0):
        self.path = path
        self.start_at = max(0.0, start)
        self.backend = backend
        self.offset = offset
        self.proc = None
        self.t0 = None
        self.lat = 0.0
        self._off = None
        self._stop = False
        self._tmp = None
        self.sock = None

    def begin(self):
        be = self.backend
        if be == 'auto':
            be = next((b for b in ('mpv', 'ffplay', 'afplay') if shutil.which(b)), 'none')
        if not self.path or not os.path.exists(self.path):
            be = 'none'
        self.backend = be
        dn = subprocess.DEVNULL
        if be == 'mpv':
            self.sock = os.path.join(tempfile.gettempdir(), f'miku-mv-{os.getpid()}.sock')
            cmd = ['mpv', '--no-video', '--no-terminal', '--really-quiet', '--audio-display=no',
                   f'--start={self.start_at:.3f}', f'--input-ipc-server={self.sock}', self.path]
            self.proc = subprocess.Popen(cmd, stdin=dn, stdout=dn, stderr=dn)
            threading.Thread(target=self._mpv_sync, daemon=True).start()
        elif be == 'ffplay':
            cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', '-ss', f'{self.start_at:.3f}', self.path]
            self.proc = subprocess.Popen(cmd, stdin=dn, stdout=dn, stderr=dn)
            self.lat = 0.12
        elif be == 'afplay':
            src = self.path
            if self.start_at > 0.01 and shutil.which('ffmpeg'):
                fd, self._tmp = tempfile.mkstemp(suffix='.m4a')
                os.close(fd)
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{self.start_at:.3f}', '-i', self.path,
                                '-c:a', 'aac', '-b:a', '192k', self._tmp], check=False)
                src = self._tmp
            self.proc = subprocess.Popen(['afplay', src], stdin=dn, stdout=dn, stderr=dn)
            self.lat = 0.06
        self.t0 = time.perf_counter()

    def _mpv_sync(self):
        s = None
        for _ in range(300):
            if self._stop:
                return
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.sock)
                break
            except OSError:
                s.close()
                s = None
                time.sleep(0.02)
        if s is None:
            return
        s.settimeout(0.5)
        buf = b''
        while not self._stop:
            try:
                ts = time.perf_counter()
                s.sendall(b'{"command":["get_property","playback-time"],"request_id":39}\n')
                resp = None
                while resp is None:
                    chunk = s.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        if msg.get('request_id') == 39:
                            resp = msg
                tr = time.perf_counter()
                val = resp.get('data')
                if resp.get('error') == 'success' and isinstance(val, (int, float)) and val > self.start_at - 1:
                    off = val - (ts + tr) / 2
                    if self._off is None or abs(off - self._off) > 0.2:
                        self._off = off
                    else:
                        self._off += (off - self._off) * 0.15
            except (OSError, socket.timeout):
                if self.proc is None or self.proc.poll() is not None:
                    return
            time.sleep(0.25 if self._off is not None else 0.02)

    def time(self):
        now = time.perf_counter()
        if self.backend == 'mpv':
            if self._off is not None:
                return now + self._off + self.offset
            waited = now - self.t0
            if waited < 3.0:
                return self.start_at
            return self.start_at + waited - 3.0 + self.offset
        return self.start_at + (now - self.t0) - self.lat + self.offset

    def stop(self):
        self._stop = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(1.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for p in (self._tmp, self.sock):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
