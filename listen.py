"""listen.py —— 让我"听见"：下载音轨 → 算包络/节奏 → 画图 + 打印可读摘要。

用法: python listen.py <BV>
输出: video/audio_out/<BV>/envelope.png + 文字摘要（分段类型、高能时刻、动态范围）
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

from audio_util import ensure_audio

HERE = Path(__file__).parent
SR = 16000
WIN = 0.25  # 每 0.25 秒一个能量点


def fmt(t: float) -> str:
    return f"{int(t)//60}:{int(t)%60:02d}"


def envelope(path: Path):
    with wave.open(str(path), "rb") as w:
        n, ch, sw, fr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    step = int(fr * WIN)
    vals = []
    # 16-bit 小端
    for i in range(0, len(raw) - 3, 2 * step):
        chunk = raw[i:i + 2 * step]
        s = 0
        cnt = 0
        for j in range(0, len(chunk) - 1, 2):
            v = int.from_bytes(chunk[j:j + 2], "little", signed=True)
            s += v * v
            cnt += 1
        vals.append((s / cnt) ** 0.5 if cnt else 0.0)
    return vals, len(raw) / (2 * fr)


def analyze(vals, dur):
    peak = max(vals) or 1
    norm = [v / peak for v in vals]
    # 静音 / 中 / 高 三段占比
    sil = sum(1 for v in norm if v < 0.06) / len(norm)
    mid = sum(1 for v in norm if 0.06 <= v < 0.5) / len(norm)
    high = sum(1 for v in norm if v >= 0.5) / len(norm)
    # 高能时刻：局部极大且超过 0.6
    cand = [(i, norm[i]) for i in range(1, len(norm) - 1)
            if norm[i] > 0.6 and norm[i] >= norm[i - 1] and norm[i] >= norm[i + 1]]
    cand.sort(key=lambda x: -x[1])
    peaks = []
    for i, v in cand:
        if all(abs(i - j) * WIN >= 15 for j, _ in peaks):
            peaks.append((i, v))
        if len(peaks) >= 6:
            break
    peaks.sort()
    # 音量突变（切歌/静音/爆音）
    jumps = []
    for i in range(1, len(norm)):
        d = norm[i] - norm[i - 1]
        if abs(d) > 0.35:
            jumps.append((i, d))
    return norm, sil, mid, high, peaks[:8], jumps[:10]


def draw(norm, dur, peaks, jumps, out: Path, title: str):
    W, H = 1600, 440
    img = Image.new("RGB", (W, H), (14, 17, 22))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 22)
    f2 = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 16)

    left, right, top, bot = 64, W - 40, 76, H - 46
    # 标题与刻度
    d.text((28, 20), title[:64], font=f1, fill=(245, 246, 248))
    for lv, lab in ((0.5, "50%"), (1.0, "100%")):
        y = bot - int((bot - top) * lv)
        d.line([(left, y), (right, y)], fill=(34, 40, 50), width=1)
        d.text((16, y - 9), lab, font=f2, fill=(96, 104, 118))

    # 抽稀到 ~400 点，画面积
    n = len(norm)
    step = max(1, n // 400)
    pts = [norm[i] for i in range(0, n, step)]
    m = len(pts)
    poly = [(left, bot)]
    for i, v in enumerate(pts):
        x = left + (right - left) * i / max(1, m - 1)
        poly.append((x, bot - int((bot - top) * v)))
    poly.append((right, bot))
    d.polygon(poly, fill=(46, 96, 150))
    d.line(poly[1:-1], fill=(120, 180, 255), width=2)

    # 高能区（>50%）涂橙
    for i, v in enumerate(pts):
        if v > 0.5:
            x = left + (right - left) * i / max(1, m - 1)
            y = bot - int((bot - top) * v)
            d.line([(x, bot), (x, y)], fill=(255, 117, 0), width=max(2, (right - left) // m))

    # 峰值标注（错开两行）
    for k, (i, v) in enumerate(peaks):
        x = left + (right - left) * (i / max(1, n - 1))
        y = bot - int((bot - top) * v)
        d.line([(x, top), (x, bot)], fill=(255, 190, 120), width=1)
        ly = top - 24 if k % 2 == 0 else top - 46
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 190, 120))
        d.text((x - 16, ly), fmt(i * WIN), font=f2, fill=(255, 190, 120))

    for tpx in range(0, int(dur) + 1, 30):
        x = left + (right - left) * tpx / max(1, dur)
        d.line([(x, bot), (x, bot - 4)], fill=(70, 78, 92), width=1)
        d.text((x - 14, bot + 10), fmt(tpx), font=f2, fill=(120, 128, 142))

    d.text((28, H - 26), "橙色=高能(>50%)  蓝色=有声   竖线=局部峰值", font=f2, fill=(110, 118, 132))
    img.save(out)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法: python listen.py <BV>")
    bv = sys.argv[1]
    outdir = HERE / "audio_out" / bv
    outdir.mkdir(parents=True, exist_ok=True)
    wav = ensure_audio(bv)          # 缺就自动下载（纯 HTTP，无需 bilibili-api）

    vals, dur = envelope(wav)
    norm, sil, mid, high, peaks, jumps = analyze(vals, dur)
    png = outdir / "envelope.png"
    draw(norm, dur, peaks, jumps, png, f"{bv} 音轨分析 · {fmt(dur)}")

    print(f"时长 {fmt(dur)}｜静音 {sil*100:.0f}%｜有声 {mid*100:.0f}%｜高能 {high*100:.0f}%")
    if peaks:
        print("高能时刻: " + "、".join(f"{fmt(i*WIN)}({v:.2f})" for i, v in peaks))
    if jumps:
        print("音量突变: " + "、".join(f"{fmt(i*WIN)}({'+' if dv>0 else ''}{dv:.2f})" for i, dv in jumps[:6]))
    print(f"图: {png}")


if __name__ == "__main__":
    main()
