#!/usr/bin/env python3
"""Render the MV offline to a video file (default: 3840x2160 @ 30fps H.264 + original audio).

    python3 export.py                          # full 4K export -> miku_4k.mp4
    python3 export.py --preview 1:45.6         # write one PNG frame to check the look
    python3 export.py --start 1:40 --end 1:50  # export a clip
"""
import argparse
import os
import subprocess
import sys
import time
from collections import deque
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mv.engine import SONG_END, Audio, Frame, is_wide  # noqa: E402
from mv.scenes import Director  # noqa: E402
from play import find_audio, parse_time  # noqa: E402

FONT_ASCII = ('/System/Library/Fonts/Menlo.ttc', 0)
FONT_CJK = ('/System/Library/Fonts/Hiragino Sans GB.ttc', 1)
FONT_FALLBACK = ('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 0)

# (up, down, left, right) stroke weights: 1 = light, 2 = heavy
BOX = {'─': (0, 0, 1, 1), '━': (0, 0, 2, 2), '│': (1, 1, 0, 0), '┃': (2, 2, 0, 0), '┌': (0, 1, 0, 1),
       '┐': (0, 1, 1, 0), '└': (1, 0, 0, 1), '┘': (1, 0, 1, 0), '├': (1, 1, 0, 1), '┤': (1, 1, 1, 0),
       '┬': (0, 1, 1, 1), '┴': (1, 0, 1, 1), '┼': (1, 1, 1, 1), '┿': (1, 1, 2, 2), '╋': (2, 2, 2, 2),
       '╸': (0, 0, 2, 0), '╺': (0, 0, 0, 2), '╹': (2, 0, 0, 0), '╻': (0, 2, 0, 0)}
QUAD = {'▖': (0, 0, 1, 0), '▗': (0, 0, 0, 1), '▘': (1, 0, 0, 0), '▝': (0, 1, 0, 0), '▚': (1, 0, 0, 1),
        '▞': (0, 1, 1, 0), '▙': (1, 0, 1, 1), '▛': (1, 1, 1, 0), '▜': (1, 1, 0, 1), '▟': (0, 1, 1, 1)}


class Glyphs:
    """Per-process glyph atlas: char -> coverage mask(s) of one cell each (wide glyphs split in two)."""

    def __init__(self, cw, chh):
        from PIL import ImageFont
        self.cw, self.chh = cw, chh
        size = int(round(cw / 0.602))
        self.f_ascii = ImageFont.truetype(FONT_ASCII[0], size, index=FONT_ASCII[1])
        self.f_cjk = ImageFont.truetype(FONT_CJK[0], int(chh * 0.86), index=FONT_CJK[1])
        self.f_fb = ImageFont.truetype(FONT_FALLBACK[0], size, index=FONT_FALLBACK[1])
        from fontTools.ttLib import TTCollection, TTFont
        self.cmap_ascii = set(TTCollection(FONT_ASCII[0]).fonts[FONT_ASCII[1]].getBestCmap())
        self.cmap_cjk = set(TTCollection(FONT_CJK[0]).fonts[FONT_CJK[1]].getBestCmap())
        self.cmap_fb = set(TTFont(FONT_FALLBACK[0]).getBestCmap())
        self.masks = [np.zeros((chh, cw), np.float32)]
        self.index = {' ': (0, 0), '': (0, 0)}

    def get(self, c):
        r = self.index.get(c)
        if r is None:
            m = self._render(c)
            i = len(self.masks)
            if m.shape[1] > self.cw:
                self.masks += [m[:, :self.cw], m[:, self.cw:]]
                r = (i, i + 1)
            else:
                self.masks.append(m)
                r = (i, i)
            self.index[c] = r
        return r

    def atlas(self):
        return np.stack(self.masks)

    def _ss(self, draw_fn, w):
        """Draw at 4x supersampling into a boolean canvas, return anti-aliased coverage."""
        S = 4
        a = np.zeros((self.chh * S, w * S), bool)
        draw_fn(a, S)
        return a.reshape(self.chh, S, w, S).mean((1, 3)).astype(np.float32)

    def _render(self, c):
        cw, chh = self.cw, self.chh
        o = ord(c)
        if 0x2800 <= o <= 0x28FF:
            bits = o - 0x2800
            order = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]

            def fn(a, S):
                H, W = a.shape
                yy, xx = np.mgrid[0:H, 0:W]
                r = min(W / 4, H / 8) * 0.62
                for b, (dx, dy) in enumerate(order):
                    if bits >> b & 1:
                        cx, cy = W * (1 + 2 * dx) / 4, H * (1 + 2 * dy) / 8
                        a |= (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
            return self._ss(fn, cw)
        if c in BOX:
            return self._box(BOX[c])
        if c in QUAD:
            ul, ur, ll, lr = QUAD[c]
            m = np.zeros((chh, cw), np.float32)
            h2, w2 = chh // 2, cw // 2
            m[:h2, :w2], m[:h2, w2:], m[h2:, :w2], m[h2:, w2:] = ul, ur, ll, lr
            return m
        if c in '░▒▓':
            return np.full((chh, cw), {'░': 0.25, '▒': 0.5, '▓': 0.75}[c], np.float32)
        if c == '█':
            return np.ones((chh, cw), np.float32)
        if 0x2581 <= o <= 0x2587:
            m = np.zeros((chh, cw), np.float32)
            m[chh - int(round(chh * (o - 0x2580) / 8)):] = 1
            return m
        if c in '▀▔▌▐':
            m = np.zeros((chh, cw), np.float32)
            if c == '▀':
                m[:chh // 2] = 1
            elif c == '▔':
                m[:max(1, chh // 8)] = 1
            elif c == '▌':
                m[:, :cw // 2] = 1
            else:
                m[:, cw // 2:] = 1
            return m
        wide = is_wide(c)
        if o < 0x3000 and o in self.cmap_ascii and not wide:
            font = self.f_ascii
        elif o in self.cmap_cjk and wide:
            font = self.f_cjk
        elif o in self.cmap_fb:
            font = self.f_fb
        else:
            font = self.f_ascii
        return self._text(c, font, cw * (2 if wide else 1))

    def _text(self, c, font, w):
        from PIL import Image, ImageDraw
        asc, desc = font.getmetrics()
        img = Image.new('L', (w * 3, self.chh), 0)
        ImageDraw.Draw(img).text((w, (self.chh - asc - desc) // 2), c, font=font, fill=255)
        bb = img.getbbox()
        if bb is None:
            return np.zeros((self.chh, w), np.float32)
        adv = font.getlength(c)
        if adv > w * 1.05:
            gw = bb[2] - bb[0]
            crop = img.crop((bb[0], 0, bb[2], self.chh)).resize((min(w, gw), self.chh), Image.LANCZOS)
            img = Image.new('L', (w, self.chh), 0)
            img.paste(crop, ((w - crop.size[0]) // 2, 0))
        else:
            img = img.crop((w - int((w - adv) / 2), 0, w - int((w - adv) / 2) + w, self.chh))
        return np.asarray(img, np.float32) / 255.0

    def _box(self, spec):
        cw, chh = self.cw, self.chh
        m = np.zeros((chh, cw), np.float32)
        th = {1: max(2, cw // 10), 2: max(4, cw // 5)}
        cx, cy = cw // 2, chh // 2
        up, down, left, right = spec
        wv = max(up, down, 1)
        wh = max(left, right, 1)
        if up:
            t = th[up]
            m[:cy + th[wh] // 2 + 1, cx - t // 2:cx - t // 2 + t] = 1
        if down:
            t = th[down]
            m[cy - th[wh] // 2:, cx - t // 2:cx - t // 2 + t] = 1
        if left:
            t = th[left]
            m[cy - t // 2:cy - t // 2 + t, :cx + th[wv] // 2 + 1] = 1
        if right:
            t = th[right]
            m[cy - t // 2:cy - t // 2 + t, cx - th[wv] // 2:] = 1
        return m


_G = None


def _init(cw, chh):
    global _G
    _G = Glyphs(cw, chh)


def raster(args):
    ch, fg, bg = args
    G = _G
    H, W = ch.shape
    rows = ch.tolist()
    idx = np.zeros((H, W), np.int32)
    fg = fg.copy()
    for y in range(H):
        r = rows[y]
        x = 0
        while x < W:
            c = r[x]
            a, b = G.get(c)
            if a != b:
                if x + 1 < W:
                    idx[y, x], idx[y, x + 1] = a, b
                    fg[y, x + 1] = fg[y, x]
                x += 2
                continue
            idx[y, x] = a
            x += 1
    A = G.atlas()[idx]                                     # H, W, chh, cw
    f = fg.astype(np.float32)[:, :, None, None, :]
    b = bg.astype(np.float32)[:, :, None, None, :]
    img = b + A[..., None] * (f - b)
    img = img.transpose(0, 2, 1, 3, 4).reshape(H * G.chh, W * G.cw, 3)
    return np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes()


def frames(director, W, H, t0, n, fps):
    fb = Frame(W, H)
    for i in range(n):
        fb.clear()
        director.render(fb, t0 + i / fps, 1 / fps)
        yield fb.ch.copy(), fb.fg.copy(), fb.bg.copy()


def main():
    ap = argparse.ArgumentParser(description='Export the MV to video')
    ap.add_argument('--out', default=os.path.join(HERE, 'miku_4k.mp4'))
    ap.add_argument('--width', type=int, default=3840)
    ap.add_argument('--height', type=int, default=2160)
    ap.add_argument('--grid', default='128x36', help='terminal size in cells (must divide the resolution)')
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--start', default='0')
    ap.add_argument('--end', default=str(SONG_END))
    ap.add_argument('--crf', type=int, default=18)
    ap.add_argument('--preset', default='medium')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 4) - 3))
    ap.add_argument('--preview', help='render a single frame at time T to PNG and exit')
    args = ap.parse_args()

    W, H = (int(v) for v in args.grid.lower().split('x'))
    if args.width % W or args.height % H:
        sys.exit('grid must divide the resolution evenly')
    cw, chh = args.width // W, args.height // H
    path = find_audio(None)
    director = Director(Audio(path))

    if args.preview:
        from PIL import Image
        t = parse_time(args.preview)
        t0 = max(0.0, t - 2.0)
        n = int((t - t0) * args.fps) + 1
        last = None
        for last in frames(director, W, H, t0, n, args.fps):
            pass
        _init(cw, chh)
        img = np.frombuffer(raster(last), np.uint8).reshape(args.height, args.width, 3)
        out = os.path.splitext(args.out)[0] + f'_preview_{t:.2f}.png'
        Image.fromarray(img).save(out)
        print(out)
        return

    t0, t1 = parse_time(args.start), min(parse_time(args.end), SONG_END)
    n = int(round((t1 - t0) * args.fps))
    cmd = ['ffmpeg', '-v', 'error', '-y',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{args.width}x{args.height}', '-r', str(args.fps), '-i', '-']
    if path:
        cmd += ['-ss', f'{t0:.3f}', '-t', f'{t1 - t0:.3f}', '-i', path]
    cmd += ['-c:v', 'libx264', '-preset', args.preset, '-crf', str(args.crf), '-tune', 'animation',
            '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-level', '5.2', '-movflags', '+faststart']
    if path:
        cmd += ['-c:a', 'aac', '-b:a', '320k', '-shortest']
    cmd += [args.out]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    start = time.time()
    window = args.workers * 2
    with Pool(args.workers, initializer=_init, initargs=(cw, chh)) as pool:
        pending = deque()
        done = 0

        def drain(k):
            nonlocal done
            while len(pending) > k:
                enc.stdin.write(pending.popleft().get())
                done += 1
                if done % 150 == 0 or done == n:
                    el = time.time() - start
                    eta = el / done * (n - done)
                    print(f'  {done}/{n} frames  {done / el:5.1f} fps  elapsed {el / 60:4.1f}m  eta {eta / 60:4.1f}m',
                          flush=True)

        for item in frames(director, W, H, t0, n, args.fps):
            pending.append(pool.apply_async(raster, (item,)))
            drain(window)
        drain(0)
    enc.stdin.close()
    rc = enc.wait()
    print(f'done in {(time.time() - start) / 60:.1f} min -> {args.out}' if rc == 0 else f'ffmpeg failed ({rc})')


if __name__ == '__main__':
    main()
