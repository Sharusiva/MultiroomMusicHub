"""
Generates the demo music library for Multiroom Music Hub.

Every track is synthesized from scratch with numpy (oscillators, envelopes,
filters, a simple sequencer), so the music is 100% original and royalty free.

Usage:
    pip install numpy scipy
    python tools/generate_music.py            # writes media/*.mp3 (needs ffmpeg)
"""
import json
import os
import subprocess
import sys

import numpy as np
from scipy.signal import butter, lfilter

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "media")


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def adsr(n, a=0.01, d=0.1, s=0.7, r=0.1):
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(n - a_n - d_n - r_n, 0)
    env = np.concatenate([
        np.linspace(0, 1, a_n, endpoint=False),
        np.linspace(1, s, d_n, endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, r_n),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def lowpass(x, cutoff):
    b, a = butter(2, min(cutoff / (SR / 2), 0.99), btype="low")
    return lfilter(b, a, x)


def highpass(x, cutoff):
    b, a = butter(2, cutoff / (SR / 2), btype="high")
    return lfilter(b, a, x)


def bandpass(x, lo, hi):
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], btype="band")
    return lfilter(b, a, x)


def saw(f, t, harmonics=12):
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if f * k > SR / 2.2:
            break
        out += ((-1) ** (k + 1)) * np.sin(2 * np.pi * f * k * t) / k
    return out * 0.6


def square(f, t, duty=0.5):
    ph = (f * t) % 1.0
    return np.where(ph < duty, 1.0, -1.0) * 0.5


def triangle(f, t):
    ph = (f * t) % 1.0
    return (4 * np.abs(ph - 0.5) - 1.0)


# ---------------------------------------------------------------------------
# Instruments: each returns a mono numpy buffer
# ---------------------------------------------------------------------------

def inst_pad(m, dur, bright=1800):
    t = t_axis(dur)
    f = midi_hz(m)
    x = saw(f * 0.997, t) + saw(f * 1.003, t) + 0.5 * saw(f * 2.001, t, 6)
    x = lowpass(x, bright)
    return x * adsr(len(t), a=min(0.8, dur / 3), d=0.3, s=0.8, r=min(0.8, dur / 3)) * 0.18


def inst_keys(m, dur):
    """Electric-piano-ish: sine + bell partials with decay."""
    t = t_axis(dur)
    f = midi_hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 6) \
        + 0.15 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 9)
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return x * trem * adsr(len(t), a=0.005, d=0.6, s=0.35, r=0.25) * 0.22


def inst_pluck(m, dur):
    t = t_axis(dur)
    f = midi_hz(m)
    x = saw(f, t, 8)
    x = lowpass(x, 900 + 3000 * np.exp(-0.0) )
    return x * np.exp(-t * 5.5) * adsr(len(t), a=0.003, d=0.05, s=1.0, r=0.05) * 0.3


def inst_bell(m, dur):
    t = t_axis(dur)
    f = midi_hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3) \
        + 0.25 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 6)
    return x * np.exp(-t * 2.2) * adsr(len(t), a=0.002, d=0.1, s=1, r=0.1) * 0.16


def inst_lead(m, dur):
    t = t_axis(dur)
    f = midi_hz(m)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t * 3, 0, 1)
    ph = np.cumsum(f * vib) / SR
    x = np.zeros_like(t)
    for k in range(1, 10):
        x += ((-1) ** (k + 1)) * np.sin(2 * np.pi * k * ph) / k
    x = lowpass(x, 2600)
    return x * adsr(len(t), a=0.02, d=0.15, s=0.7, r=0.12) * 0.13


def inst_bass(m, dur):
    t = t_axis(dur)
    f = midi_hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t)
    x = np.tanh(x * 1.6)
    return x * adsr(len(t), a=0.005, d=0.1, s=0.8, r=0.06) * 0.32


def inst_square(m, dur, duty=0.25):
    t = t_axis(dur)
    x = square(midi_hz(m), t, duty)
    return lowpass(x, 6000) * adsr(len(t), a=0.002, d=0.05, s=0.6, r=0.03) * 0.12


def inst_tri_bass(m, dur):
    t = t_axis(dur)
    return triangle(midi_hz(m), t) * adsr(len(t), a=0.002, d=0.05, s=0.9, r=0.02) * 0.3


def drum_kick(dur=0.45, punch=1.0):
    t = t_axis(dur)
    f = 45 + 110 * np.exp(-t * 28)
    ph = np.cumsum(f) / SR
    return np.sin(2 * np.pi * ph) * np.exp(-t * 7) * 0.75 * punch


def drum_snare(dur=0.25, rng=None):
    t = t_axis(dur)
    noise = rng.uniform(-1, 1, len(t))
    x = bandpass(noise, 1200, 7000) * np.exp(-t * 18) * 0.6
    x += np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.35
    return x * 0.6


def drum_clap(dur=0.25, rng=None):
    t = t_axis(dur)
    noise = bandpass(rng.uniform(-1, 1, len(t)), 900, 4000)
    env = np.exp(-t * 22) + 0.6 * np.exp(-((t - 0.012) % 0.011) * 300) * (t < 0.035)
    return noise * env * 0.45


def drum_hat(dur=0.06, rng=None, open_=False):
    d = 0.25 if open_ else dur
    t = t_axis(d)
    x = highpass(rng.uniform(-1, 1, len(t)), 7000)
    return x * np.exp(-t * (12 if open_ else 60)) * 0.22


def drum_noise_chip(dur=0.08, rng=None, low=False):
    t = t_axis(dur)
    step = 40 if low else 8
    n = rng.uniform(-1, 1, len(t) // step + 1).repeat(step)[: len(t)]
    return np.sign(n) * np.exp(-t * (20 if low else 45)) * 0.18


# ---------------------------------------------------------------------------
# Sequencer
# ---------------------------------------------------------------------------

class Song:
    def __init__(self, bpm, bars, seed=0):
        self.bpm = bpm
        self.beat = 60.0 / bpm
        self.bars = bars
        self.length = bars * 4 * self.beat + 3.0
        self.L = np.zeros(int(self.length * SR) + SR)
        self.R = np.zeros_like(self.L)
        self.rng = np.random.default_rng(seed)

    def add(self, buf, beat_pos, pan=0.0, gain=1.0):
        i = int(beat_pos * self.beat * SR)
        if i >= len(self.L):
            return
        n = min(len(buf), len(self.L) - i)
        lg = gain * np.sqrt(0.5 * (1 - pan))
        rg = gain * np.sqrt(0.5 * (1 + pan))
        self.L[i:i + n] += buf[:n] * lg
        self.R[i:i + n] += buf[:n] * rg

    def beats(self, b):
        return b * self.beat

    def render(self, reverb=0.25):
        out = []
        for ch, delay_ms in ((self.L, 0), (self.R, 11)):
            x = ch.copy()
            # cheap reverb: a few feedback-less echoes that are lowpassed
            for d, g in ((0.037, 0.5), (0.061, 0.4), (0.089, 0.32), (0.131, 0.25), (0.173, 0.18)):
                k = int((d + delay_ms / 1000) * SR)
                tail = np.zeros_like(x)
                tail[k:] = x[:-k]
                x = x + lowpass(tail, 3500) * g * reverb
            out.append(x)
        st = np.stack(out, axis=1)
        st = st[: int(self.length * SR)]
        # fade in/out and normalize
        fade = int(2.5 * SR)
        st[-fade:] *= np.linspace(1, 0, fade)[:, None]
        st[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))[:, None]
        peak = np.max(np.abs(st)) or 1
        st = np.tanh(st / peak * 1.15) * 0.89
        return st


def chord_notes(root, quality):
    shapes = {
        "maj": [0, 4, 7], "min": [0, 3, 7], "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10],
        "dom7": [0, 4, 7, 10], "sus2": [0, 2, 7], "add9": [0, 4, 7, 14], "min9": [0, 3, 7, 10, 14],
    }
    return [root + s for s in shapes[quality]]


def motif(rng, chord, scale, length_beats=8, density=0.55, step=0.5):
    """A repeating melodic phrase; chord tones on strong beats, scale tones elsewhere."""
    notes = []
    pos = 0.0
    last = rng.choice(chord) + 12
    while pos < length_beats:
        if rng.random() < density or pos == 0:
            strong = (pos % 1.0) == 0
            pool = [c + 12 for c in chord] if strong else [s for s in scale if abs(s - last) <= 5]
            if not pool:
                pool = [c + 12 for c in chord]
            n = int(rng.choice(pool))
            dur = step * (2 if rng.random() < 0.3 else 1)
            notes.append((pos, n, dur))
            last = n
            pos += dur
        else:
            pos += step
    return notes


def scale_notes(root, mode="minor", lo=60, hi=88):
    steps = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11],
             "penta": [0, 3, 5, 7, 10], "dorian": [0, 2, 3, 5, 7, 9, 10]}[mode]
    return [n for n in range(lo, hi) if (n - root) % 12 in steps]


# ---------------------------------------------------------------------------
# The six tracks
# ---------------------------------------------------------------------------

def track_lofi():
    s = Song(bpm=78, bars=36, seed=1)
    prog = [(57, "min9"), (53, "maj7"), (48, "maj7"), (55, "dom7")]  # Am9 Fmaj7 Cmaj7 G7
    scale = scale_notes(57, "minor", 69, 90)
    phrases = [motif(s.rng, chord_notes(r - 12 + 12, q)[:3], scale, 8, 0.45) for r, q in prog[:2]]
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        for n in chord_notes(r, q):
            s.add(inst_keys(n, s.beats(3.6)), b0, pan=-0.2, gain=0.9)
            s.add(inst_keys(n, s.beats(1.5)), b0 + 2.5, pan=0.2, gain=0.35)
        s.add(inst_bass(r - 24, s.beats(1.6)), b0)
        s.add(inst_bass(r - 24 + 7, s.beats(0.9)), b0 + 2.5)
        if 4 <= bar < 32:
            for k in (0, 2.5):
                s.add(drum_kick(punch=0.8), b0 + k)
            for k in (1, 3):
                s.add(drum_snare(rng=s.rng), b0 + k, gain=0.6)
            for e in range(8):
                swing = 0.17 if e % 2 else 0
                s.add(drum_hat(rng=s.rng), b0 + e * 0.5 + swing, pan=0.3, gain=0.6 if e % 2 else 0.9)
        if 12 <= bar < 28 and bar % 2 == 0:
            for pos, n, d in phrases[(bar // 2) % 2]:
                s.add(inst_bell(n, s.beats(d) + 0.6), b0 + pos, pan=0.35, gain=0.8)
    # vinyl crackle
    crackle = (s.rng.random(len(s.L)) > 0.9993) * s.rng.uniform(-0.25, 0.25, len(s.L))
    s.L += crackle
    s.R += np.roll(crackle, 300)
    s.L += lowpass(s.rng.normal(0, 0.004, len(s.L)), 3000)
    return s.render(0.35)


def track_synthwave():
    s = Song(bpm=100, bars=44, seed=2)
    prog = [(57, "min"), (53, "maj"), (48, "maj"), (55, "maj")]
    scale = scale_notes(57, "minor", 64, 88)
    lead_a = motif(s.rng, [57, 60, 64], scale, 8, 0.6)
    lead_b = motif(s.rng, [53, 57, 60], scale, 8, 0.6)
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        notes = chord_notes(r, q)
        for n in notes:
            s.add(inst_pad(n, s.beats(4.1), bright=1400 if bar < 8 else 2400), b0, pan=0, gain=0.9)
        if bar >= 4:
            for e in range(16):  # arpeggio
                n = notes[e % 3] + (12 if (e // 3) % 2 else 0)
                s.add(inst_pluck(n + 12, s.beats(0.3)), b0 + e * 0.25, pan=0.4 * np.sin(e), gain=0.55)
            for e in range(8):
                s.add(inst_bass(r - 24, s.beats(0.45)), b0 + e * 0.5, gain=0.85)
        if 8 <= bar < 40:
            for k in range(4):
                s.add(drum_kick(), b0 + k)
            for k in (1, 3):
                s.add(drum_snare(rng=s.rng), b0 + k, gain=1.0)
                s.add(drum_clap(rng=s.rng), b0 + k, gain=0.6)
            for e in range(8):
                s.add(drum_hat(rng=s.rng), b0 + e * 0.5 + 0.0, pan=-0.3, gain=0.5)
        if 16 <= bar < 40 and bar % 2 == 0:
            for pos, n, d in (lead_a if (bar // 4) % 2 == 0 else lead_b):
                s.add(inst_lead(n, s.beats(d) * 0.95), b0 + pos, pan=0.1, gain=1.0)
    return s.render(0.4)


def track_ambient():
    s = Song(bpm=60, bars=26, seed=3)
    prog = [(50, "add9"), (45, "sus2"), (47, "min7"), (43, "maj7")]  # D A Bm G
    for bar in range(s.bars):
        r, q = prog[(bar // 2) % 4]
        b0 = bar * 4
        if bar % 2 == 0:
            for n in chord_notes(r, q):
                s.add(inst_pad(n, s.beats(8.4), bright=1100), b0, pan=s.rng.uniform(-0.5, 0.5), gain=1.1)
            s.add(inst_pad(r - 12, s.beats(8.4), bright=500), b0, gain=0.9)
        if bar >= 2:
            for e in range(4):
                if s.rng.random() < 0.7:
                    n = int(s.rng.choice(chord_notes(r, q))) + 24
                    s.add(inst_bell(n, 3.5), b0 + e + s.rng.choice([0, 0.5]),
                          pan=s.rng.uniform(-0.8, 0.8), gain=0.7)
    return s.render(0.7)


def track_kitchen():
    s = Song(bpm=112, bars=44, seed=4)
    prog = [(48, "maj"), (57, "min"), (53, "maj"), (55, "maj")]  # C Am F G
    scale = scale_notes(48, "major", 67, 88)
    hook = motif(s.rng, [60, 64, 67], scale, 8, 0.7)
    hook2 = motif(s.rng, [57, 60, 64], scale, 8, 0.65)
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        notes = chord_notes(r + 12, q)
        for k in (0, 1.5, 2, 3.5):  # bouncy comping
            for n in notes:
                s.add(inst_keys(n, s.beats(0.45)), b0 + k, pan=-0.25, gain=0.7)
        s.add(inst_bass(r - 12, s.beats(0.9)), b0)
        s.add(inst_bass(r - 12, s.beats(0.4)), b0 + 1.5)
        s.add(inst_bass(r - 5, s.beats(0.9)), b0 + 2)
        s.add(inst_bass(r - 12 + 12, s.beats(0.4)), b0 + 3.5)
        if 4 <= bar < 42:
            s.add(drum_kick(), b0)
            s.add(drum_kick(punch=0.7), b0 + 2.5)
            for k in (1, 3):
                s.add(drum_clap(rng=s.rng), b0 + k, gain=1.1)
            for e in range(16):
                s.add(drum_hat(rng=s.rng), b0 + e * 0.25, pan=0.35, gain=0.55 if e % 2 else 0.8)
        if 8 <= bar < 40:
            ph = hook if (bar // 2) % 2 == 0 else hook2
            if bar % 2 == 0:
                for pos, n, d in ph:
                    s.add(inst_pluck(n, s.beats(d)), b0 + pos, pan=0.25, gain=1.0)
                    s.add(inst_bell(n + 12, s.beats(d)), b0 + pos, pan=0.4, gain=0.35)
    return s.render(0.3)


def track_chiptune():
    s = Song(bpm=140, bars=56, seed=5)
    prog = [(57, "min"), (53, "maj"), (55, "maj"), (52, "min")]  # Am F G Em
    scale = scale_notes(57, "minor", 69, 93)
    a = motif(s.rng, [69, 72, 76], scale, 8, 0.8, step=0.25)
    b = motif(s.rng, [65, 69, 72], scale, 8, 0.8, step=0.25)
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        notes = chord_notes(r, q)
        for e in range(8):
            s.add(inst_tri_bass(r - 12 + (12 if e % 2 else 0), s.beats(0.45)), b0 + e * 0.5, gain=0.9)
        for e in range(16):
            s.add(inst_square(notes[e % 3] + 12, s.beats(0.2), duty=0.125), b0 + e * 0.25, pan=-0.3, gain=0.6)
        if bar >= 4:
            for k in (0, 2):
                s.add(drum_noise_chip(0.12, s.rng, low=True), b0 + k, gain=1.4)
            for k in (1, 3):
                s.add(drum_noise_chip(0.1, s.rng), b0 + k, gain=1.2)
            for e in range(8):
                s.add(drum_noise_chip(0.03, s.rng), b0 + e * 0.5 + 0.25, gain=0.5)
        if 8 <= bar < 52 and bar % 2 == 0:
            for pos, n, d in (a if (bar // 4) % 2 == 0 else b):
                s.add(inst_square(n, s.beats(d) * 0.9, duty=0.5), b0 + pos, pan=0.2, gain=1.1)
    return s.render(0.12)


def track_house():
    s = Song(bpm=122, bars=56, seed=6)
    prog = [(50, "min7"), (50, "min7"), (46, "maj7"), (48, "dom7")]  # Dm7 Dm7 Bbmaj7 C7
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        notes = chord_notes(r + 12, q)
        if bar >= 8:
            for k in (0.5, 1.75, 2.5, 3.75):  # chord stabs
                for n in notes:
                    s.add(lowpass(inst_pluck(n, s.beats(0.35)), 2200 if bar < 24 else 4000), b0 + k, gain=0.6)
        else:
            for n in notes:
                s.add(inst_pad(n, s.beats(4.1), bright=900 + bar * 120), b0, gain=0.8)
        if bar >= 4:
            for e in range(4):
                s.add(inst_bass(r - 12, s.beats(0.4)), b0 + e + 0.5, gain=0.9)
        if bar < 52:
            for k in range(4):
                s.add(drum_kick(punch=1.05), b0 + k)
        if bar >= 4 and bar < 52:
            for k in range(4):
                s.add(drum_hat(rng=s.rng, open_=True), b0 + k + 0.5, pan=0.2, gain=0.5)
            if bar >= 16:
                for k in (1, 3):
                    s.add(drum_clap(rng=s.rng), b0 + k, gain=0.9)
                for e in range(16):
                    s.add(drum_hat(rng=s.rng), b0 + e * 0.25, pan=-0.3, gain=0.3)
        if 24 <= bar < 48 and bar % 4 == 0:
            for i, n in enumerate([74, 72, 69, 72, 74, 77, 76, 72]):
                s.add(inst_bell(n, 1.2), b0 + i * 1.5 + 0.5, pan=0.5, gain=0.5)
    return s.render(0.3)


def track_jazzhop():
    """Swung jazz-hop: ii-V-I-vi in Bb with a walking bass and soft keys."""
    s = Song(bpm=86, bars=40, seed=7)
    prog = [(48, "min9"), (53, "dom7"), (46, "maj7"), (55, "min7")]  # Cm9 F7 Bbmaj7 Gm7
    scale = scale_notes(46, "major", 70, 89)
    lick_a = motif(s.rng, [70, 74, 77], scale, 8, 0.5)
    lick_b = motif(s.rng, [67, 70, 74], scale, 8, 0.5)
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        nr = prog[(bar + 1) % 4][0]
        b0 = bar * 4
        for n in chord_notes(r + 12, q)[:4]:
            s.add(inst_keys(n, s.beats(1.4)), b0, pan=-0.3, gain=0.8)
            s.add(inst_keys(n, s.beats(0.8)), b0 + 2.66, pan=-0.3, gain=0.5)
        if bar >= 2:  # walking bass: root, 3rd/5th, 5th, approach note to the next root
            walk = [r - 12, r - 12 + (3 if "min" in q else 4), r - 12 + 7, nr - 12 - 1]
            for k, n in enumerate(walk):
                s.add(inst_bass(n, s.beats(0.9)), b0 + k, gain=0.8)
        if 4 <= bar < 38:
            s.add(drum_kick(punch=0.7), b0)
            s.add(drum_kick(punch=0.5), b0 + 2.66)
            for k in (1, 3):
                s.add(drum_snare(rng=s.rng), b0 + k, gain=0.45)
            for k in range(4):  # swung ride pattern
                s.add(drum_hat(rng=s.rng), b0 + k, pan=0.4, gain=0.7)
                if k % 2:
                    s.add(drum_hat(rng=s.rng), b0 + k + 0.66, pan=0.4, gain=0.45)
        if 12 <= bar < 36 and bar % 2 == 0:
            for pos, n, d in (lick_a if (bar // 4) % 2 == 0 else lick_b):
                swing = 0.16 if (pos % 1) == 0.5 else 0
                s.add(inst_lead(n, s.beats(d) * 0.9), b0 + pos + swing, pan=0.25, gain=0.75)
    crackle = (s.rng.random(len(s.L)) > 0.9995) * s.rng.uniform(-0.2, 0.2, len(s.L))
    s.L += crackle
    s.R += np.roll(crackle, 211)
    return s.render(0.35)


def track_piano():
    """A slow, gentle piano piece: broken chords in G with a simple melody on top."""
    s = Song(bpm=72, bars=32, seed=8)
    prog = [(55, "maj"), (50, "maj"), (52, "min"), (48, "maj")]  # G D Em C
    melody = [
        [(0, 79, 1.5), (1.5, 78, 0.5), (2, 76, 2)],
        [(0, 74, 1.5), (1.5, 76, 0.5), (2, 78, 2)],
        [(0, 79, 1), (1, 81, 1), (2, 83, 1.5), (3.5, 81, 0.5)],
        [(0, 79, 3), (3, 76, 1)],
    ]
    for bar in range(s.bars):
        r, q = prog[bar % 4]
        b0 = bar * 4
        notes = chord_notes(r, q)
        pattern = [notes[0] - 12, notes[2] - 12, notes[0], notes[1], notes[2], notes[1], notes[0], notes[2] - 12]
        for e, n in enumerate(pattern):
            s.add(inst_keys(n, s.beats(1.6)), b0 + e * 0.5, pan=-0.15 + 0.04 * e, gain=0.75)
        if 4 <= bar < 28:
            octave = 12 if 16 <= bar < 24 else 0
            for pos, n, d in melody[bar % 4]:
                s.add(inst_keys(n + octave, s.beats(d) + 0.5), b0 + pos, pan=0.15, gain=1.0)
        if 8 <= bar < 28 and bar % 2 == 0:
            s.add(inst_pad(notes[0], s.beats(8.2), bright=800), b0, gain=0.5)
    return s.render(0.55)


def track_disco():
    """Disco/funk: octave bass, four-on-the-floor, offbeat open hats, string stabs."""
    s = Song(bpm=118, bars=52, seed=9)
    prog = [(57, "min7"), (50, "min7"), (55, "dom7"), (48, "maj7")]  # Am7 Dm7 G7 Cmaj7
    scale = scale_notes(57, "dorian", 69, 91)
    riff = motif(s.rng, [69, 72, 76], scale, 8, 0.75, step=0.25)
    for bar in range(s.bars):
        r, q = prog[(bar // 2) % 4]
        b0 = bar * 4
        notes = chord_notes(r + 12, q)
        for e in range(8):  # octave-jumping disco bass
            n = r - 12 + (12 if e % 2 else 0)
            s.add(inst_bass(n, s.beats(0.4)), b0 + e * 0.5, gain=0.85)
        if bar >= 4:
            for k in (0.5, 1.75, 2.5, 3.75):  # muted guitar-ish chops
                for n in notes[:3]:
                    s.add(lowpass(inst_pluck(n + 12, s.beats(0.18)), 3500), b0 + k, pan=0.45, gain=0.45)
        if bar >= 8 and bar % 2 == 0:
            for n in notes:
                s.add(inst_pad(n, s.beats(7.8), bright=3000), b0, pan=-0.35, gain=0.6)
        if 4 <= bar < 50:
            for k in range(4):
                s.add(drum_kick(punch=0.95), b0 + k)
                s.add(drum_hat(rng=s.rng, open_=True), b0 + k + 0.5, pan=0.25, gain=0.55)
            for k in (1, 3):
                s.add(drum_clap(rng=s.rng), b0 + k, gain=0.9)
                s.add(drum_snare(rng=s.rng), b0 + k, gain=0.4)
            for e in range(16):
                s.add(drum_hat(rng=s.rng), b0 + e * 0.25, pan=-0.3, gain=0.25)
        if 16 <= bar < 44 and bar % 2 == 0:
            for pos, n, d in riff:
                s.add(inst_lead(n, s.beats(d) * 0.85), b0 + pos, pan=0.1, gain=0.9)
    return s.render(0.3)


def track_dnb():
    """Drum & bass at 174 BPM: syncopated breakbeat, rolling sub bass, airy pads."""
    s = Song(bpm=174, bars=72, seed=10)
    prog = [(50, "min"), (46, "maj"), (53, "maj"), (48, "maj")]  # Dm Bb F C
    kick_pat = [0, 2.5]
    snare_pat = [1, 3]
    for bar in range(s.bars):
        r, q = prog[(bar // 2) % 4]
        b0 = bar * 4
        if bar % 4 == 0:
            for n in chord_notes(r, q):
                s.add(inst_pad(n + 12, s.beats(16.5), bright=1500 if bar < 32 else 2600), b0,
                      pan=s.rng.uniform(-0.6, 0.6), gain=0.8)
        if bar >= 8:
            for k, d in ((0, 1.4), (1.5, 0.4), (2.5, 1.2), (3.5, 0.4)):
                s.add(lowpass(inst_bass(r - 24, s.beats(d)), 400), b0 + k, gain=1.1)
        if 8 <= bar < 64:
            for k in kick_pat:
                s.add(drum_kick(punch=1.05), b0 + k)
            for k in snare_pat:
                s.add(drum_snare(rng=s.rng), b0 + k, gain=1.0)
            if bar % 2 == 1:
                s.add(drum_snare(rng=s.rng), b0 + 3.75, gain=0.45)  # ghost note
            for e in range(8):
                s.add(drum_hat(rng=s.rng), b0 + e * 0.5 + 0.25, pan=0.3, gain=0.55)
        if 24 <= bar < 56 and bar % 4 == 0:
            for i, n in enumerate([74, 77, 81, 79, 77, 74, 72, 74]):
                s.add(inst_bell(n, 2.0), b0 + i * 2, pan=-0.4 if i % 2 else 0.4, gain=0.6)
    return s.render(0.45)


TRACKS = [
    ("midnight-lofi", "Midnight Lo-Fi", "Sol Static", "Lo-fi", "#8b5cf6", track_lofi),
    ("neon-drive", "Neon Drive", "Synth Harbor", "Synthwave", "#ec4899", track_synthwave),
    ("glass-garden", "Glass Garden", "Aurora Fields", "Ambient", "#14b8a6", track_ambient),
    ("sunday-kitchen", "Sunday Kitchen", "The Toast Ensemble", "Pop", "#f59e0b", track_kitchen),
    ("pixel-quest", "Pixel Quest", "8-Bit Navigator", "Chiptune", "#22c55e", track_chiptune),
    ("deep-room-4am", "Deep Room 4AM", "Basement Theory", "House", "#3b82f6", track_house),
    ("rainy-window", "Rainy Window", "Blue Note Robots", "Jazz-hop", "#06b6d4", track_jazzhop),
    ("paper-lanterns", "Paper Lanterns", "Mira Keys", "Piano", "#f97316", track_piano),
    ("mirrorball", "Mirrorball", "Velvet Elevator", "Disco", "#ef4444", track_disco),
    ("night-circuit", "Night Circuit", "Halfstep Kids", "Drum & bass", "#a3e635", track_dnb),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    only = sys.argv[1:]
    meta = []
    for slug, title, artist, genre, color, fn in TRACKS:
        fname = f"{slug}.mp3"
        meta.append({"file": fname, "title": title, "artist": artist, "genre": genre, "color": color})
        if only and slug not in only:
            continue
        print(f"rendering {title} ...", flush=True)
        audio = fn()
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
             "-codec:a", "libmp3lame", "-b:a", "128k",
             "-metadata", f"title={title}", "-metadata", f"artist={artist}", "-metadata", f"genre={genre}",
             os.path.join(OUT_DIR, fname)],
            input=pcm, check=True,
        )
        print(f"  {fname}: {len(audio) / SR:.0f}s")
    with open(os.path.join(OUT_DIR, "library.json"), "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
