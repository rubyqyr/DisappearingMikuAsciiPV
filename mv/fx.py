"""Reusable visual effects: big text, glitch passes, decrypt/typewriter text, boxes."""
from functools import lru_cache

import numpy as np

from .engine import (BLACK, DIM, GRAY, RED, RED_D, TEAL, TEAL_B, TEAL_D, WHITE, clamp, h01, is_wide,
                     str_width)

NOISE = np.array(list('░▒▓█▚▞▖▗▘▝#%&@$*+=/\\|<>01'), dtype='<U1')
HEX = '0123456789ABCDEF'
HALFKANA = 'ｦｧｨｩｪｫｬｭｮｯｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ'
WIDE_POOL = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン'
NARROW_POOL = '#$%&*+-/0123456789<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_{|}~'
SHADE = np.array(list(' ░▒▓█'), dtype='<U1')

_FONT_SRC = {
    'A': '.###.|#...#|#####|#...#|#...#', 'B': '####.|#...#|####.|#...#|####.',
    'C': '.####|#....|#....|#....|.####', 'D': '####.|#...#|#...#|#...#|####.',
    'E': '#####|#....|####.|#....|#####', 'F': '#####|#....|####.|#....|#....',
    'G': '.####|#....|#.###|#...#|.####', 'H': '#...#|#...#|#####|#...#|#...#',
    'I': '#####|..#..|..#..|..#..|#####', 'J': '..###|...#.|...#.|#..#.|.##..',
    'K': '#...#|#..#.|###..|#..#.|#...#', 'L': '#....|#....|#....|#....|#####',
    'M': '#...#|##.##|#.#.#|#...#|#...#', 'N': '#...#|##..#|#.#.#|#..##|#...#',
    'O': '.###.|#...#|#...#|#...#|.###.', 'P': '####.|#...#|####.|#....|#....',
    'Q': '.###.|#...#|#.#.#|#..#.|.##.#', 'R': '####.|#...#|####.|#..#.|#...#',
    'S': '.####|#....|.###.|....#|####.', 'T': '#####|..#..|..#..|..#..|..#..',
    'U': '#...#|#...#|#...#|#...#|.###.', 'V': '#...#|#...#|#...#|.#.#.|..#..',
    'W': '#...#|#...#|#.#.#|##.##|#...#', 'X': '#...#|.#.#.|..#..|.#.#.|#...#',
    'Y': '#...#|.#.#.|..#..|..#..|..#..', 'Z': '#####|...#.|..#..|.#...|#####',
    '0': '.###.|#..##|#.#.#|##..#|.###.', '1': '..#..|.##..|..#..|..#..|.###.',
    '2': '.###.|#...#|..##.|.#...|#####', '3': '####.|....#|.###.|....#|####.',
    '4': '#..#.|#..#.|#####|...#.|...#.', '5': '#####|#....|####.|....#|####.',
    '6': '.###.|#....|####.|#...#|.###.', '7': '#####|....#|...#.|..#..|..#..',
    '8': '.###.|#...#|.###.|#...#|.###.', '9': '.###.|#...#|.####|....#|.###.',
    ' ': '...|...|...|...|...', '-': '....|....|####|....|....', '.': '.|.|.|.|#',
    ':': '.|#|.|#|.', '/': '....#|...#.|..#..|.#...|#....', '_': '.....|.....|.....|.....|#####',
    '!': '#|#|#|.|#', '?': '.###.|#...#|..##.|.....|..#..', '%': '#...#|...#.|..#..|.#...|#...#',
    '>': '#...|.#..|..#.|.#..|#...', '<': '...#|..#.|.#..|..#.|...#', '@': '.###.|#.###|#.#.#|#.##.|.###.',
    '#': '.#.#.|#####|.#.#.|#####|.#.#.', '[': '##|#.|#.|#.|##', ']': '##|.#|.#|.#|##',
    '=': '....|####|....|####|....', '+': '.....|..#..|.###.|..#..|.....', '*': '#.#.#|.###.|#####|.###.|#.#.#',
}
FONT = {k: np.array([[c == '#' for c in row] for row in v.split('|')], bool) for k, v in _FONT_SRC.items()}


def block_text(text, sx=1, sy=1):
    """ASCII text -> bool mask using the 5-row block font, scaled by (sx, sy)."""
    cols = []
    for i, ch in enumerate(text.upper()):
        g = FONT.get(ch, FONT['?'])
        if i:
            cols.append(np.zeros((5, 1), bool))
        cols.append(g)
    m = np.hstack(cols) if cols else np.zeros((5, 1), bool)
    return np.repeat(np.repeat(m, sy, 0), sx, 1)


_FONT_PATHS = [
    '/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc',
    '/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc',
    '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    'C:/Windows/Fonts/msgothic.ttc',
]


@lru_cache(maxsize=4)
def _font(size):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for p in _FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return None


@lru_cache(maxsize=64)
def raster(text, rows):
    """Rasterise text (incl. CJK) into a coverage mask of `rows` terminal rows. None if unavailable."""
    rows = max(3, int(rows))
    if text.isascii():
        m = block_text(text, 1, 1).astype(np.float32)
        sy = max(1, rows // 5)
        return np.repeat(np.repeat(m, sy, 0), sy * 2, 1)
    font = _font(160)
    if font is None:
        return None
    from PIL import Image, ImageDraw
    l, t, r, b = font.getbbox(text)
    img = Image.new('L', (r - l + 16, b - t + 16), 0)
    ImageDraw.Draw(img).text((8 - l, 8 - t), text, font=font, fill=255)
    bb = img.getbbox()
    if bb is None:
        return None
    img = img.crop(bb)
    w, h = img.size
    cols = max(1, int(round(rows * (w / h) * 2.0)))
    small = img.resize((cols, rows), Image.BOX)
    return np.asarray(small, np.float32) / 255.0


def fit_raster(text, max_rows, max_cols):
    """Largest raster of `text` that fits in max_rows x max_cols."""
    rows = int(max_rows)
    while rows >= 3:
        m = raster(text, rows)
        if m is None:
            return None
        if m.shape[1] <= max_cols:
            return m
        rows -= 1
    return None


def draw_mask(fb, mask, x0, y0, color=TEAL_B, style='shade', rng=None, thr=0.18, visible=None, bg=None,
              clear_bg=False):
    """Stamp a coverage mask into the frame. style: shade | bits | hex | solid | <literal char>."""
    if mask is None:
        return
    h, w = mask.shape
    x0, y0 = int(x0), int(y0)
    ax, ay = max(0, -x0), max(0, -y0)
    bx, by = min(w, fb.w - x0), min(h, fb.h - y0)
    if ax >= bx or ay >= by:
        return
    m = mask[ay:by, ax:bx]
    on = m > thr
    if visible is not None:
        on &= visible[ay:by, ax:bx]
    region = (slice(y0 + ay, y0 + by), slice(x0 + ax, x0 + bx))
    if clear_bg:
        fb.ch[region][on] = ' '
    n = int(on.sum())
    if n == 0:
        return
    rng = rng or np.random.default_rng()
    if style == 'shade':
        idx = np.clip((m[on] * 4.0 + 0.5).astype(int), 1, 4)
        chars = SHADE[idx]
    elif style == 'bits':
        chars = np.where(rng.random(n) < 0.5, '0', '1')
    elif style == 'hex':
        chars = np.array(list(HEX))[rng.integers(0, 16, n)]
    elif style == 'solid':
        chars = '█'
    else:
        chars = style
    fb.ch[region][on] = chars
    if isinstance(color, np.ndarray) and color.ndim == 3:
        fb.fg[region][on] = color[ay:by, ax:bx][on]
    else:
        fb.fg[region][on] = color
    if bg is not None:
        fb.bg[region][on] = bg


def decrypt(s, prog, seed=0, tick=0):
    """Reveal s left->right; unrevealed glyphs are width-preserving random characters."""
    if prog <= 0:
        return ''
    n = len(s)
    k = int(prog * n * 1.25 - n * 0.25)
    out = []
    for i, ch in enumerate(s):
        if ch == ' ' or i < k:
            out.append(ch)
        else:
            r = h01(i, seed, tick)
            out.append(WIDE_POOL[int(r * len(WIDE_POOL))] if is_wide(ch) else NARROW_POOL[int(r * len(NARROW_POOL))])
    return ''.join(out)


def typewriter(fb, x, y, s, since, cps, fg=WHITE, cursor=False, t=0.0, bg=None):
    if since < 0:
        return x
    n = min(len(s), int(since * cps))
    end = fb.put(x, y, s[:n], fg, bg)
    if cursor and (n < len(s) or (t * 2.0) % 1.0 < 0.55):
        fb.put(end, y, '█', fg, bg)
    return end


def box(fb, x, y, w, h, fg=TEAL, bg=BLACK, fill=True, title=None, title_fg=None, title_bg=None):
    x, y, w, h = int(x), int(y), int(w), int(h)
    if w < 2 or h < 2:
        return
    if fill:
        fb.fill(x, y, w, h, ' ', fg, bg)
    fb.put(x, y, '┌' + '─' * (w - 2) + '┐', fg, bg)
    fb.put(x, y + h - 1, '└' + '─' * (w - 2) + '┘', fg, bg)
    for yy in range(y + 1, y + h - 1):
        fb.put(x, yy, '│', fg, bg)
        fb.put(x + w - 1, yy, '│', fg, bg)
    if title:
        fb.put(x + 2, y, title, title_fg or fg, title_bg if title_bg is not None else bg)


# ------------------------------------------------------------------------------------ glitch passes

def tear(fb, rng, amount, max_band=0.12):
    n = rng.poisson(amount * 5)
    for _ in range(n):
        y0 = int(rng.integers(0, fb.h))
        hh = int(rng.integers(1, max(2, int(fb.h * max_band))))
        dx = int(rng.normal(0, 1) * amount * fb.w * 0.12)
        if dx == 0:
            continue
        sl = slice(y0, min(fb.h, y0 + hh))
        fb.ch[sl] = np.roll(fb.ch[sl], dx, axis=1)
        fb.fg[sl] = np.roll(fb.fg[sl], dx, axis=1)
        fb.bg[sl] = np.roll(fb.bg[sl], dx, axis=1)


def sprinkle(fb, rng, prob, colors=(TEAL, WHITE, RED)):
    if prob <= 0:
        return
    m = rng.random((fb.h, fb.w)) < prob
    n = int(m.sum())
    if not n:
        return
    fb.ch[m] = NOISE[rng.integers(0, len(NOISE), n)]
    pal = np.array(colors, np.uint8)
    fb.fg[m] = pal[rng.integers(0, len(pal), n)]


def chroma(fb, dx, color=RED_D, y0=0, y1=None):
    """Colour-fringe ghost of rows y0..y1 shifted by dx (only into empty cells)."""
    y1 = fb.h if y1 is None else y1
    ch = fb.ch[y0:y1]
    src = (ch != ' ') & (ch != '')
    tgt = np.roll(src, dx, axis=1) & ~src
    if tgt.any():
        ch[tgt] = np.roll(ch, dx, axis=1)[tgt]
        fb.fg[y0:y1][tgt] = color


def blocks(fb, rng, n, colors=(RED, TEAL, WHITE)):
    for _ in range(n):
        w = int(rng.integers(3, max(4, fb.w // 5)))
        h = int(rng.integers(1, max(2, fb.h // 6)))
        x = int(rng.integers(0, max(1, fb.w - w)))
        y = int(rng.integers(0, max(1, fb.h - h)))
        c = colors[int(rng.integers(0, len(colors)))]
        k = int(rng.integers(0, 3))
        if k == 0:
            fb.fill(x, y, w, h, NOISE[int(rng.integers(0, 4))], c)
        elif k == 1:
            sub = (slice(y, y + h), slice(x, x + w))
            fb.bg[sub] = (np.array(c) * 0.45).astype(np.uint8)
            fb.fg[sub] = BLACK
        else:
            chars = NOISE[rng.integers(0, len(NOISE), (min(h, fb.h - y), min(w, fb.w - x)))]
            fb.ch[y:y + h, x:x + w] = chars
            fb.fg[y:y + h, x:x + w] = c


def glitch(fb, amount, rng):
    """Composite corruption pass. amount ~ 0 (clean) .. 1 (wrecked)."""
    if amount <= 0.02:
        return
    a = clamp(amount, 0, 1.5)
    tear(fb, rng, a)
    sprinkle(fb, rng, 0.06 * a * a)
    if rng.random() < a * 0.45:
        y0 = int(rng.integers(0, fb.h))
        y1 = min(fb.h, y0 + int(rng.integers(1, max(2, fb.h // 5))))
        chroma(fb, int(rng.choice([-2, -1, 1, 2])), RED_D if rng.random() < 0.6 else TEAL_D, y0, y1)
    nb = rng.poisson(a * a * 1.6)
    if nb:
        blocks(fb, rng, nb)


def flash(fb, s, color=(60, 90, 88)):
    if s <= 0:
        return
    s = clamp(s)
    fb.bg[:] = (fb.bg * (1 - s) + np.array(color) * s).astype(np.uint8)
    fb.fg[:] = (fb.fg * (1 - s) + np.array(WHITE) * s).astype(np.uint8)


def invert(fb, color=TEAL):
    on = (fb.ch != ' ') & (fb.ch != '')
    fb.bg[:] = color
    fb.bg[on] = (np.array(color) * 0.25).astype(np.uint8)
    fb.fg[:] = BLACK
    fb.fg[on] = WHITE


def flood(fb, rng, frac, colors=(TEAL, WHITE, TEAL_B, RED)):
    """Fill a fraction of all cells with noise glyphs."""
    sprinkle(fb, rng, frac, colors)


def rain_glyph(i, j, k=0):
    r = h01(i, j, k)
    if r < 0.5:
        return '0' if r < 0.25 else '1'
    return HALFKANA[int((r - 0.5) * 2 * len(HALFKANA)) % len(HALFKANA)]


__all__ = ['NOISE', 'HEX', 'HALFKANA', 'WIDE_POOL', 'block_text', 'raster', 'fit_raster', 'draw_mask', 'decrypt',
           'typewriter', 'box', 'tear', 'sprinkle', 'chroma', 'blocks', 'glitch', 'flash', 'invert', 'flood',
           'rain_glyph', 'str_width', 'GRAY', 'DIM']
