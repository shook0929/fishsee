"""bgm.py —— 用代码合成原创背景音乐（免版权、可调情绪）。

用法:
  python bgm.py <输出wav> --dur 70 --mood calm|tense|warm
说明: 生成一段 ambient pad（和弦铺底），音量很轻，配旁白用。
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100

# 和弦（频率 Hz）：根音、五度、八度、三度
CHORDS = {
    "calm":  [[220.00, 329.63, 440.00, 261.63],   # Am
              [174.61, 261.63, 349.23, 220.00],   # F
              [261.63, 392.00, 523.25, 329.63],   # C
              [196.00, 293.66, 392.00, 246.94]],  # G
    "warm":  [[261.63, 392.00, 523.25, 329.63],   # C
              [220.00, 329.63, 440.00, 261.63],   # Am
              [174.61, 261.63, 349.23, 220.00],   # F
              [196.00, 293.66, 392.00, 246.94]],  # G
    "tense": [[146.83, 220.00, 293.66, 174.61],   # Dm
              [138.59, 207.65, 277.18, 164.81],   # C#dim 味道
              [146.83, 220.00, 293.66, 174.61],
              [130.81, 196.00, 261.63, 155.56]],  # Cm
}

MOOD_CFG = {
    "calm":  dict(bar=4.0, attack=1.2, release=1.8, bright=0.55, level=0.18),
    "warm":  dict(bar=3.6, attack=0.9, release=1.5, bright=0.70, level=0.20),
    "tense": dict(bar=3.0, attack=0.4, release=0.9, bright=0.85, level=0.20),
}


def env(n: int, attack: float, release: float, sr: int = SR) -> np.ndarray:
    a = int(attack * sr)
    r = int(release * sr)
    e = np.ones(n, dtype=np.float32)
    a = min(a, n)
    if a > 0:
        e[:a] = np.linspace(0, 1, a, dtype=np.float32) ** 1.5
    r = min(r, n)
    if r > 0:
        e[-r:] *= np.linspace(1, 0, r, dtype=np.float32) ** 1.2
    return e


def lowpass(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    """一阶 IIR 低通。"""
    alpha = cutoff / (cutoff + sr / (2 * np.pi))
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y


def make(dur: float, mood: str) -> np.ndarray:
    cfg = MOOD_CFG[mood]
    chords = CHORDS[mood]
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)

    bar = cfg["bar"]
    t0 = 0.0
    idx = 0
    while t0 < dur:
        chord = chords[idx % len(chords)]
        length = min(bar, dur - t0)
        m = int(length * SR)
        if m <= 0:
            break
        seg = np.zeros(m, dtype=np.float32)
        tt = np.arange(m) / SR
        for k, f in enumerate(chord):
            amp = 0.30 / (k + 1) ** 0.7
            # 轻微失谐，避免电子味
            vib = 1 + 0.0015 * np.sin(2 * np.pi * (0.15 + 0.05 * k) * tt)
            seg += amp * np.sin(2 * np.pi * f * tt * vib).astype(np.float32)
            seg += 0.35 * amp * np.sin(2 * np.pi * f * 2 * tt).astype(np.float32)  # 泛音
        seg *= env(m, cfg["attack"], cfg["release"])
        start = int(t0 * SR)
        out[start:start + m] += seg
        t0 += length
        idx += 1

    # 低通去刺耳，加一点点底噪（呼吸感）
    bright = cfg["bright"]
    out = lowpass(out, 900 + 2600 * bright)
    out += (np.random.default_rng(7).normal(0, 0.0015, n)).astype(np.float32)

    # 整体淡入淡出
    fade = int(2.0 * SR)
    out[:fade] *= np.linspace(0, 1, fade, dtype=np.float32) ** 1.5
    out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32) ** 1.2

    peak = np.max(np.abs(out)) or 1.0
    return (out / peak * cfg["level"]).astype(np.float32)


def save(path: Path, x: np.ndarray) -> None:
    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--dur", type=float, default=70)
    ap.add_argument("--mood", default="calm", choices=list(CHORDS))
    a = ap.parse_args()
    x = make(a.dur, a.mood)
    save(Path(a.out), x)
    print(f"{a.out}  {a.dur:.0f}s  mood={a.mood}  峰值 {20*np.log10(np.max(np.abs(x))):.1f} dB")


if __name__ == "__main__":
    main()
