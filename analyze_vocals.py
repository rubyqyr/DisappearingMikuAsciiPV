#!/usr/bin/env python3
"""Extract syllable events and a pitch track from an isolated vocal stem -> assets/vocal.npz.

The stem comes from Demucs, e.g.:
    python -m demucs --two-stems=vocals -o /tmp/sep assets/song.mp3
    python3 analyze_vocals.py /tmp/sep/htdemucs/song/vocals.wav
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 22050
BEAT0, SLOT = 0.08, 0.0625          # 1/16 note grid at 240 BPM


def decode(path):
    p = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, np.float32).copy()


def align(song, stem):
    """Samples by which the stem lags the decoded song."""
    mix_start = int(60 * SR)
    ref = song[mix_start:mix_start + 10 * SR]
    best = (-np.inf, 0)
    for lag in range(-4000, 4001):
        y = stem[mix_start + lag:mix_start + lag + len(ref)]
        if len(y) == len(ref):
            c = float(np.dot(ref, y))
            if c > best[0]:
                best = (c, lag)
    return best[1]


def stft_bands(v, n_fft=1024, hop=110, nb=40):
    nfr = (len(v) - n_fft) // hop
    win = np.hanning(n_fft).astype(np.float32)
    f = np.fft.rfftfreq(n_fft, 1 / SR)
    edges = np.geomspace(150, 7000, nb + 1)
    M = np.zeros((len(f), nb), np.float32)
    for i in range(nb):
        m = (f >= edges[i]) & (f < edges[i + 1])
        if not m.any():
            m[np.argmin(np.abs(f - edges[i]))] = True
        M[m, i] = 1 / m.sum()
    B = np.empty((nfr, nb), np.float32)
    for s in range(0, nfr, 8000):
        e = min(nfr, s + 8000)
        idx = (np.arange(s, e) * hop)[:, None] + np.arange(n_fft)[None, :]
        B[s:e] = np.abs(np.fft.rfft(v[idx] * win, axis=1)) @ M
    return B, SR / hop


def syllables(v):
    """1/16-grid slots where a new syllable starts: (times, strength 0..1, spectral centroid in Hz)."""
    B, fps = stft_bands(v)
    fc = np.sqrt(np.geomspace(150, 7000, 41)[:-1] * np.geomspace(150, 7000, 41)[1:])
    vb = (fc > 300) & (fc < 3500)
    L = np.log(B + 1e-4)
    E = 10 * np.log10(B.sum(1) + 1e-10)
    ref = np.percentile(E, 99)
    lag = 4
    flux = np.r_[np.zeros(lag), np.maximum(0, L[lag:] - L[:-lag]).mean(1)]
    dur = len(v) / SR
    slots = np.arange(BEAT0, dur - 0.1, SLOT)
    strength = np.zeros(len(slots))
    level = np.zeros(len(slots))
    for k, ts in enumerate(slots):
        i0, i1 = int((ts - 0.025) * fps), int((ts + 0.035) * fps)
        strength[k] = flux[max(0, i0):i1].max()
        level[k] = E[max(0, i0):i1].max() - ref
    voiced = level > -30
    med = np.median(strength[voiced])
    fire = voiced & (strength > med * 0.7)
    cent = np.zeros(len(slots))
    for k in np.where(fire)[0]:
        i0 = int(slots[k] * fps)
        spec = B[i0:i0 + int(0.06 * fps), vb].mean(0)
        cent[k] = float((spec * fc[vb]).sum() / (spec.sum() + 1e-9))
    return slots[fire], np.clip(strength[fire] / (med * 3), 0, 1), cent[fire]


def pitch(v, hop=220, n=1024):
    """Autocorrelation pitch at 100 fps, as MIDI note numbers (nan when unvoiced)."""
    nfr = (len(v) - n) // hop
    lo, hi = int(SR / 1100), int(SR / 150)
    out = np.full(nfr, np.nan, np.float32)
    win = np.hanning(n).astype(np.float32)
    for s in range(0, nfr, 4000):
        e = min(nfr, s + 4000)
        idx = (np.arange(s, e) * hop)[:, None] + np.arange(n)[None, :]
        fr = v[idx] * win
        spec = np.fft.rfft(fr, 2 * n, axis=1)
        acf = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, :hi + 1]
        e0 = acf[:, 0] + 1e-9
        seg = acf[:, lo:hi + 1]
        k = np.argmax(seg, axis=1)
        conf = seg[np.arange(len(k)), k] / e0
        loud = 10 * np.log10(e0) > np.percentile(10 * np.log10(e0), 40)
        f0 = SR / (k + lo)
        ok = (conf > 0.45) & loud
        out[s:e][ok] = 69 + 12 * np.log2(f0[ok] / 440.0)
    good = ~np.isnan(out)
    sm = out.copy()
    for i in np.where(good)[0]:
        w = out[max(0, i - 3):i + 4]
        w = w[~np.isnan(w)]
        sm[i] = np.median(w)
    return sm


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    song = decode(os.path.join(HERE, 'assets', 'song.mp3'))
    stem = decode(sys.argv[1])
    lag = align(song, stem)
    v = stem[lag:] if lag >= 0 else np.pad(stem, (-lag, 0))
    t, s, cent = syllables(v)
    f0 = pitch(v)
    out = os.path.join(HERE, 'assets', 'vocal.npz')
    np.savez_compressed(out, syl_t=t.astype(np.float32), syl_s=s.astype(np.float32), syl_c=cent.astype(np.float32),
                        f0=f0, f0_fps=np.float32(100))
    print(f'lag {lag} samples; {len(t)} syllables; pitch frames {len(f0)} -> {out}')


if __name__ == '__main__':
    main()
