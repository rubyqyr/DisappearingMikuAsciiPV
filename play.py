#!/usr/bin/env python3
"""初音ミクの消失 — terminal ASCII music video.

    python3 play.py                 # full MV with audio
    python3 play.py --start 2:19    # jump to a timestamp
    python3 play.py --no-audio      # visuals only (timer driven)

Keys: q / Esc / Ctrl-C to quit.
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mv.engine import SONG_END, Audio, Encoder, Frame, Player, Terminal  # noqa: E402
from mv.scenes import Director  # noqa: E402


def parse_time(s):
    if ':' in s:
        m, sec = s.split(':', 1)
        return int(m) * 60 + float(sec)
    return float(s)


def find_audio(path):
    if path:
        return path
    d = os.path.join(HERE, 'assets')
    for name in ('song.mp3', 'song.m4a', 'song.opus', 'song.wav', 'song.flac'):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def dump_frame(director, t, w, h):
    fb = Frame(w, h)
    fb.clear()
    director.render(fb, t, 1 / 30)
    rows = []
    for row in fb.ch.tolist():
        rows.append(''.join(c for c in row).rstrip())
    print('\n'.join(rows))


def bench(director, w, h, fps):
    enc = Encoder(True)
    fb = Frame(w, h)
    worst = {}
    t = 0.0
    total = 0.0
    n = 0
    size = 0
    while t < SONG_END:
        fb.clear()
        t0 = time.perf_counter()
        director.render(fb, t, 1 / fps)
        data = enc.encode(fb)
        dt = time.perf_counter() - t0
        name = director.order[director.index(t)]
        worst[name] = max(worst.get(name, 0), dt)
        total += dt
        size += len(data)
        n += 1
        t += 1 / fps
    print(f'{n} frames, avg {total / n * 1000:.1f} ms/frame, avg {size / n / 1024:.1f} KiB/frame')
    for k, v in worst.items():
        print(f'  worst {k:10s} {v * 1000:6.1f} ms')


def main():
    ap = argparse.ArgumentParser(description='初音ミクの消失 — terminal ASCII MV')
    ap.add_argument('--audio', help='audio file (default: assets/song.*)')
    ap.add_argument('--start', default='0', help='start time, seconds or m:ss')
    ap.add_argument('--no-audio', action='store_true', help='do not play sound')
    ap.add_argument('--backend', default='auto', choices=['auto', 'mpv', 'ffplay', 'afplay', 'none'])
    ap.add_argument('--offset', type=float, default=0.0, help='A/V offset in seconds (+ = visuals later)')
    ap.add_argument('--fps', type=float, default=30.0)
    ap.add_argument('--color', default='auto', choices=['auto', 'truecolor', '256'])
    ap.add_argument('--dump', type=str, help='print a single frame at time T as plain text and exit')
    ap.add_argument('--size', default='100x30', help='frame size for --dump/--bench')
    ap.add_argument('--bench', action='store_true', help='render the whole timeline offscreen and report speed')
    args = ap.parse_args()

    path = find_audio(args.audio)
    if path is None:
        sys.stderr.write('audio not found (assets/song.mp3); run ./fetch_song.sh or pass --audio. '
                         'Continuing with synthetic audio features.\n')
    audio = Audio(path)
    director = Director(audio)

    if args.dump or args.bench:
        w, h = (int(v) for v in args.size.lower().split('x'))
        if args.bench:
            bench(director, w, h, args.fps)
        else:
            dump_frame(director, parse_time(args.dump), w, h)
        return

    tc = args.color == 'truecolor' or (args.color == 'auto' and os.environ.get('COLORTERM', '').lower() in
                                       ('truecolor', '24bit'))
    enc = Encoder(tc)
    start = parse_time(args.start)
    backend = 'none' if args.no_audio or path is None else args.backend
    player = Player(path, start, backend, args.offset)
    frame_dt = 1.0 / args.fps
    term = Terminal()
    try:
        with term:
            player.begin()
            fb = None
            last_t = None
            next_tick = time.perf_counter()
            while True:
                k = term.key()
                if k and any(ch in k for ch in ('q', 'Q', '\x1b', '\x03')):
                    break
                t = player.time()
                if t > SONG_END + 0.4:
                    break
                W, H = term.size()
                if fb is None or (fb.w, fb.h) != (W, H):
                    fb = Frame(W, H)
                    term.write(b'\x1b[0m\x1b[2J')
                dt = frame_dt if last_t is None else float(np.clip(t - last_t, 0.0, 0.2))
                last_t = t
                fb.clear()
                director.render(fb, t, dt)
                term.write(enc.encode(fb))
                next_tick += frame_dt
                sl = next_tick - time.perf_counter()
                if sl > 0:
                    time.sleep(sl)
                else:
                    next_tick = time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()


if __name__ == '__main__':
    main()
