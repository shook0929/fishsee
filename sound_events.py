"""sound_events.py —— 本地声音事件识别（YAMNet, ONNX, CPU）。

用法: python sound_events.py <BV>            （需先跑 listen.py 下好 audio.wav）
输出: 每 0.96 秒的 top 声音事件时间线 + 事件统计 + 可选时间线图
"""
from __future__ import annotations

import csv
import sys
import wave
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFont
from audio_util import ensure_audio

HERE = Path(__file__).parent
MODEL = HERE / "models" / "yamnet.onnx"
CLASSES = HERE / "models" / "yamnet_class_map.csv"
SR = 16000

# 合并到易读的大类
GROUPS = {
    "说话": ["Speech", "Speech synthesizer", "Conversation", "Narration", "Male speech", "Female speech", "Child speech"],
    "音乐": ["Music", "Musical instrument", "Guitar", "Piano", "Drum", "Singing", "Choir", "Pop music", "Hip hop music",
             "Rock music", "Electronic music", "Background music", "Theme music", "Soundtrack music"],
    "机械/引擎": ["Engine", "Machine", "Mechanisms", "Power tool", "Drill", "Sawing", "Lathe", "Grinding", "Tools",
                 "Motorcycle", "Vehicle", "Car", "Lawn mower"],
    "人声反应": ["Laughter", "Applause", "Cheering", "Clapping", "Cough", "Sneeze", "Screaming", "Shout", "Battle cry"],
    "环境": ["Silence", "White noise", "Pink noise", "Wind", "Rain", "Outside, rural or natural", "Inside, small room",
             "Inside, large room or hall"],
}


def load_wav(path: Path):
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        sr = w.getframerate()
        ch = w.getnchannels()
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        # 简单线性重采样
        idx = np.linspace(0, len(x) - 1, int(len(x) * SR / sr))
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    return x


def _require(path, what, hint):
    if path.exists():
        return
    raise SystemExit(
        f"\n[缺少 {what}] {path}\n"
        f"  {hint}\n"
        "  说明：这两个文件不随仓库分发（YAMNet 模型约 15 MB）。\n"
        "  最省事的办法：先把它们放到上面的路径，再重跑本脚本。")


def load_classes():
    _require(CLASSES, "YAMNet 类目表",
             "下载 yamnet_class_map.csv（TensorFlow Hub 的 yamnet 模型包里有这个文件）。")
    names = [""] * 521
    with open(CLASSES, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                names[int(row["index"])] = row["display_name"]
            except Exception:
                continue
    return names


def group_of(label: str) -> str | None:
    for g, keys in GROUPS.items():
        for k in keys:
            if label == k or label.startswith(k):
                return g
    return None


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法: python sound_events.py <BV>")
    bv = sys.argv[1]
    wav = ensure_audio(bv)
    if not wav.exists():
        sys.exit(f"缺音频，先跑: python listen.py {bv}")

    x = load_wav(wav)
    names = load_classes()
    sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])

    # YAMNet 每帧 0.96s（hop 0.48s）
    scores = sess.run(None, {"waveform": x.astype(np.float32)})[0]
    hop = 0.48
    print(f"时长 {len(x)/SR:.0f}s｜帧 {len(scores)}｜每帧 {hop}s")

    timeline, counter = [], Counter()
    for i, row in enumerate(scores):
        top = int(np.argmax(row))
        t, conf = i * hop, float(row[top])
        g = group_of(names[top])
        if conf < 0.12:
            g, lab = "静音/低置信", "—"
        else:
            lab = names[top]
        counter[g or lab] += 1
        timeline.append((t, g or "其他", lab, conf))

    # 合并连续同类，输出区间
    segs = []
    for t, g, lab, conf in timeline:
        if segs and segs[-1][2] == g:
            segs[-1][1] = t + hop
            segs[-1][3].append(conf)
        else:
            segs.append([t, t + hop, g, [conf]])

    print("\n--- 声音时间段 ---")
    for s, e, g, cs in segs:
        if e - s < 0.9:
            continue
        print(f"  {int(s)//60}:{int(s)%60:02d}–{int(e)//60}:{int(e)%60:02d}  {g:<8} 置信 {sum(cs)/len(cs):.2f}")

    total = sum(counter.values()) or 1
    print("\n--- 占比 ---")
    for g, c in counter.most_common():
        print(f"  {g:<10} {c/total*100:5.1f}%")

    # 时间线图
    png = HERE / "audio_out" / bv / "events.png"
    W, H = 1600, 220
    img = Image.new("RGB", (W, H), (14, 17, 22))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 20)
    f2 = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 15)
    colors = {"说话": (74, 158, 255), "音乐": (168, 120, 255), "机械/引擎": (255, 117, 0),
              "人声反应": (255, 210, 90), "环境": (90, 200, 160), "静音/低置信": (50, 56, 66)}
    dur = len(x) / SR
    d.text((20, 14), f"{bv} 声音事件时间线", font=f1, fill=(245, 246, 248))
    left, right, top, bot = 20, W - 20, 50, H - 40
    for s, e, g, cs in segs:
        x0 = left + (right - left) * s / dur
        x1 = left + (right - left) * e / dur
        d.rectangle([x0, top, max(x0 + 1, x1), bot], fill=colors.get(g, (70, 70, 70)))
    for tsec in range(0, int(dur) + 1, 15):
        x = left + (right - left) * tsec / dur
        d.text((x - 10, bot + 6), f"{tsec//60}:{tsec%60:02d}", font=f2, fill=(120, 128, 142))
    lx = 20
    for g, col in colors.items():
        if counter.get(g, 0) == 0:
            continue
        d.rectangle([lx, H - 22, lx + 10, H - 12], fill=col)
        d.text((lx + 16, H - 24), g, font=f2, fill=(160, 168, 182))
        lx += 110
    img.save(png)
    print(f"\n时间线图: {png}")


if __name__ == "__main__":
    main()
