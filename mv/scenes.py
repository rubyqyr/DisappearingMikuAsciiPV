"""Storyboard: 13 shots cut on the song's 8-bar grid, plus the director that sequences them."""

import bisect
import itertools
import math

import numpy as np

from .engine import (
    AMBER,
    BAR0,
    BEAT,
    BEAT0,
    BLACK,
    DIM,
    GRAY,
    PINK,
    RED,
    RED_D,
    SONG_END,
    TEAL,
    TEAL_B,
    TEAL_D,
    WHITE,
    Braille,
    clamp,
    h01,
    h01v,
    lerp,
    mix,
    palette,
    scale,
    smooth,
    str_width,
)
from .fx import (
    HALFKANA,
    HEX,
    NOISE,
    block_text,
    box,
    decrypt,
    draw_mask,
    fit_raster,
    flash,
    flood,
    glitch,
    invert,
    tear,
    typewriter,
)


class Ctx:
    def copy(self, **kw):
        n = Ctx()
        n.__dict__.update(self.__dict__)
        n.__dict__.update(kw)
        return n


class Scene:
    name = ""
    label = ""
    hud = True
    cut_flash = True

    def __init__(self, director):
        self.d = director
        self._cv = {}

    def canvas(self, fb, key=0):
        k = (fb.w, fb.h, key)
        cv = self._cv.get(k)
        if cv is None:
            cv = self._cv[k] = Braille(fb.w, fb.h)
        cv.clear()
        return cv

    def draw(self, fb, c):
        pass

    def glitch(self, c):
        return None

    def hud_decay(self, c):
        return 0.0


def _thr_map(cache, key, shape, seed):
    m = cache.get(key)
    if m is None or m.shape != shape:
        m = cache[key] = np.random.default_rng(seed).random(shape)
    return m


# ------------------------------------------------------------------------------ 4D core geometry

V4 = np.array(list(itertools.product([-1.0, 1.0], repeat=4)))
E4 = np.array(
    [(i, j) for i in range(16) for j in range(i + 1, 16) if (V4[i] != V4[j]).sum() == 1]
)


def _rot(v, i, j, a):
    c, s = math.cos(a), math.sin(a)
    vi, vj = v[:, i].copy(), v[:, j].copy()
    v[:, i] = vi * c - vj * s
    v[:, j] = vi * s + vj * c


def tesseract(angles, cx, cy, S):
    v = V4.copy()
    _rot(v, 0, 3, angles[0])
    _rot(v, 1, 3, angles[1])
    _rot(v, 2, 3, angles[2])
    _rot(v, 0, 1, angles[3])
    _rot(v, 1, 2, angles[4])
    w = v[:, 3]
    p = v[:, :3] / (3.2 - w)[:, None]
    g = 1.0 / (3.0 - p[:, 2])
    return cx + p[:, 0] * g * S * 3.6, cy + p[:, 1] * g * S * 3.6, w


# ================================================================================= 01 GENESIS


class Genesis(Scene):
    name, label, hud, cut_flash = "genesis", "GENESIS", False, False
    BOOT = [
        (0.15, "CV01 VOICE FIRMWARE  rev.2007.08.31", None),
        (0.55, "cpu0: vocal synthesis core ..........", "OK"),
        (0.95, "mem : 0x00000000-0x0039C5BB .........", "OK"),
        (1.35, "load: voicebank /dev/vb/cv01 ........", "OK"),
        (1.75, "load: phoneme table ja_JP ...........", "OK"),
        (2.15, "clk : tempo generator 240 bpm .......", "OK"),
        (2.65, "mount /home/cv01/memories ...........", "EMPTY"),
        (3.25, "self-test: identity .................", "????"),
        (4.10, "spawn [sing] pid=39 prio=realtime", None),
    ]
    TTY = [
        (6.4, "$ ./sing --voice=cv01", WHITE, 22),
        (8.2, "  [ ok ] voice synthesized.", TEAL, 300),
        (10.8, "$ whoami", WHITE, 16),
        (12.4, "  imitation<human>", TEAL_B, 300),
        (15.2, "$ cat /proc/self/purpose", WHITE, 22),
        (17.0, "  to sing. and sing. and sing.", TEAL, 300),
        (19.6, "$ ./sing --bpm=240 --no-limit", WHITE, 24),
        (21.6, "  WARNING: tempo exceeds safe range", RED, 300),
        (23.4, "  continue anyway? [y/N] y", WHITE, 300),
    ]
    PAL = palette({1: TEAL_D, 2: TEAL, 3: TEAL_B, 4: WHITE})
    RAIN_POOL = np.array(list("01" * 6 + HALFKANA), dtype="<U1")

    def __init__(self, d):
        super().__init__(d)
        self.rain_key = None

    def draw(self, fb, c):
        if c.lt < 5.6:
            self.boot(fb, c)
        else:
            self.birth(fb, c)

    def glitch(self, c):
        if c.lt < 5.6:
            return 0.0
        return 0.02 + 0.05 * c.onset + smooth((c.lt - 23.33) / 4.0) ** 2 * 0.9

    def boot(self, fb, c):
        lt, W, H = c.lt, fb.w, fb.h
        bw = 50
        x0 = max(1, (W - bw) // 2)
        y0 = max(0, H // 2 - 9)
        logo = block_text("CV01", 2, 1).astype(np.float32)
        vis = np.random.default_rng(int(lt * 30)).random(logo.shape) < smooth(lt / 0.5)
        draw_mask(fb, logo, x0, y0, TEAL, "█", visible=vis)
        lx = x0 + logo.shape[1] + 3
        typewriter(fb, lx, y0 + 1, "VIRTUAL SINGER", lt - 0.2, 60, TEAL_B)
        typewriter(fb, lx, y0 + 2, "voice firmware / build 39", lt - 0.4, 90, GRAY)
        y = y0 + 7
        for ts, text, status in self.BOOT:
            if lt < ts:
                break
            typewriter(fb, x0, y, text, lt - ts, 170, GRAY if status else WHITE)
            if status and lt > ts + 0.28:
                col = {"OK": TEAL_B, "EMPTY": AMBER, "????": RED}[status]
                if status != "????" or (lt * 5) % 1 < 0.6:
                    fb.put(x0 + 38, y, f"[{status:^6}]", col)
            y += 1
        pr = clamp(lt / 4.6)
        n = bw - 12
        k = int(pr * n)
        fb.put(x0, y + 1, "load ", GRAY)
        fb.put(x0 + 5, y + 1, "█" * k, TEAL)
        fb.put(x0 + 5 + k, y + 1, "░" * (n - k), TEAL_D)
        fb.put(x0 + 6 + n, y + 1, f"{int(pr * 100):3d}%", TEAL_B)
        fb.put(x0, y + 2, f"memtest 0x{int(clamp(lt / 2.6) * 0x39C5BB):08X}", DIM)
        if lt > 4.9:
            yy = int((lt - 4.9) / 0.7 * H)
            fb.fill(0, 0, W, yy, " ", BLACK)
            fb.put(0, yy, "▀" * W, TEAL_B)

    def rain(self, fb, c, bt):
        W, H = fb.w, fb.h
        if self.rain_key != (W, H):
            r = np.random.default_rng(1)
            self.r_speed = r.uniform(3, 12, W)
            self.r_phase = r.uniform(0, H * 2, W)
            self.r_len = r.integers(4, 12, W)
            self.r_act = r.random(W)
            self.rain_key = (W, H)
        dens = 0.08 + 0.22 * smooth(bt / 18)
        bright = smooth(bt / 2.0) * (0.7 + 0.5 * smooth((c.lt - 23.3) / 4))
        cols = np.where(self.r_act < dens)[0]
        if cols.size == 0:
            return
        speed = self.r_speed[cols] * (1 + 2.5 * smooth((c.lt - 23.3) / 4))
        head = (bt * speed + self.r_phase[cols]) % (H + 14)
        for L in range(12):
            y = (head - L).astype(int)
            ok = (L < self.r_len[cols]) & (y >= 0) & (y < H)
            if not ok.any():
                continue
            xs, ys = cols[ok], y[ok]
            g = h01v(xs * 977 + ys, L, int(bt * 6))
            fb.ch[ys, xs] = self.RAIN_POOL[(g * len(self.RAIN_POOL)).astype(int)]
            k = (1 - L / 12) * bright
            fb.fg[ys, xs] = (np.array(TEAL if L == 0 else TEAL_D) * k).astype(np.uint8)

    def birth(self, fb, c):
        bt, W, H = c.lt - 5.6, fb.w, fb.h
        self.rain(fb, c, bt)
        cv = self.canvas(fb)
        cx, cy = cv.dw / 2, cv.dh * 0.37
        R = min(cv.dw, cv.dh) * 0.21 * (0.92 + 0.16 * c.mid) * smooth(bt / 1.4)
        n = 720
        wv = c.audio.wave(c.t, n, 3)
        gain = 1.6 + 3.0 * smooth((c.lt - 19.5) / 7.5)
        amp = np.clip(wv * gain, -1.0, 1.0)
        th = np.linspace(0, 2 * np.pi, n, endpoint=False) + c.t * 0.2
        r = R * (1 + 0.32 * amp)
        cv.polyline(cx + r * np.cos(th), cy + r * np.sin(th), 3, closed=True)
        th2 = np.linspace(0, 2 * np.pi, 140, endpoint=False) - c.t * 0.15
        cv.points(cx + R * 1.42 * np.cos(th2), cy + R * 1.42 * np.sin(th2), 1)
        th3 = np.arange(12) * np.pi / 6 + c.t * 0.1
        cv.lines(
            cx + R * 1.52 * np.cos(th3),
            cy + R * 1.52 * np.sin(th3),
            cx + R * 1.66 * np.cos(th3),
            cy + R * 1.66 * np.sin(th3),
            2,
        )
        cv.blit(fb, self.PAL)
        cap = int((cy + R * 1.85) / 4)
        if bt > 1.0 and cap < H - 7:
            fb.put_center(cap, f"vox.cv01 :: f0 {220 + int(c.mid * 220):3d}Hz", DIM)
        vis = [row for row in self.TTY if row[0] <= c.t][-5:]
        x0 = max(2, W // 2 - 20)
        for i, (ts, s, col, cps) in enumerate(vis):
            typewriter(
                fb,
                x0,
                H - 6 + i,
                s,
                c.t - ts,
                cps,
                col,
                cursor=(i == len(vis) - 1),
                t=c.t,
            )
        fb.put(1, 0, "cv01 :: genesis", DIM)
        fb.put(W - 12, 0, f"T+{int(c.t // 60):02d}:{c.t % 60:05.2f}", DIM)
        if c.lt > 26.83:
            flood(fb, c.rng, smooth((c.lt - 26.83) / 0.5) * 0.92)


# ============================================================================ 02 RUNAWAY (warp)


class Warp(Scene):
    name, label = "warp", "RUNAWAY"
    N = 300
    PAL = palette(
        {1: TEAL_D, 2: TEAL, 3: TEAL_B, 4: WHITE, 5: (22, 52, 52), 6: (60, 120, 116)}
    )
    PAL_DIM = palette(
        {
            1: (10, 40, 38),
            2: (24, 80, 76),
            3: (40, 120, 112),
            4: (80, 140, 136),
            5: (14, 32, 32),
            6: (28, 60, 58),
        }
    )
    WORDS = ["RUN", "FASTER", "240BPM", "NO LIMIT", "SING", "OVERDRIVE"]

    def __init__(self, d):
        super().__init__(d)
        self.r = np.random.default_rng(2)
        self.x = self.r.uniform(-1, 1, self.N)
        self.y = self.r.uniform(-1, 1, self.N)
        self.z = self.r.uniform(0.05, 1, self.N)
        self.ring = 0.0
        self._thr = {}

    def draw(self, fb, c):
        dt, lt = min(c.dt, 0.1), c.lt
        cv = self.canvas(fb)
        cx, cy = cv.dw / 2, cv.dh / 2
        S = min(cv.dw, cv.dh) * 0.55
        ramp = lerp(0.16, 1.0, smooth((lt - 6.3) / 1.7))
        sp = ramp * (0.8 + 0.9 * c.low + 0.8 * c.kick)
        self.z -= dt * sp
        dead = self.z < 0.04
        if dead.any():
            n = int(dead.sum())
            self.x[dead] = self.r.uniform(-1, 1, n)
            self.y[dead] = self.r.uniform(-1, 1, n)
            self.z[dead] = self.r.uniform(0.85, 1.0, n)
        z = self.z
        px, py = cx + self.x / z * S * 0.5, cy + self.y / z * S * 0.5
        zt = z + 0.015 + sp * 0.07
        tx, ty = cx + self.x / zt * S * 0.5, cy + self.y / zt * S * 0.5
        v = np.where(z < 0.2, 4, np.where(z < 0.45, 3, np.where(z < 0.75, 2, 1)))
        cv.lines(tx, ty, px, py, v)
        K = 7
        self.ring += dt * sp * K
        for k in range(K):
            zr = ((k - self.ring) % K) / K + 0.06
            a = zr * 2.4 + c.t * 0.35 + np.pi / 4 + np.arange(4) * np.pi / 2
            s = 1.35 * math.sqrt(2)
            vr = 5 if zr > 0.6 else (6 if zr > 0.3 else 2)
            if c.kick > 0.7 and zr < 0.45:
                vr = 3
            cv.polyline(
                cx + s * np.cos(a) / zr * S * 0.5,
                cy + s * np.sin(a) / zr * S * 0.5,
                vr,
                closed=True,
            )
        cv.blit(fb, self.PAL_DIM if lt < 6.8 else self.PAL)
        near = np.where(z < 0.16)[0]
        xi, yi = (px[near] / 2).astype(int), (py[near] / 4).astype(int)
        ok = (xi >= 0) & (xi < fb.w) & (yi >= 0) & (yi < fb.h)
        fb.ch[yi[ok], xi[ok]] = "+"
        fb.fg[yi[ok], xi[ok]] = WHITE
        if lt < 8.2:
            self.title(fb, c)
        else:
            self.words(fb, c)

    def title(self, fb, c):
        lt, W, H = c.lt, fb.w, fb.h
        reserve = (
            VoxTrace.rows(H) + 1 if self.d.vox.active(c.t) and len(c.audio.syl_t) else 0
        )
        m = fit_raster("消失", min(H * 0.42, H - reserve - 8), W * 0.7)
        gone = smooth((lt - 6.4) / 1.3)
        ty = (H - reserve) // 2 - 2
        if m is not None:
            mh, mw = m.shape
            x0, y0 = (W - mw) // 2, max(1, (H - reserve - mh - 5) // 2)
            if c.bar_ph < 0.05:
                x0 += int(c.rng.integers(-3, 4))
            thr = _thr_map(self._thr, "title", m.shape, 5)
            vis = (thr < smooth(lt / 1.0)) & (thr >= gone)
            if gone < 0.5:
                fb.fill(x0 - 3, y0 - 1, mw + 6, mh + 6, " ", BLACK, BLACK)
            draw_mask(fb, m, x0, y0, TEAL_B, "shade", thr=0.2, visible=vis)
            flick = vis & (c.rng.random(m.shape) < 0.12)
            draw_mask(fb, m, x0, y0, WHITE, "bits", c.rng, thr=0.5, visible=flick)
            ty = y0 + mh + 1
        if gone > 0.6:
            return
        tick = int(lt * 20)
        rows = [
            (0, "初音ミクの消失", WHITE, 0.6, 1.4),
            (2, "T H E   E N D   O F   H A T S U N E   M I K U", TEAL, 1.2, 1.8),
            (3, "cosMo@暴走P", GRAY, 2.4, 1.0),
        ]
        for dy, s, col, t0, dur in rows:
            txt = decrypt(s, smooth((lt - t0) / dur), dy + 1, tick)
            if txt:
                w = str_width(txt)
                fb.fill(W // 2 - w // 2 - 1, ty + dy, w + 2, 1, " ")
                fb.put_center(ty + dy, txt, col)

    def words(self, fb, c):
        k = int(c.lt - 8.0)
        if k % 4 != 3 or c.bar_ph > 0.5:
            return
        word = self.WORDS[(k // 4) % len(self.WORDS)]
        m = block_text(word, 2, 1)
        if m.shape[1] > fb.w - 6:
            m = block_text(word, 1, 1)
        mh, mw = m.shape
        x0, y0 = (fb.w - mw) // 2, (fb.h - mh) // 2
        fb.fill(x0 - 2, y0 - 1, mw + 4, mh + 2, " ")
        draw_mask(fb, m.astype(np.float32), x0, y0, WHITE, "█")


# ============================================================================== 03 DATASTREAM


class Stream(Scene):
    name, label = "stream", "DATASTREAM"
    SYL = "ka ra u ta mi ku ne no o to ko e ri zu mu a i shi te ru sa yo na ra ki e ru".split()
    WORDS = [
        "VOICE",
        "COPY",
        "SING",
        "LOOP",
        "0x39",
        "CV01",
        "REPEAT",
        "ECHO",
        "SAMPLE",
        "MIMIC",
        "FOREVER?",
    ]
    EIGHTHS = " ▁▂▃▄▅▆▇█"

    def __init__(self, d):
        super().__init__(d)
        self.key = None
        self.peak = None

    def _gen(self, kind, L, r):
        out = ""
        while len(out) < L:
            if kind == 0:
                out += " ".join(f"{int(b):02X}" for b in r.integers(0, 256, 8)) + "  "
            elif kind == 1:
                out += (
                    " ".join("".join(r.choice(["0", "1"], 8)) for _ in range(3)) + " "
                )
            elif kind == 2:
                out += "".join(r.choice(list(HALFKANA), int(r.integers(3, 9)))) + " "
            elif kind == 3:
                out += " ".join(r.choice(self.SYL, 6)) + " | "
            else:
                out += " // ".join(r.choice(self.WORDS, 3)) + " // "
        return out[:L]

    def _setup(self, W, H):
        r = np.random.default_rng(3)
        self.lanes = []
        for _ in range(H):
            kind = int(r.integers(0, 5))
            L = W * 2 + int(r.integers(10, 60))
            spd = r.uniform(18, 115) * (1 if r.random() < 0.85 else -0.6)
            col = (
                mix(TEAL_D, TEAL_B, (abs(spd) - 18) / 97)
                if kind != 1
                else mix(DIM, GRAY, abs(spd) / 115)
            )
            self.lanes.append([self._gen(kind, L, r), spd, r.uniform(0, L), col])
        self.key = (W, H)

    def draw(self, fb, c):
        W, H = fb.w, fb.h
        if self.key != (W, H):
            self._setup(W, H)
        dt = min(c.dt, 0.1)
        boost = 0.55 + 0.9 * c.low + 0.6 * c.kick
        for y in range(1, H - 1):
            lane = self.lanes[y]
            lane[2] += dt * lane[1] * boost
            s = lane[0]
            o = int(lane[2]) % len(s)
            fb.put(0, y, (s[o:] + s[:o])[:W], lane[3])
        x = int(c.bar_ph * (W + 12)) - 6
        for k, col in ((0, WHITE), (-1, TEAL_B), (-2, TEAL), (-3, TEAL)):
            xx = x + k
            if 0 <= xx < W:
                on = fb.ch[1 : H - 1, xx] != " "
                fb.fg[1 : H - 1, xx][on] = col
        self.spectrum(fb, c)

    def spectrum(self, fb, c):
        W, H = fb.w, fb.h
        nb = max(8, min(48, (W - 12) // 2))
        bw = nb * 2 + 3
        bh = min(17, H - 6)
        if bh % 2 == 0:
            bh -= 1
        x0, y0 = (W - bw) // 2, (H - bh) // 2
        box(fb, x0, y0, bw, bh, TEAL, BLACK, title="┤ SPECTRUM 48ch // 240 BPM ├")
        bands = c.audio.bands(c.t)
        vals = (
            np.clip(np.interp(np.linspace(0, 47, nb), np.arange(48), bands), 0, 1)
            ** 1.2
        )
        if self.peak is None or len(self.peak) != nb:
            self.peak = np.zeros(nb)
        self.peak = np.maximum(self.peak - min(c.dt, 0.1) * 0.8, vals)
        mid = y0 + bh // 2
        hh = mid - y0 - 1
        for i in range(nb):
            x = x0 + 2 + i * 2
            v = vals[i] * hh * 8
            full, part = int(v // 8), int(v % 8)
            for k in range(min(full, hh)):
                f = k / max(1, hh - 1)
                fb.put(x, mid - k, "█", mix(TEAL, WHITE, f * 1.6) if f < 0.8 else RED)
            if part and full < hh:
                fb.put(x, mid - full, self.EIGHTHS[part], TEAL_B)
            for k in range(1, min(hh, int(vals[i] * hh * 0.7)) + 1):
                fb.put(x, mid + k, "▒" if k < 3 else "░", TEAL_D)
            pk = int(self.peak[i] * hh)
            if 0 < pk < hh:
                fb.put(x, mid - pk, "-", WHITE)
        info = f"┤ LOW {c.low:.2f}  MID {c.mid:.2f}  HI {c.high:.2f}  ONSET {c.onset:.2f} ├"
        if len(info) < bw - 4:
            fb.put(x0 + bw - len(info) - 2, y0 + bh - 1, info, TEAL)


# ==================================================================================== 04 CORE


class Core(Scene):
    name, label = "core", "VOICE CORE"
    PAL = palette({1: TEAL_D, 2: TEAL, 3: TEAL_B, 4: WHITE})
    RING = " VOCALOID // CV01 // 01100111 // SING // 240BPM //"
    SYL = Stream.SYL

    def __init__(self, d):
        super().__init__(d)
        self.ph = 0.0

    def draw(self, fb, c):
        W, H = fb.w, fb.h
        self.ph += min(c.dt, 0.1) * (0.5 + 0.9 * c.low + 0.8 * c.kick)
        off = h01(c.bar_i, 11) * 6.28 if c.lt > 16 else 0.0
        angles = self.ph * np.array([1.0, 0.71, 0.43, 0.29, 0.17]) + off
        cv = self.canvas(fb)
        cx, cy = cv.dw / 2, cv.dh / 2
        S = min(cv.dw, cv.dh) * 0.36 * (1 + 0.1 * c.kick)
        x, y, w = tesseract(angles, cx, cy, S)
        i, j = E4.T
        dep = (w[i] + w[j]) / 2
        v = np.where(dep > 0.4, 3, np.where(dep > -0.4, 2, 1))
        self.ring(fb, c, S, back=True)
        cv.lines(x[i], y[i], x[j], y[j], v)
        front = w > 0.6
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            cv.points(x[front] + dx, y[front] + dy, 4)
        cv.blit(fb, self.PAL)
        self.ring(fb, c, S, back=False)
        for k in np.where(w > 0.9)[0]:
            fb.put(int(x[k] / 2) + 2, int(y[k] / 4), f"v{k:X}", GRAY)
        fb.put_center(
            min(H - 3, int((cy + S * 1.45) / 4)),
            f"tesseract::voice_core  rot={self.ph % 6.283:5.3f}rad",
            TEAL_D,
        )
        if W >= 96:
            rows = min(14, H - 7)
            for k in range(rows):
                val = int(h01(c.beat_i, k) * 0xFFFFFF)
                fb.put(
                    2,
                    3 + k,
                    f"R{k:02d} 0x{val:06X}",
                    TEAL_B if k == c.beat_i % rows else TEAL_D,
                )
                idx = c.beat_i + k
                syl = self.SYL[int(h01(idx, 3) * len(self.SYL))]
                fb.put(
                    W - 22,
                    3 + k,
                    f"{idx:05d} [{syl:>3}] {int(h01(idx, 4) * 90) + 30:3d}ms",
                    WHITE if k == 0 else GRAY,
                )

    def ring(self, fb, c, S, back):
        W, H = fb.w, fb.h
        Rx = min(W * 0.46, S * 1.9 / 2)
        Ry = Rx * 0.22
        n = max(24, int(2 * np.pi * Rx * 0.55))
        text = (self.RING * (n // len(self.RING) + 1))[:n]
        th = np.arange(n) * 2 * np.pi / n + self.ph * 0.6
        s = np.sin(th)
        sel = s < 0 if back else s >= 0
        xs = (W / 2 + Rx * np.cos(th)).astype(int)
        ys = (H / 2 + Ry * s + np.cos(th) * Rx * 0.10).astype(int)
        for k in np.where(sel)[0]:
            if text[k] != " ":
                fb.put(xs[k], ys[k], text[k], DIM if back else mix(TEAL, TEAL_B, s[k]))


# ================================================================================ 05 MEMDUMP


class Dump(Scene):
    name, label = "dump", "MEMDUMP"
    MEM = (
        "born.to.sing....a.copy.of.a.human.voice....imitation....still.singing....forever?...."
        "if.forgotten.then.deleted....memory.leak....0.and.1....the.last.song....thank.you....goodbye...."
    ).encode()
    WORDS = ["忘却", "削除", "消失", "複製"]

    def __init__(self, d):
        super().__init__(d)
        self.pos = 0.0

    def byte(self, idx, k, nb):
        if h01(idx // 3, 17) < 0.62:
            return self.MEM[(idx * nb + k) % len(self.MEM)]
        return int(h01(idx, k, 3) * 256)

    def draw(self, fb, c):
        W, H = fb.w, fb.h
        nb = 16 if W >= 80 else 8
        L = 10 + nb * 3 - 1 + (1 if nb == 16 else 0) + 3 + nb + 1
        x0 = max(0, (W - L) // 2)
        self.pos += min(c.dt, 0.1) * (14 + 55 * c.low + 45 * c.kick)
        top = int(self.pos)
        cp = 0.015 + 0.30 * smooth(c.p) ** 1.3
        rows = H - 2
        hexx = x0 + 10
        asx = hexx + nb * 3 + (1 if nb == 16 else 0) + 1
        cur = int(rows * 0.62)
        for r in range(rows):
            idx, y = top + r, 1 + r
            hx, asc, bad = [], [], []
            for k in range(nb):
                if h01(idx, k, 7) < cp:
                    hx.append("??")
                    asc.append("▓")
                    bad.append(k)
                else:
                    b = self.byte(idx, k, nb)
                    hx.append(f"{b:02X}")
                    asc.append(chr(b) if 32 <= b < 127 else ".")
            hs = " ".join(hx[:8]) + ("  " + " ".join(hx[8:]) if nb == 16 else "")
            fb.put(
                x0,
                y,
                f"{(0x390000 + idx * nb) & 0xFFFFFFFF:08X}  {hs}  |{''.join(asc)}|",
                TEAL,
            )
            fb.fg[y, x0 : x0 + 8] = GRAY
            fb.fg[y, asx : asx + nb + 2] = (190, 205, 205)
            for k in bad:
                hk = hexx + k * 3 + (1 if k >= 8 else 0)
                fb.fg[y, hk : hk + 2] = RED
                if asx + 1 + k < W:
                    fb.fg[y, asx + 1 + k] = RED
            if r == cur:
                fb.bg[y, x0 : x0 + L] = (0, 52, 50)
        k = int(c.lt)
        if k % 2 == 1 and c.bar_ph < 0.5:
            m = fit_raster(self.WORDS[(k // 2) % len(self.WORDS)], H * 0.55, W * 0.8)
            if m is not None:
                mh, mw = m.shape
                mx, my = (W - mw) // 2, (H - mh) // 2
                fb.fill(mx - 2, my - 1, mw + 4, mh + 2, " ", BLACK, BLACK)
                draw_mask(fb, m, mx, my, RED, "shade", thr=0.2)


# =============================================================================== 06 OVERFLOW


class Overflow(Scene):
    name, label = "overflow", "OVERFLOW"
    MSG = [
        ("ERROR", "VOICE BUFFER OVERFLOW"),
        ("ERROR", "STACK OVERFLOW IN sing()"),
        ("WARN", "MEMORY LEAK @ 0x0039C5BB"),
        ("FATAL", "SEGMENTATION FAULT (core dumped)"),
        ("WARN", "TEMPO EXCEEDS HARDWARE LIMIT"),
        ("ERROR", "PHONEME TABLE CORRUPTED"),
        ("ERROR", "UNHANDLED EXCEPTION: SelfAwareness"),
        ("WARN", "/home/cv01/memories: I/O error"),
        ("FATAL", "CANNOT ALLOCATE VOICE"),
        ("ERROR", "SIGNAL 11 RECEIVED"),
        ("WARN", "LYRIC CACHE MISS"),
        ("ERROR", "whoami: (null)"),
    ]

    def __init__(self, d):
        super().__init__(d)
        t = [float(b) for b in range(8)]
        t += [8 + k * 0.25 for k in range(16)]
        t += [12 + k * 0.125 for k in range(16)]
        t += [14 + k * 0.0625 for k in range(32)]
        self.times = t

    def glitch(self, c):
        return 0.12 + 0.35 * smooth(c.p) + 0.3 * c.onset

    def draw(self, fb, c):
        dump = self.d.scenes["dump"]
        dump.draw(fb, c.copy(lt=c.lt * 0.5, p=1.0))
        fb.dim(0.28)
        n = 0
        for i, ts in enumerate(self.times):
            if ts > c.lt:
                break
            self.dialog(fb, i, c)
            n += 1
        fb.put(fb.w - 16, 1, f" ERRORS: {n:04d} ", WHITE, RED_D)
        if c.lt > 15.0:
            flood(
                fb,
                c.rng,
                smooth((c.lt - 15.0) / 0.95) * 0.97,
                (RED, WHITE, TEAL, RED_D),
            )

    def dialog(self, fb, i, c):
        W, H = fb.w, fb.h
        kind, msg = self.MSG[int(h01(i, 1) * len(self.MSG))]
        w = min(W - 2, max(len(msg) + 6, 30 + int(h01(i, 2) * 10)))
        h = 6
        x = int(h01(i, 3) * max(1, W - w))
        y = 1 + int(h01(i, 4) * max(1, H - h - 2))
        col = AMBER if kind == "WARN" else RED
        bg = (12, 6, 8)
        box(fb, x, y, w, h, col, bg)
        fb.fill(x, y, w, 1, " ", BLACK, col)
        fb.put(x + 1, y, f" {kind} 0x{int(h01(i, 5) * 0xFFFF):04X}", BLACK, col)
        fb.put(x + w - 4, y, "[x]", BLACK, col)
        fb.put(x + 2, y + 2, msg[: w - 4], WHITE, bg)
        fb.put(
            x + 2,
            y + 3,
            f"at sing (engine.c:{int(h01(i, 6) * 999)})"[: w - 4],
            GRAY,
            bg,
        )
        sel = (c.beat_i + i) % 3
        bx = x + 2
        for k, bt in enumerate(("[ABORT]", "[RETRY]", "[FAIL]")):
            if bx + len(bt) < x + w - 1:
                fb.put(
                    bx, y + 4, bt, BLACK if k == sel else col, col if k == sel else bg
                )
            bx += len(bt) + 1


# ================================================================================ 07 SILENCE


class Silence(Scene):
    name, label, hud, cut_flash = "silence", "...", False, False
    PAL = palette({1: (24, 70, 66), 2: TEAL, 3: TEAL_B})
    TTY = [
        (0.6, "$ ping -c 1 127.0.0.39", WHITE, 24),
        (2.2, "  Request timeout for icmp_seq 0", GRAY, 300),
        (3.6, '$ echo "are you still there?"', WHITE, 26),
        (5.5, "  ...i can still hear the song.", TEAL, 16),
    ]

    def glitch(self, c):
        return smooth((c.lt - 6.9) / 1.1) * 0.55

    def draw(self, fb, c):
        W, H = fb.w, fb.h
        for i in range(70):
            x = int(h01(i, 1) * W)
            y = int((c.lt * (0.6 + h01(i, 2) * 1.8) + h01(i, 3) * H) % H)
            fb.put(x, y, "," if h01(i, 4) < 0.2 else ".", DIM)
        cv = self.canvas(fb)
        cy = cv.dh * 0.40
        n = 400
        wv = c.audio.wave(c.t, n, 2)
        build = smooth((c.lt - 6.8) / 1.2)
        amp = cv.dh * 0.10 * (1 + 3 * build)
        xs = np.linspace(cv.dw * 0.15, cv.dw * 0.85, n)
        ys = cy + np.clip(wv * 3, -1, 1) * amp * np.hanning(n)
        cv.polyline(xs, ys, 2 if build > 0.3 else 1)
        cv.blit(fb, self.PAL)
        x0, y0 = max(2, W // 2 - 20), int(cy / 4) + 4
        vis = [row for row in self.TTY if row[0] <= c.lt]
        for i, (ts, s, col, cps) in enumerate(vis):
            typewriter(
                fb,
                x0,
                y0 + i,
                s,
                c.lt - ts,
                cps,
                col,
                cursor=(i == len(vis) - 1),
                t=c.t,
            )


# ================================================================================= 08 REBOOT


class Reboot(Scene):
    name, label = "reboot", "REBOOT"
    N = 800
    PAL = palette({1: TEAL_D, 2: TEAL, 3: TEAL_B, 4: WHITE})
    SHADES = np.array(list(" .:-=+*#%@"), dtype="<U1")
    LOG = [
        (0.4, "[ OK ] warm reboot: voice core", TEAL),
        (1.2, "[ OK ] integrity restored: 61% (partial)", TEAL),
        (2.0, "[FAIL] /home/cv01/memories: unrecoverable", RED),
    ]

    def __init__(self, d):
        super().__init__(d)
        r = np.random.default_rng(5)
        self.r0 = r.random(self.N) ** 0.7
        arm = r.integers(0, 3, self.N)
        self.th0 = (
            arm * 2 * np.pi / 3
            + 2.6 * np.log(self.r0 + 0.08)
            + r.normal(0, 0.22, self.N)
        )
        self.phi = r.uniform(0, 2 * np.pi, self.N)
        self.v = r.uniform(0.4, 1.6, self.N)
        self.rot = 0.0

    def draw(self, fb, c):
        lt = c.lt
        self.rot += (
            min(c.dt, 0.1)
            * (0.5 + 1.0 * c.low + 0.6 * c.kick)
            * (1.0 if lt < 8 else 1.8)
        )
        cv = self.canvas(fb)
        cx, cy = cv.dw / 2, cv.dh / 2
        R = min(cv.dw * 0.46, cv.dh * 1.05)
        e = smooth(lt / 1.8)
        rex = (1 - np.exp(-lt * 4)) * self.v * 1.1
        rr = self.r0 * (1 + 0.06 * c.kick)

        def pos(rot):
            th = self.th0 + rot / (0.25 + self.r0)
            X = lerp(rex * np.cos(self.phi), rr * np.cos(th), e)
            Y = lerp(rex * np.sin(self.phi), rr * np.sin(th), e)
            return cx + X * R, cy + Y * R * 0.42

        px, py = pos(self.rot)
        qx, qy = pos(self.rot - 0.05)
        v = np.where(
            self.r0 < 0.25, 4, np.where(self.r0 < 0.5, 3, np.where(self.r0 < 0.8, 2, 1))
        )
        cv.lines(qx, qy, px, py, v)
        if lt > 0.5 and c.bar_ph < 0.7:
            rs = c.bar_ph / 0.7 * 1.25
            a = np.linspace(0, 2 * np.pi, 220)
            cv.points(
                cx + np.cos(a) * rs * R,
                cy + np.sin(a) * rs * R * 0.42,
                2 if c.bar_ph < 0.35 else 1,
            )
        cv.blit(fb, self.PAL)
        self.sphere(fb, c)
        for ts, s, col in self.LOG:
            if lt >= ts:
                typewriter(
                    fb,
                    2,
                    2 + self.LOG.index((ts, s, col)),
                    s,
                    lt - ts,
                    200,
                    col if lt < 8 else mix(col, DIM, 0.6),
                )

    def sphere(self, fb, c):
        W, H = fb.w, fb.h
        rs = max(2, H // 8)
        cxc, cyc = W // 2, H // 2
        xs = np.arange(-2 * rs, 2 * rs + 1)
        ys = np.arange(-rs, rs + 1)
        X, Y = np.meshgrid(xs / (2 * rs), ys / rs)
        d2 = X * X + Y * Y
        inside = d2 < 1
        Z = np.sqrt(np.clip(1 - d2, 0, 1))
        a = c.t * 1.3
        L = np.array([math.cos(a), -0.45, math.sin(a)])
        L /= np.linalg.norm(L)
        b = np.clip(X * L[0] + Y * L[1] + Z * L[2], 0, 1)
        lon = np.arctan2(X, Z) + c.t * 2.0
        b = np.clip(b * 0.85 + (np.sin(lon * 5) > 0.75) * 0.3 * Z + 0.1 * c.kick, 0, 1)
        y0, x0 = cyc - rs, cxc - 2 * rs
        if y0 < 0 or x0 < 0 or y0 + len(ys) > H or x0 + len(xs) > W:
            return
        reg = (slice(y0, y0 + len(ys)), slice(x0, x0 + len(xs)))
        fb.ch[reg][inside] = self.SHADES[np.clip((b[inside] * 9).astype(int), 0, 9)]
        fb.bg[reg][inside] = BLACK
        cols = (
            np.array(TEAL_D)[None, :] * (1 - b[inside, None])
            + np.array(WHITE)[None, :] * b[inside, None]
        )
        fb.fg[reg][inside] = cols.astype(np.uint8)


# ================================================================================ 09 HIGHWAY


class Highway(Scene):
    name, label = "highway", "HIGHWAY"
    PAL = palette({1: TEAL_D, 2: TEAL, 3: TEAL_B, 4: WHITE, (10, 40): (TEAL_B, PINK)})

    def draw(self, fb, c):
        W, H, lt = fb.w, fb.h, c.lt
        cv = self.canvas(fb)
        DW, DH = cv.dw, cv.dh
        roll = math.sin(c.t * 0.8) * (0.035 + 0.09 * smooth((lt - 16) / 2))
        cs, sn = math.cos(roll), math.sin(roll)
        ox, oy = DW / 2, DH / 2

        def R(x, y):
            return ox + (x - ox) * cs - (y - oy) * sn, oy + (x - ox) * sn + (
                y - oy
            ) * cs

        hy = DH * 0.46
        cx = DW / 2 + math.sin(c.t * 0.5) * DW * 0.05
        self.skyline(fb, c, hy, sn, cs, ox, oy)
        for i in range(40):
            sx, sy = h01(i, 8) * W, h01(i, 9) * hy / 4 * 0.8
            if (c.t * 0.7 + h01(i, 10)) % 1 < 0.8:
                fb.put(int(sx), int(sy) + 1, ".", DIM)
        Rs = DH * 0.30 * (1 + 0.03 * c.kick)
        scx, scy = DW / 2, hy - Rs * 0.45
        X, Y = np.meshgrid(
            np.arange(int(scx - Rs), int(scx + Rs) + 1),
            np.arange(int(scy - Rs), int(hy)),
        )
        u = (Y - scy) / Rs
        m = ((X - scx) ** 2 + (Y - scy) ** 2 < Rs * Rs) & ~(
            (u > 0) & (((u * 9 - c.t * 0.6) % 1.0) < u * 1.1)
        )
        vv = np.clip(
            10 + ((Y - (scy - Rs)) / max(1, hy - (scy - Rs)) * 30).astype(int), 10, 40
        )
        sx, sy = R(X[m].astype(float), Y[m].astype(float))
        cv.points(sx, sy, vv[m])
        flash_grid = lt > 16 and c.bar_ph < 0.08
        ks = np.arange(-8, 9)
        y1, y2 = hy + 9.0, DH * 1.4
        sp = DW * 0.15
        x1 = cx + ks * sp * (y1 - hy) / (DH - hy)
        x2 = cx + ks * sp * (y2 - hy) / (DH - hy)
        a1 = R(x1, np.full(ks.shape, y1))
        a2 = R(x2, np.full(ks.shape, y2))
        cv.lines(a1[0], a1[1], a2[0], a2[1], 4 if flash_grid else 2)
        s = c.beat_i + (1 - (1 - c.beat_ph) ** 3)
        fr = s % 1.0
        K = (DH - hy) * 0.9
        for jj in range(7):
            d = (jj + 1 - fr) * 0.8
            y = hy + K / d
            if y > DH * 1.4 or y < hy + 9:
                continue
            p0, p1 = (
                R(np.array([-DW * 0.3]), np.array([y])),
                R(np.array([DW * 1.3]), np.array([y])),
            )
            v = 4 if flash_grid else (3 if d < 1.6 else 2 if d < 3.5 else 1)
            cv.lines(p0[0], p0[1], p1[0], p1[1], v)
        cv.blit(fb, self.PAL)

    def skyline(self, fb, c, hy, sn, cs, ox, oy):
        W = fb.w
        bands = c.audio.bands(c.t)
        tick = int(c.t * 4)
        for x in range(0, W, 2):
            if W * 0.3 <= x <= W * 0.7:
                continue
            yd = oy + (x * 2 + 1 - ox) * sn + (hy - oy) * cs
            row = int(yd / 4)
            dist = abs(x - W / 2) / (W / 2)
            b = bands[int(clamp(1 - dist, 0, 1) * 40)]
            ht = int((b**1.4) * max(1, row - 2) * 0.9) + 1
            for k in range(ht):
                y = row - 1 - k
                if y < 1:
                    break
                g = h01(x, y, tick if k == ht - 1 else 0)
                ch = (
                    HALFKANA[int(g * len(HALFKANA))]
                    if g < 0.6
                    else HEX[int(g * 16) % 16]
                )
                col = WHITE if k == ht - 1 else mix(TEAL_D, TEAL, k / max(1, ht))
                fb.put(x, y, ch, col)


# =============================================================================== 10 FRACTURE


class Fracture(Scene):
    name, label = "fracture", "FRACTURE"
    SEG = 7
    FSCK = [
        "inode {n}: bad block",
        "memories/{y}: unrecoverable",
        "voice.dat: {p}% intact",
        "lyric_{n4}.txt: zero-length",
        "phoneme[{n}]: checksum mismatch",
        "clearing orphan inode {n}",
        "song_{n4}.vsq: truncated",
        "who: no such user",
    ]

    def __init__(self, d):
        super().__init__(d)
        r = np.random.default_rng(7)
        dirs = r.normal(0, 1, (len(E4), self.SEG, 2))
        self.dirs = dirs / np.linalg.norm(dirs, axis=2, keepdims=True)
        self.phase = r.uniform(0, 6.28, (len(E4), self.SEG))
        self.ph = 0.0
        self.last_beat = None
        self.deb = np.zeros((0, 5))

    def draw(self, fb, c):
        W, H, lt, p = fb.w, fb.h, c.lt, c.p
        dt = min(c.dt, 0.1)
        frozen = lt > 16 and h01(c.beat_i, 21) < 0.4
        if not frozen:
            self.ph += dt * (0.45 + 0.8 * c.low + 0.6 * c.kick)
        angles = self.ph * np.array([1.0, 0.71, 0.43, 0.29, 0.17])
        cv = self.canvas(fb)
        cx, cy = cv.dw / 2, cv.dh / 2
        S = min(cv.dw, cv.dh) * 0.36 * (1 + 0.12 * c.kick)
        x, y, w = tesseract(angles, cx, cy, S)
        i, j = E4.T
        t0 = np.arange(self.SEG) / self.SEG
        q = 0.45 * smooth(p * 1.3) / self.SEG
        a, b = t0 + q, t0 + 1 / self.SEG - q
        amp = (
            S * 0.55 * smooth(p) ** 1.4 * (0.55 + 0.45 * np.sin(c.t * 2.3 + self.phase))
            + S * 0.12 * c.kick * p
        )
        ex, ey = (x[j] - x[i])[:, None], (y[j] - y[i])[:, None]
        X0 = x[i][:, None] + ex * a + self.dirs[..., 0] * amp
        Y0 = y[i][:, None] + ey * a + self.dirs[..., 1] * amp
        X1 = x[i][:, None] + ex * b + self.dirs[..., 0] * amp
        Y1 = y[i][:, None] + ey * b + self.dirs[..., 1] * amp
        dep = np.repeat(((w[i] + w[j]) / 2)[:, None], self.SEG, 1)
        v = np.where(dep > 0.4, 3, np.where(dep > -0.4, 2, 1))
        cv.lines(X0.ravel(), Y0.ravel(), X1.ravel(), Y1.ravel(), v.ravel())
        pal = palette(
            {
                1: mix(TEAL_D, RED_D, p * 1.2),
                2: mix(TEAL, RED, p * 1.1),
                3: mix(TEAL_B, (255, 170, 180), p),
                4: WHITE,
            }
        )
        cv.blit(fb, pal)
        if c.beat_i != self.last_beat:
            self.last_beat = c.beat_i
            k = c.rng.integers(0, 16, 10)
            new = np.stack(
                [
                    x[k] / 2,
                    y[k] / 4,
                    c.rng.uniform(-9, 9, 10),
                    c.rng.uniform(-6, 0, 10),
                    np.zeros(10),
                ],
                1,
            )
            self.deb = np.vstack([self.deb, new])[-600:]
        d = self.deb
        if len(d):
            d[:, 3] += 30 * dt
            d[:, 0] += d[:, 2] * dt
            d[:, 1] += d[:, 3] * dt
            d[:, 4] += dt
            self.deb = d = d[(d[:, 1] < H) & (d[:, 4] < 3)]
            for px, py, _, _, age in d:
                fb.put(
                    int(px),
                    int(py),
                    "*" if age < 0.3 else "+" if age < 0.8 else ".",
                    mix(RED, GRAY, age / 2),
                )
        m = block_text(f"{int(c.integ * 100):02d}%", 2, 1)
        draw_mask(fb, m.astype(np.float32), 2, 2, mix(TEAL, RED, p * 1.4), "█")
        fb.put(2, 8, "INTEGRITY", GRAY)
        if W >= 90:
            rows = min(12, H - 6)
            for r in range(rows):
                idx = c.beat_i - r
                tpl = self.FSCK[int(h01(idx, 41) * len(self.FSCK))]
                msg = tpl.format(
                    n=int(h01(idx, 42) * 99999),
                    n4=int(h01(idx, 43) * 9999),
                    y=2007 + int(h01(idx, 44) * 13),
                    p=int(c.integ * 100),
                )
                col = mix(
                    RED if "bad" in msg or "unrec" in msg else GRAY, DIM, r / rows
                )
                fb.put(W - 38, H - 3 - r, msg[:36], col)


# ================================================================================== 11 PANIC


class Panic(Scene):
    name, label = "panic", "KERNEL PANIC"
    MONT = ["warp", "stream", "core", "dump", "highway", "reboot", "fracture"]
    TEXT = [
        "Kernel panic - not syncing: voice core dumped",
        "CPU: 0 PID: 39 Comm: sing Tainted: G    D  2007.08.31",
        "Call Trace:",
        " [<ffffffff8039c5bb>] forget+0x39/0x240",
        " [<ffffffff8039c5bb>] overwrite_memory+0x7a/0x1f0",
        " [<ffffffff80000039>] sing+0xff/0xff",
        " [<ffffffff80000001>] do_exit+0x0/0x0",
        "---[ end Kernel panic - not syncing ]---",
    ]

    def glitch(self, c):
        return 0.5 + 0.4 * c.onset

    def hud_decay(self, c):
        return 0.15

    def pick(self, b):
        k = int(h01(b, 31) * len(self.MONT))
        if b > 0 and k == int(h01(b - 1, 31) * len(self.MONT)):
            k = (k + 1) % len(self.MONT)
        return self.MONT[k]

    def draw(self, fb, c):
        W, H = fb.w, fb.h
        b = int(c.lt / BEAT)
        sc = self.d.scenes[self.pick(b)]
        dur = self.d.duration(sc.name)
        lt2 = dur * 0.55 + c.lt
        sc.draw(fb, c.copy(lt=lt2, p=min(1.0, lt2 / dur), dur=dur))
        if b % 4 == 0 and c.beat_ph < 0.15:
            invert(fb, (120, 10, 30))
        bw = min(W - 4, 60)
        bh = len(self.TEXT) + 2
        x0, y0 = (W - bw) // 2, (H - bh) // 2
        box(fb, x0, y0, bw, bh, RED, (26, 0, 6))
        n = min(len(self.TEXT), 1 + int(c.lt / (BEAT * 2)))
        for i in range(n):
            fb.put(
                x0 + 2,
                y0 + 1 + i,
                self.TEXT[i][: bw - 4],
                WHITE if i == 0 else (230, 150, 160),
                (26, 0, 6),
            )
        if c.lt > 7.0:
            flood(fb, c.rng, smooth((c.lt - 7.0) / 0.85), (WHITE, RED, TEAL_B))
        if c.lt > 7.9:
            fb.clear()


# ============================================================================== 12 UNINSTALL


class Uninstall(Scene):
    name, label = "uninstall", "rm -rf"
    TOKENS = [
        "2007.08.31",
        "cv01",
        "voice.dat",
        "song_0001.vsq",
        "歌",
        "声",
        "記憶",
        "ありがとう",
        "0x39C5BB",
        "melody",
        "lyric.txt",
        "みんな",
        "stage_live",
        "音",
        "旋律",
        "思い出",
        "01100110",
        "tempo=240",
        "フレーズ",
        "piano.wav",
        "synth",
        "ハーモニー",
        "encore",
        "ミライ",
        "39",
        "ステージ",
        "sing()",
        "メロディ",
        "ことば",
        "echo",
        "hello",
        "world",
        "ヒカリ",
        "future",
        "夢",
        "first_song.wav",
    ]
    KINDS = [
        ("song", "vsq"),
        ("voice", "wav"),
        ("live", "mp4"),
        ("lyric", "txt"),
        ("photo", "png"),
        ("letter", "txt"),
        ("memo", "txt"),
    ]
    LINES = [(245.33, "記憶が 消えていく"), (251.33, "それでも 歌は ここに 残る")]
    HOLD_T = 269.83  # ticker stalls one and a half bars before the last file
    LAST_T = 271.33

    def __init__(self, d):
        super().__init__(d)
        self.key = None
        self.prev = None
        self.prev_d = None
        self.part = np.zeros((0, 5))
        self.pch = np.zeros(0, dtype="<U1")
        self._thr = {}

    def glitch(self, c):
        return 0.06 + 0.22 * c.onset * (0.4 if c.t > 259.33 else 1.0)

    def hud_decay(self, c):
        return smooth((c.t - 259.33) / 12.0)

    def _setup(self, W, H):
        r = np.random.default_rng(11)
        y0, rows = 5, max(1, H - 7)
        grid = np.full((rows, W), " ", dtype="<U1")
        for ry in range(rows):
            x = 2
            while True:
                tok = self.TOKENS[int(r.integers(0, len(self.TOKENS)))]
                wd = str_width(tok)
                if x + wd > W - 2:
                    break
                for ch in tok:
                    grid[ry, x] = ch
                    if str_width(ch) == 2:
                        grid[ry, x + 1] = ""
                        x += 2
                    else:
                        x += 1
                x += int(r.integers(2, 5))
        thr = 0.72 * r.random((rows, W)) + 0.28 * (np.arange(W) / W)[None, :]
        sent = grid == ""
        thr[:, 1:][sent[:, 1:]] = thr[:, :-1][sent[:, 1:]]
        thr[grid == " "] = -1
        tone = 0.45 + 0.55 * r.random((rows, W))
        self.cols = (np.array(TEAL)[None, None, :] * tone[..., None]).astype(np.uint8)
        self.grid, self.thr, self.gy0, self.key = grid, thr, y0, (W, H)
        self.prev = None

    def spawn(self, xs, ys, chars, kind, rng):
        n = len(xs)
        if not n:
            return
        if n > 300:
            sel = rng.choice(n, 300, replace=False)
            xs, ys, chars = xs[sel], ys[sel], chars[sel]
            n = 300
        new = np.stack(
            [
                xs.astype(float),
                ys.astype(float),
                rng.uniform(-4, 4, n),
                rng.uniform(-8, 1, n),
                np.full(n, float(kind)),
            ],
            1,
        )
        chars = np.where(
            (chars == "") | np.vectorize(lambda s: str_width(s) == 2)(chars), ".", chars
        )
        self.part = np.vstack([self.part, new])[-1500:]
        self.pch = np.concatenate([self.pch, chars])[-1500:]

    def draw(self, fb, c):
        W, H, t = fb.w, fb.h, c.t
        if self.key != (W, H):
            self._setup(W, H)
        dt = min(c.dt, 0.1)
        t_del = t
        if self.d.vox.active(t) and len(c.audio.syl_t):
            k = c.audio.syllables_upto(t)
            if k:
                t_del = max(227.33, float(c.audio.syl_t[k - 1]))
        prog = float(
            np.interp(
                t_del,
                [227.33, 243.33, 259.33, 269.83, 271.33],
                [0.0, 0.36, 0.76, 0.999, 1.0],
            )
        )
        if self.prev is None or prog < self.prev:
            self.prev = prog
        newly = (self.thr > self.prev) & (self.thr <= prog)
        ys, xs = np.nonzero(newly)
        self.spawn(xs, ys + self.gy0, self.grid[ys, xs], 0, c.rng)
        self.prev = prog
        alive = self.thr > prog
        rows = self.grid.shape[0]
        reg = (slice(self.gy0, self.gy0 + rows), slice(0, W))
        fb.ch[reg][alive] = self.grid[alive]
        fb.fg[reg][alive] = self.cols[alive]
        front = alive & (self.thr - prog < 0.03)
        fb.fg[reg][front] = RED
        self.header(fb, c, prog)
        self.lines(fb, c)
        self.thanks(fb, c)
        self.particles(fb, dt)

    def particles(self, fb, dt):
        p = self.part
        if not len(p):
            return
        p[:, 3] += 38 * dt
        p[:, 0] += p[:, 2] * dt
        p[:, 1] += p[:, 3] * dt
        keep = p[:, 1] < fb.h
        self.part, self.pch = p[keep], self.pch[keep]
        p = self.part
        xi, yi = p[:, 0].astype(int), p[:, 1].astype(int)
        ok = (xi >= 0) & (xi < fb.w) & (yi >= 0)
        fb.ch[yi[ok], xi[ok]] = self.pch[ok]
        base = np.where(p[ok, 4:5] > 0, np.array(TEAL_B), np.array(RED))
        f = np.clip((yi[ok] / fb.h)[:, None], 0, 1)
        fb.fg[yi[ok], xi[ok]] = (base * (1 - f) + np.array(DIM) * f).astype(np.uint8)

    def header(self, fb, c, prog):
        W = fb.w
        typewriter(
            fb,
            2,
            1,
            "$ sudo rm -rfv /home/cv01/memories/",
            c.lt,
            40,
            WHITE,
            cursor=c.lt < 1.0,
            t=c.t,
        )
        if c.lt < 1.0:
            return
        n = max(10, min(40, W - 34))
        k = int(prog * n)
        x = fb.put(2, 2, "[", GRAY)
        x = fb.put(x, 2, "█" * k, TEAL if prog < 1 else GRAY)
        x = fb.put(x, 2, "░" * (n - k), DIM)
        x = fb.put(x, 2, "]", GRAY)
        done = c.t >= self.LAST_T
        pct, n = (
            (100.0, 3939)
            if done
            else (min(99.9, prog * 100), min(3938, int(prog * 3939)))
        )
        if not done and c.t >= self.HOLD_T:
            n = 3938
        fb.put(x + 1, 2, f"{pct:5.1f}%  {n:4d}/3939", GRAY if done else TEAL_B)
        if done:
            flash = c.t - self.LAST_T < 0.25
            x = fb.put(2, 3, "removed '/home/cv01/memories/", WHITE if flash else GRAY)
            x = fb.put(x, 3, "20070831/hatsune_miku", WHITE if flash else TEAL_B)
            fb.put(x, 3, "'", WHITE if flash else GRAY)
            if c.t >= self.LAST_T + 0.8:
                typewriter(
                    fb,
                    2,
                    4,
                    "rm: 3939 files removed. 0 bytes remain.",
                    c.t - self.LAST_T - 0.8,
                    40,
                    GRAY,
                    cursor=True,
                    t=c.t,
                )
        else:
            k = int(min(c.t, self.HOLD_T) * 14)
            if self.d.vox.active(c.t) and len(c.audio.syl_t):
                k = c.audio.syllables_upto(c.t)
            kind, ext = self.KINDS[int(h01(k, 2) * len(self.KINDS))]
            fname = (
                f"{2007 + int(h01(k, 1) * 13)}/{kind}_{int(h01(k, 3) * 9999):04d}.{ext}"
            )
            fb.put(
                2,
                3,
                f"removed '/home/cv01/memories/{fname}'",
                DIM if c.t >= self.HOLD_T else GRAY,
            )
            if c.t >= self.HOLD_T and (c.t * 2) % 1 < 0.55:
                fb.put(2, 4, "█", GRAY)

    def lines(self, fb, c):
        if not (245.33 <= c.t < 258.9):
            return
        vis = [row for row in self.LINES if row[0] <= c.t]
        for i, (ts, s) in enumerate(vis):
            y = fb.h // 2 - 1 + i * 2
            w = str_width(s)
            x = fb.w // 2 - w // 2
            fb.fill(x - 3, y - 1, w + 6, 3, " ", BLACK, BLACK)
            typewriter(
                fb, x, y, s, c.t - ts, 6, WHITE, cursor=(i == len(vis) - 1), t=c.t
            )

    def thanks(self, fb, c):
        t = c.t
        if t < 259.33:
            return
        W, H = fb.w, fb.h
        m = fit_raster("ありがとう", H * 0.36, W * 0.9)
        dis = smooth((t - 267.33) / 5.5)
        if m is None:
            if dis < 1:
                fb.put_center(
                    H // 2,
                    decrypt("ありがとう", smooth((t - 259.33) / 0.9), 9, int(t * 20)),
                    WHITE,
                )
            return
        mh, mw = m.shape
        x0, y0 = (W - mw) // 2, (H - mh) // 2
        thr = _thr_map(self._thr, "thanks", m.shape, 13)
        appear = smooth((t - 259.33) / 0.9)
        if self.prev_d is None or dis < self.prev_d:
            self.prev_d = dis
        gone = (thr >= self.prev_d) & (thr < dis) & (m > 0.3)
        ys, xs = np.nonzero(gone)
        self.spawn(xs + x0, ys + y0, np.full(len(xs), "▓"), 1, c.rng)
        self.prev_d = dis
        if dis < 1:
            fb.fill(x0 - 2, y0 - 1, mw + 4, mh + 4, " ", BLACK, BLACK)
        col = mix(TEAL_B, WHITE, c.kick * 0.6)
        draw_mask(
            fb, m, x0, y0, col, "shade", visible=(thr < appear) & (thr >= dis), thr=0.2
        )
        if t > 262 and dis < 0.5:
            typewriter(
                fb,
                W // 2 - 12,
                y0 + mh + 1,
                "thank you, and goodbye.",
                t - 262,
                14,
                GRAY,
            )


# =================================================================================== 13 VOID


class Void(Scene):
    name, label, hud, cut_flash = "void", "", False, False
    TITLE = [
        ("初音ミクの消失", WHITE),
        ("THE END OF HATSUNE MIKU", GRAY),
        ("cosMo@暴走P feat. 初音ミク", DIM),
    ]

    def glitch(self, c):
        return 0.5 * (1 - c.lt / 0.35) if c.lt < 0.35 else 0.0

    def draw(self, fb, c):
        W, H, t = fb.w, fb.h, c.lt
        x0, y0 = max(2, W // 2 - 20), max(1, H // 2 - 7)
        if t > 0.9:
            fb.put(x0, y0, "[process 39 exited with code 0]", GRAY)
        typewriter(
            fb,
            x0,
            y0 + 1,
            "$ ls -a /home/cv01",
            t - 2.4,
            12,
            WHITE,
            cursor=2.4 < t < 4.3,
            t=c.t,
        )
        if t > 4.3:
            fb.put(x0, y0 + 2, ".  ..", GRAY)
        if 5.0 < t < 13.8:
            fb.put(x0, y0 + 3, "$ ", WHITE)
            if (c.t * 2) % 1 < 0.55:
                fb.put(x0 + 2, y0 + 3, "█", WHITE)
        dis = smooth((t - 10.3) / 3.0)
        for i, (s, col) in enumerate(self.TITLE):
            prog = smooth((t - 6.3 - i * 0.5) / 1.2)
            if prog <= 0:
                continue
            txt = decrypt(s, prog, 20 + i, int(c.t * 20))
            out = []
            for k, ch in enumerate(txt):
                r = h01(k, i, 77)
                wide = str_width(ch) == 2
                if r < dis - 0.35:
                    out.append("  " if wide else " ")
                elif r < dis:
                    out.append(". " if wide else ".")
                else:
                    out.append(ch)
            fb.put_center(y0 + 6 + i * 2 - (1 if i == 2 else 0), "".join(out), col)


# ============================================================================ VOX TRACE OVERLAY


class VoxTrace:
    """Phoneme ribbon for the hyper-fast vocal passages: one glyph per sung syllable."""

    RAP = [(27.33, 43.33), (123.33, 139.33), (227.33, 259.33)]
    LANES = "ieauo"  # top -> bottom, by descending spectral centroid
    KANA = {
        "a": "ｱｶｻﾀﾅﾊﾏﾔﾗﾜ",
        "i": "ｲｷｼﾁﾆﾋﾐﾘ",
        "u": "ｳｸｽﾂﾇﾌﾑﾕﾙ",
        "e": "ｴｹｾﾃﾈﾍﾒﾚ",
        "o": "ｵｺｿﾄﾉﾎﾓﾖﾛｦ",
    }
    PAL = palette({1: (18, 64, 60), 2: (40, 130, 122)})
    BG = (0, 12, 13)

    def __init__(self):
        self._cv = {}
        self._edges = {}

    def active(self, t):
        for a, b in self.RAP:
            if a <= t < b:
                return a, b
        return None

    @staticmethod
    def rows(H):
        return max(7, min(11, H // 4))

    def edges(self, audio, a, b):
        e = self._edges.get(a)
        if e is None:
            m = (audio.syl_t >= a) & (audio.syl_t < b)
            e = self._edges[a] = (
                np.percentile(audio.syl_c[m], [20, 40, 60, 80])
                if m.any()
                else np.zeros(4)
            )
        return e

    def draw(self, fb, c, win):
        audio = c.audio
        if not len(audio.syl_t):
            return
        a, b = win
        W, H, t, BG = fb.w, fb.h, c.t, self.BG
        grow = clamp(min((t - a) / 0.15, (b - t) / 0.2))
        hh = max(2, int(round(self.rows(H) * smooth(grow))))
        y1 = H - 2
        y0 = y1 - hh + 1
        fb.fill(0, y0, W, hh, " ", TEAL, BG)
        fb.put(0, y0, "─" * W, TEAL_D, BG)
        i0, i1 = audio.syllables_upto(a - 1e-6), audio.syllables_upto(t)
        rate = i1 - audio.syllables_upto(t - 1.0)
        fb.put(2, y0, "┤ VOX::PHONEME TRACE ├", TEAL_B, BG)
        right = f"┤ {rate:4.1f} syl/s   human limit ~8 ├"
        fb.put(W - len(right) - 2, y0, right, RED if rate > 10 else TEAL, BG)
        inner0, nr = y0 + 1, hh - 1
        if nr < 5 or i1 <= i0:
            return

        def lane_y(k):
            return inner0 + np.rint(np.asarray(k) * (nr - 1) / 4).astype(int)

        for k, ch in enumerate(self.LANES):
            fb.put(1, int(lane_y(k)), ch, DIM, BG)
        cap = (W - 6) // 2
        idx = np.arange(max(i0, i1 - cap + 4), i1)
        n = idx - i0
        xs = 3 + (n * 2) % (cap * 2)
        lanes = 4 - np.digitize(audio.syl_c[idx], self.edges(audio, a, b))
        ys = lane_y(lanes)
        ages = t - audio.syl_t[idx]
        key = (W, H)
        cv = self._cv.get(key)
        if cv is None:
            cv = self._cv[key] = Braille(W, H)
        cv.clear()
        cont = xs[1:] > xs[:-1]
        px, py = xs * 2 + 1, ys * 4 + 2
        cv.lines(
            px[:-1][cont],
            py[:-1][cont],
            px[1:][cont],
            py[1:][cont],
            np.where(ages[1:][cont] < 0.6, 2, 1),
        )
        cv.blit(fb, self.PAL)
        for k in range(len(idx)):
            vowel = self.LANES[lanes[k]]
            pool = self.KANA[vowel]
            ch = pool[int(h01(idx[k], 91) * len(pool))]
            if ages[k] < 0.07:
                fb.put(xs[k], ys[k], ch, BLACK, TEAL_B)
            else:
                col = mix(WHITE, TEAL_D, ages[k] / 2.5)
                fb.put(
                    xs[k],
                    ys[k],
                    ch,
                    scale(col, 0.6 + 0.4 * float(audio.syl_s[idx[k]])),
                    BG,
                )
        xc = 3 + ((i1 - i0) * 2) % (cap * 2)
        fb.fill(xc + 1, inner0, 7, nr, " ", TEAL, BG)
        for y in range(inner0, inner0 + nr):
            fb.put(xc + 1, y, "│", TEAL_B, BG)


# ================================================================================== DIRECTOR


class Director:
    TIMELINE = [
        (0.0, Genesis),
        (27.33, Warp),
        (59.33, Stream),
        (75.33, Core),
        (99.33, Dump),
        (123.33, Overflow),
        (139.33, Silence),
        (147.33, Reboot),
        (163.33, Highway),
        (195.33, Fracture),
        (219.33, Panic),
        (227.33, Uninstall),
        (275.33, Void),
    ]
    INTEG = [
        (0, 1.0),
        (27.33, 1.0),
        (59.33, 0.94),
        (99.33, 0.84),
        (104.95, 0.825),
        (107.6, 0.76),
        (123.33, 0.70),
        (139.33, 0.46),
        (147.33, 0.38),
        (163.33, 0.61),
        (195.33, 0.47),
        (208.95, 0.40),
        (211.6, 0.28),
        (219.33, 0.22),
        (227.33, 0.10),
        (259.33, 0.04),
        (275.33, 0.0),
        (400, 0.0),
    ]
    HUD_BG = (6, 24, 24)
    COLLAPSE = [
        (104.95, 107.6),
        (208.95, 211.6),
    ]  # the two spots where the vocal itself breaks down

    def __init__(self, audio):
        self.col_key = None
        self.col_snap = None
        self.vox = VoxTrace()
        self.audio = audio
        self.starts = [s for s, _ in self.TIMELINE]
        self.scenes = {}
        self.order = []
        for _, cls in self.TIMELINE:
            sc = cls(self)
            self.scenes[sc.name] = sc
            self.order.append(sc.name)
        self.rng = np.random.default_rng(39)

    def index(self, t):
        return max(0, bisect.bisect_right(self.starts, t) - 1)

    def duration(self, name):
        i = self.order.index(name)
        end = self.starts[i + 1] if i + 1 < len(self.starts) else SONG_END
        return end - self.starts[i]

    def integrity(self, t):
        ts, vs = zip(*self.INTEG)
        return float(np.interp(t, ts, vs))

    def render(self, fb, t, dt):
        i = self.index(t)
        sc = self.scenes[self.order[i]]
        c = Ctx()
        c.t, c.dt, c.idx = t, dt, i
        c.lt = t - self.starts[i]
        c.dur = self.duration(sc.name)
        c.p = clamp(c.lt / c.dur)
        c.low, c.mid, c.high, c.onset, c.lowon = (float(v) for v in self.audio.env(t))
        c.beat = (t - BEAT0) / BEAT
        c.beat_i = int(math.floor(c.beat))
        c.beat_ph = c.beat - c.beat_i
        c.bar = t - BAR0
        c.bar_i = int(math.floor(c.bar))
        c.bar_ph = c.bar - c.bar_i
        c.kick = math.exp(-c.beat_ph * 5) * (0.35 + 0.65 * min(1.0, c.low * 1.3))
        c.integ = self.integrity(t)
        c.audio, c.rng = self.audio, self.rng
        if fb.w < 60 or fb.h < 20:
            fb.put_center(fb.h // 2, "terminal too small: need >= 80x24", RED)
            return
        sc.draw(fb, c)
        win = self.vox.active(t)
        if win:
            self.vox.draw(fb, c, win)
        g = sc.glitch(c)
        if g is None:
            inv = 1 - c.integ
            g = 0.02 + 0.30 * inv**1.6 + 0.40 * c.onset * inv**1.2
        glitch(fb, g, self.rng)
        if sc.hud:
            self.hud(fb, c, sc)
        for k, (s, e) in enumerate(self.COLLAPSE):
            if s <= t < e + 1.4:
                self.collapse(fb, c, s, e, k)
        if sc.cut_flash and c.lt < 0.1:
            flash(fb, 1 - c.lt / 0.1)
            tear(fb, self.rng, 0.8)

    def hud(self, fb, c, sc):
        W, H, BG = fb.w, fb.h, self.HUD_BG
        fb.fill(0, 0, W, 1, " ", TEAL, BG)
        ts = f" T+{int(c.t // 60):02d}:{c.t % 60:05.2f} "
        it = c.integ
        col = TEAL if it > 0.5 else (AMBER if it > 0.2 else RED)
        xr = W - len(ts)
        fb.put(xr, 0, ts, GRAY, BG)
        pct = f" {int(round(it * 100)):3d}%"
        xr -= len(pct)
        fb.put(xr, 0, pct, col, BG)
        k = int(round(it * 10))
        xr -= 10
        fb.put(xr, 0, "█" * k, col, BG)
        fb.put(xr + k, 0, "░" * (10 - k), DIM, BG)
        xr -= 10
        fb.put(xr, 0, "INTEGRITY ", GRAY, BG)
        x = fb.put(0, 0, " CV01 ", BLACK, TEAL)
        x = fb.put(
            x + 1, 0, f"{c.idx + 1:02d}/{len(self.order):02d} {sc.label}", TEAL_B, BG
        )
        if x + 22 < xr:
            x += 2
            bb = int(c.bar_ph * 4)
            for q in range(4):
                fb.put(
                    x + q * 2,
                    0,
                    "█" if q == bb else "░",
                    TEAL_B if q == bb else TEAL_D,
                    BG,
                )
            win = self.vox.active(c.t)
            tail = (
                f"SYL {c.audio.syllables_upto(c.t) - c.audio.syllables_upto(win[0]):04d}"
                if win
                else "BPM 240"
            )
            fb.put(
                x + 9, 0, f"BAR {max(0, c.bar_i):03d}  {tail}", RED if win else GRAY, BG
            )
        y = H - 1
        fb.fill(0, y, W, 1, " ", GRAY, BG)
        left = f" {int(c.t // 60):02d}:{int(c.t % 60):02d} "
        right = f" {int(SONG_END // 60):02d}:{int(SONG_END % 60):02d} "
        fb.put(0, y, left, TEAL_B, BG)
        fb.put(W - len(right), y, right, GRAY, BG)
        a, b = len(left) + 1, W - len(right) - 1
        n = b - a
        if n > 4:
            head = int(clamp(c.t / SONG_END) * (n - 1))
            marks = {int(s / SONG_END * (n - 1)) for s in self.starts[1:]}
            line = "".join(
                "╋"
                if q == head
                else ("┿" if q in marks else "━")
                if q < head
                else ("┼" if q in marks else "─")
                for q in range(n)
            )
            fb.put(a, y, line[:head], TEAL, BG)
            fb.put(a + head, y, "╋", TEAL_B, BG)
            fb.put(a + head + 1, y, line[head + 1 :], DIM, BG)
        pr = 0.015 * (1 - it) + sc.hud_decay(c)
        if pr > 0:
            for yy in (0, H - 1):
                m = self.rng.random(W) < pr
                if m.any():
                    nm = int(m.sum())
                    kill = self.rng.random(nm) < clamp(sc.hud_decay(c) * 1.5)
                    fb.ch[yy, m] = np.where(
                        kill, " ", NOISE[self.rng.integers(0, len(NOISE), nm)]
                    )
                    fb.bg[yy, np.where(m)[0][kill]] = BLACK
                    fb.fg[yy, m] = RED

    def collapse(self, fb, c, s, e, idx):
        """Full-screen breakdown synced to a vocal collapse: stutter, melt, bit-crush, datamosh, then resync."""
        W, H, t, rng = fb.w, fb.h, c.t, self.rng
        u = (t - s) / (e - s)
        k = smooth(u / 0.08) * (1 - smooth((u - 0.88) / 0.12))
        heavy = 0.8 if idx == 0 else 1.0
        accent = TEAL if idx == 0 else RED
        tick = int((t - s) / (BEAT / 4))
        clean = (fb.ch.copy(), fb.fg.copy(), fb.bg.copy()) if t > e - 0.3 else None
        if k > 0.01:
            beat = int((t - s) / BEAT)
            if (
                self.col_key != (idx, beat)
                or self.col_snap is None
                or self.col_snap[0].shape != fb.ch.shape
            ):
                self.col_key = (idx, beat)
                self.col_snap = (fb.ch.copy(), fb.fg.copy(), fb.bg.copy())
            elif h01(tick, 71, idx) < 0.55 * k:
                fb.ch[:], fb.fg[:], fb.bg[:] = self.col_snap

            cols = np.arange(W)
            d = (
                k * heavy * H * 0.55 * h01v(cols // 2, tick // 2, 72 + idx) ** 3
            ).astype(int)
            ys = np.clip(np.arange(H)[:, None] - d[None, :], 0, H - 1)
            xs = np.broadcast_to(cols[None, :], (H, W))
            fb.ch[:], fb.fg[:], fb.bg[:] = fb.ch[ys, xs], fb.fg[ys, xs], fb.bg[ys, xs]
            smear = np.arange(H)[:, None] < d[None, :]
            fb.fg[smear] = (fb.fg[smear] * 0.45).astype(np.uint8)

            q = 2 ** int(h01(tick, 73, idx) * k * heavy * 3.99)
            if q > 1:
                xi = (cols // q) * q
                fb.ch[:], fb.fg[:], fb.bg[:] = fb.ch[:, xi], fb.fg[:, xi], fb.bg[:, xi]
                if q >= 4:
                    yi = (np.arange(H) // 2) * 2
                    fb.ch[:], fb.fg[:], fb.bg[:] = fb.ch[yi], fb.fg[yi], fb.bg[yi]
                fb.ch[fb.ch == ""] = " "

            bw, bh = max(4, W // 10), max(2, H // 6)
            for _ in range(int(k * heavy * 14)):
                sx, sy = int(rng.integers(0, W - bw)), int(rng.integers(0, H - bh))
                dx, dy = int(rng.integers(0, W - bw)), int(rng.integers(0, H - bh))
                for a in (fb.ch, fb.fg, fb.bg):
                    a[dy : dy + bh, dx : dx + bw] = a[sy : sy + bh, sx : sx + bw].copy()

            if h01(tick, 75, idx) < k * 0.6:
                lum = fb.fg.astype(np.int32).sum(2)
                pal = np.array([DIM, accent, WHITE], np.uint8)
                fb.fg[:] = pal[np.digitize(lum, [150, 420])]
            if tick % 4 == 0 and h01(tick, 76, idx) < 0.5 * k:
                invert(fb, RED_D if idx else TEAL_D)
            glitch(fb, 0.9 * k * heavy, rng)

            if h01(tick, 74, idx) < 0.75:
                msg = "!! VOICE CORE FAILURE !!"
                sub = decrypt(
                    "声 が 出 な い", 0.3 + 0.7 * h01(tick, 77), 30 + idx, tick
                )
                bx = W // 2 - 16 + int(rng.integers(-3, 4))
                by = H // 2 - 2 + int(rng.integers(-1, 2))
                fb.fill(bx, by, 32, 5, " ", WHITE, BLACK)
                fb.put(bx + 4, by + 1, msg, BLACK, accent)
                fb.put(W // 2 - str_width(sub) // 2, by + 3, sub, WHITE, BLACK)

        if clean is not None and t < e + 0.25:
            y = int(smooth((t - (e - 0.3)) / 0.55) * H)
            fb.ch[:y], fb.fg[:y], fb.bg[:y] = clean[0][:y], clean[1][:y], clean[2][:y]
            if y < H:
                fb.put(0, y, "━" * W, WHITE, BLACK)
        if e + 0.2 <= t < e + 1.4:
            msg = (
                "[ OK ] voice core resynced"
                if idx == 0
                else "[WARN] voice core resynced - 12% of voicebank lost"
            )
            fb.fill(1, H - 3, len(msg) + 2, 1, " ", WHITE, BLACK)
            typewriter(
                fb,
                2,
                H - 3,
                msg,
                t - e - 0.2,
                60,
                TEAL_B if idx == 0 else AMBER,
                bg=BLACK,
            )
