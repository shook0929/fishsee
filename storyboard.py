"""storyboard.py —— 故事板式看视频：按镜头分配帧，快切镜头细粒度切分。

借鉴 dsh-video-storyboard 的思路：人类记不住快速切换的那几帧，所以对"快切镜头"
多给几帧，对静止长镜头只给一帧。

用法: python storyboard.py <BV> [--budget 14] [--cols 4]
输出: 一张带镜头编号/时间/快切标记的故事板拼图 + 分镜表
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
CELL_W, CELL_H = 480, 270
PAD = 10


def bili(*args: str) -> dict:
    r = subprocess.run(["bili", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "error": {"message": (r.stdout or r.stderr)[-300:]}}


def ahash(path: Path, size: int = 8):
    im = Image.open(path).convert("L").resize((size, size), Image.LANCZOS)
    px = list(im.getdata())
    avg = sum(px) / len(px)
    return [1 if v > avg else 0 for v in px]


def ham(a, b) -> int:
    return sum(x != y for x, y in zip(a, b))


def fmt(t: float) -> str:
    return f"{int(t)//60}:{int(t)%60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bv")
    ap.add_argument("--budget", type=int, default=14, help="总帧数预算")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--every", type=float, default=6.0, help="初扫间隔（秒）")
    a = ap.parse_args()

    # 1) 初扫
    tmp = HERE / "frames_out" / a.bv / "sb_scan"
    tmp.mkdir(parents=True, exist_ok=True)
    r = bili("video", "frames", a.bv, "--every", str(a.every), "-q", "preview", "--no-sheet", "--out", str(tmp))
    if not r.get("ok"):
        r = bili("video", "frames", a.bv, "--every", str(a.every * 1.5), "-q", "hd", "--no-sheet", "--out", str(tmp))
    if not r.get("ok"):
        sys.exit("初扫失败: " + json.dumps(r.get("error", {}), ensure_ascii=False)[:200])

    frames = sorted((float(f.get("actual_time") or f["time"]), Path(f["path"]))
                    for f in r["data"]["frames"] if Path(f["path"]).exists())
    if len(frames) < 3:
        sys.exit("帧太少")

    # 2) 分镜 + 镜头内运动强度
    shots = []          # [start, end, [times], motion]
    prev = None
    for t, p in frames:
        h = ahash(p)
        if prev is None:
            shots.append([t, t, [t], 0.0])
        else:
            d = ham(h, prev[1]) / 64.0
            if d >= 0.30:
                shots.append([t, t, [t], d])
            else:
                cur = shots[-1]
                cur[1] = t
                cur[2].append(t)
                cur[3] = max(cur[3], d)
        prev = (t, h)

    # 3) 分配帧预算：先每镜 1 帧，剩余按运动强度从高到低加
    alloc = [1] * len(shots)
    remain = max(0, a.budget - len(shots))
    order = sorted(range(len(shots)), key=lambda i: -shots[i][3])
    k = 0
    while remain > 0 and order:
        i = order[k % len(order)]
        if alloc[i] < min(4, max(1, len(shots[i][2]))):
            alloc[i] += 1
            remain -= 1
        k += 1
        if k > 500:
            break

    # 4) 每个镜头内按分配数量取中位/等距时间点
    picks = []
    for idx, (s, e, times, motion) in enumerate(shots):
        n = alloc[idx]
        if n == 1:
            pts = [(s + e) / 2]
        else:
            span = max(0.1, e - s)
            pts = [s + span * (j + 0.5) / n for j in range(n)]
        fast = motion >= 0.42 and len(times) >= 2
        for j, t in enumerate(pts):
            picks.append(dict(shot=idx + 1, sub=f"{j+1}/{n}", t=round(t, 1),
                              fast=fast, dur=e - s, motion=motion))

    print(f"镜头 {len(shots)} 个｜帧 {len(picks)} 张｜总预算 {a.budget}")
    for p in picks:
        tag = "[快切]" if p["fast"] else "  长镜"
        print(f"  #{p['shot']:02d} {tag} {fmt(p['t']):>6}  ({p['sub']})  镜头长 {p['dur']:.0f}s  运动 {p['motion']:.2f}")

    # 5) 取高清帧
    outdir = HERE / "frames_out" / a.bv / "sb_final"
    outdir.mkdir(parents=True, exist_ok=True)
    args = ["video", "frames", a.bv, "-q", "hd", "--no-sheet", "--out", str(outdir)]
    for p in picks:
        args += ["--at", f"{p['t']:.1f}"]
    r2 = bili(*args)
    if not r2.get("ok"):
        sys.exit("取帧失败: " + json.dumps(r2.get("error", {}), ensure_ascii=False)[:200])
    got = {round(float(f.get("actual_time") or f["time"]), 0): Path(f["path"]) for f in r2["data"]["frames"]}

    def nearest(t):
        if not got:
            return None
        k = min(got, key=lambda x: abs(x - t))
        return got[k]

    # 6) 拼故事板
    cols = a.cols
    rows = (len(picks) + cols - 1) // cols
    W = cols * (CELL_W + PAD) + PAD
    H = rows * (CELL_H + 34 + PAD) + PAD + 46
    sheet = Image.new("RGB", (W, H), (12, 15, 20))
    d = ImageDraw.Draw(sheet)
    fb = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 20)
    fs = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 15)
    d.text((PAD, 12), f"{a.bv} 故事板｜{len(shots)} 镜 / {len(picks)} 帧（橙色边框 = 快切镜头，给了多帧）",
           font=fb, fill=(240, 242, 246))

    for i, p in enumerate(picks):
        img_p = nearest(p["t"])
        if not img_p or not img_p.exists():
            continue
        x = PAD + (i % cols) * (CELL_W + PAD)
        y = 46 + (i // cols) * (CELL_H + 34 + PAD)
        im = Image.open(img_p).convert("RGB").resize((CELL_W, CELL_H), Image.LANCZOS)
        sheet.paste(im, (x, y))
        border = (255, 117, 0) if p["fast"] else (48, 56, 70)
        d.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline=border, width=3)
        label = f"#{p['shot']:02d} {p['sub']}  {fmt(p['t'])}" + ("  [快切]" if p["fast"] else "")
        d.text((x + 6, y + CELL_H + 4), label, font=fs, fill=(200, 206, 216))

    out = HERE / "frames_out" / a.bv / "storyboard.jpg"
    sheet.save(out, quality=88)
    print(f"\n故事板: {out}")


if __name__ == "__main__":
    main()
