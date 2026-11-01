"""audio_vision.py —— 把声音变成可读的数据 + 频谱图。

用法: python audio_vision.py <BV>       （需要先跑过 listen.py 下好 audio.wav）
输出: 每 10 秒的频谱特征表 + 频谱图（0-4kHz）
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

HERE = Path(__file__).parent
SR = 16000
NFFT = 1024
HOP = 512


def load(path: Path):
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        sr = w.getframerate()
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return x, sr


def frames(x, n=NFFT, hop=HOP):
    if len(x) < n:
        return np.zeros((0, n), dtype=np.float32)
    count = 1 + (len(x) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(count)[:, None]
    return x[idx]


def analyze(x, sr):
    fr = frames(x)
    win = np.hanning(NFFT).astype(np.float32)
    spec = np.abs(np.fft.rfft(fr * win, axis=1)) + 1e-9
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    power = spec ** 2

    def band(lo, hi):
        m = (freqs >= lo) & (freqs < hi)
        return power[:, m].sum(axis=1)

    bass, mid, high = band(20, 300), band(300, 3000), band(3000, 8000)
    total = bass + mid + high + 1e-9
    centroid = (spec * freqs).sum(axis=1) / (spec.sum(axis=1) + 1e-9)
    flatness = np.exp(np.mean(np.log(spec), axis=1)) / (np.mean(spec, axis=1) + 1e-9)

    # 起音（能量差分）
    energy = spec.sum(axis=1)
    onset = np.maximum(0, np.diff(energy))
    onset = onset / (np.max(onset) + 1e-9)

    tps = sr / HOP  # 每秒帧数
    return dict(freqs=freqs, bass=bass / total, mid=mid / total, high=high / total,
                centroid=centroid, flatness=flatness, onset=onset, tps=tps,
                n=len(fr))


def verdict(bass, mid, high, flat, cent):
    if flat > 0.35 and cent > 2000:
        return "噪声/机械声"
    if mid > 0.55 and flat < 0.22:
        return "人声为主"
    if bass > 0.5:
        return "低频重（鼓/引擎）"
    if flat < 0.15:
        return "音乐（谐波强）"
    return "混合"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法: python audio_vision.py <BV>")
    bv = sys.argv[1]
    d = HERE / "audio_out" / bv
    wav = d / "audio.wav"
    if not wav.exists():
        sys.exit(f"缺音频，请先跑 listen.py {bv}")

    x, sr = load(wav)
    r = analyze(x, sr)
    dur = len(x) / sr
    print(f"时长 {dur:.0f}s｜每 10 秒统计（比例按能量）")
    print("  时间    低频    中频    高频   谱心(Hz) 平坦度  起音/秒  判断")
    step = r["tps"] * 10
    i = 0
    while i * 10 < dur:
        a, b = int(i * step), int((i + 1) * step)
        if b > r["n"]:
            break
        ba, mi, hi = r["bass"][a:b].mean(), r["mid"][a:b].mean(), r["high"][a:b].mean()
        ce, fl = r["centroid"][a:b].mean(), r["flatness"][a:b].mean()
        ons = r["onset"][a:b]
        rate = float((ons > 0.18).sum()) / 10.0
        print(f"  {i*10:>3}-{i*10+10:<3} {ba:6.2f} {mi:6.2f} {hi:6.2f} {ce:8.0f} {fl:6.2f} {rate:8.1f}  {verdict(ba, mi, hi, fl, ce)}")
        i += 1

    sp = d / "spectrum_low.png"
    if not sp.exists():
        subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-lavfi",
                        "showspectrumpic=s=1600x600:mode=combined:scale=log:legend=1:color=intensity:start=0:stop=4000",
                        str(sp)], capture_output=True)
    print(f"频谱图: {sp}")


if __name__ == "__main__":
    main()
