"""scene.py —— 自动分镜：预览帧算哈希 → 找镜头切换 → 每镜头取代表帧出高清拼图。

用法：
  python scene.py <BV> [--max 14] [--thresh 0.30]
输出：镜头分段表（时长/节奏）+ 代表帧高清拼图路径
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

from PIL import Image

MIN_SHOT = 3.0          # 短于此不算独立镜头
PREVIEW_EVERY = 4.0     # 预览帧采样间隔（秒，B站会吸附到可用缩略图）


def bili(*args: str) -> dict:
    r = subprocess.run(["bili", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "error": {"message": (r.stdout or r.stderr)[-300:]}}


def ahash(path: Path, size: int = 8) -> list[int]:
    im = Image.open(path).convert("L").resize((size, size), Image.LANCZOS)
    px = list(im.getdata())
    avg = sum(px) / len(px)
    return [1 if v > avg else 0 for v in px]


def ham(a: list[int], b: list[int]) -> int:
    return sum(x != y for x, y in zip(a, b))


def fmt(t: float) -> str:
    return f"{int(t)//60}:{int(t)%60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bv")
    ap.add_argument("--max", type=int, default=14, help="最多出多少张代表帧")
    ap.add_argument("--thresh", type=float, default=0.30, help="切镜阈值（汉明距离/64）")
    a = ap.parse_args()

    tmp = Path(__file__).parent / "frames_out" / a.bv / "preview"
    tmp.mkdir(parents=True, exist_ok=True)
    r = bili("video", "frames", a.bv, "--every", str(PREVIEW_EVERY), "-q", "preview",
             "--no-sheet", "--out", str(tmp))
    if not r.get("ok"):
        # 预览缩略图取不到时，退回用 ffmpeg 抽高清帧（更慢但可靠）
        every = max(PREVIEW_EVERY * 2, 6.0)
        print(f"预览帧不可用（{r.get('error', {}).get('message', '')[:30]}），改用 ffmpeg 抽帧，间隔 {every:.0f}s")
        r = bili("video", "frames", a.bv, "--every", str(every), "-q", "hd",
                 "--no-sheet", "--out", str(tmp))
    if not r.get("ok"):
        sys.exit("抽帧失败: " + json.dumps(r.get("error", {}), ensure_ascii=False)[:300])

    frames = []
    for f in r["data"]["frames"]:
        p = Path(f["path"])
        if p.exists():
            frames.append((float(f.get("actual_time") or f["time"]), p))
    frames.sort()
    if len(frames) < 3:
        sys.exit("帧太少，无法分镜")

    # 逐帧算哈希，找切点；同时丢掉和上一帧几乎相同的（B站缩略图会重复）
    shots: list[tuple[float, float]] = []      # (start, end)
    hashes, kept = [], []
    for t, p in frames:
        h = ahash(p)
        if hashes:
            d = ham(h, hashes[-1]) / 64.0
            if d < 0.02:                       # 重复帧，跳过
                shots[-1] = (shots[-1][0], t)
                continue
            if d >= a.thresh:
                shots.append((t, t))           # 新镜头
            else:
                shots[-1] = (shots[-1][0], t)
        else:
            shots.append((t, t))
        hashes.append(h)
        kept.append((t, p))

    # 太短的镜头并入前一个
    merged = []
    for s, e in shots:
        if merged and (e - s) < MIN_SHOT:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    # 均匀抽代表镜头（超过上限时按等距保留，保证开头结尾在）
    if len(merged) > a.max:
        idx = [round(i * (len(merged) - 1) / (a.max - 1)) for i in range(a.max)]
        picks = [merged[i] for i in sorted(set(idx))]
    else:
        picks = merged

    times = [round((s + e) / 2, 1) for s, e in picks]
    lens = [e - s for s, e in picks]
    avg = sum(lens) / len(lens) if lens else 0
    print(f"共检出 {len(merged)} 个镜头，取 {len(picks)} 个代表帧；平均镜头 {avg:.1f}s")
    for (s, e), t in zip(picks, times):
        print(f"  {fmt(s)}–{fmt(e)}  ({e-s:4.1f}s)  代表帧 @ {fmt(t)}")

    outdir = Path(__file__).parent / "frames_out" / a.bv / "scenes"
    outdir.mkdir(parents=True, exist_ok=True)
    args = ["video", "frames", a.bv, "-q", "hd", "--danmaku", "--sheet", "--out", str(outdir)]
    for t in times:
        args += ["--at", f"{t:.1f}"]
    r2 = bili(*args)
    if not r2.get("ok"):
        sys.exit("高清抽帧失败: " + json.dumps(r2.get("error", {}), ensure_ascii=False)[:300])
    d = r2["data"]
    print(f"\n拼图: {d.get('sheet') or d.get('sheet_path')}")


if __name__ == "__main__":
    main()
