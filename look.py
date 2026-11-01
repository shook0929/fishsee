"""look.py —— 看得更像人：按「弹幕峰值 + 说话密度 + 时间覆盖」挑关键帧。

用法：python look.py <BV号> [帧数]
输出：一张带时间标注的高清拼图 + 每帧附近的台词，路径与摘要打到 stdout。
"""
from __future__ import annotations

import json
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from pathlib import Path

MIN_GAP = 5.0


def bili(*args: str) -> dict:
    r = subprocess.run(["bili", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "error": {"message": r.stdout[-300:] or r.stderr[-300:]}}


def info(bv: str) -> dict:
    r = bili("video", "info", bv)
    return r.get("data", {}) if r.get("ok") else {}


def peaks(bv: str, n: int = 6) -> list[tuple[float, int, str]]:
    r = bili("video", "danmaku", bv, "--peaks", str(n))
    out = []
    if r.get("ok"):
        for p in (r["data"].get("peaks") or []):
            t = p.get("time")
            if isinstance(t, (int, float)):
                top = "、".join(p.get("top") or [])[:24]
                out.append((float(t), int(p.get("count") or 0), top))
    return out


def transcript(bv: str) -> list[dict]:
    r = bili("video", "transcribe", bv)
    if r.get("ok"):
        return r["data"].get("items") or []
    return []


def pick(duration: float, pk, segs, want: int) -> list[float]:
    cand: list[tuple[float, float]] = []          # (time, score)
    for t, cnt, _ in pk:
        cand.append((t, 3.0 + min(cnt, 120) / 40.0))
    for s in segs:
        t = s.get("from")
        if isinstance(t, (int, float)):
            dur = float(s.get("to", t) or t) - t
            cand.append((float(t), 1.6 + min(dur, 12) / 6.0))
    if duration > 0:                               # 铺一层均匀覆盖，防止全挤在一处
        step = duration / (want + 1)
        for i in range(1, want + 1):
            cand.append((i * step, 0.9))

    cand.sort(key=lambda x: -x[1])
    chosen: list[float] = []
    for t, _ in cand:
        if duration and not (0.5 <= t <= duration - 0.4):
            continue
        if all(abs(t - c) >= MIN_GAP for c in chosen):
            chosen.append(round(t, 1))
        if len(chosen) >= want:
            break
    return sorted(chosen)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法: python look.py <BV号> [帧数, 默认12]")
    bv = sys.argv[1]
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    meta = info(bv)
    duration = float(meta.get("duration") or 0)
    pk = peaks(bv)
    segs = transcript(bv)
    times = pick(duration, pk, segs, want)
    if not times:
        sys.exit("没挑出时间点")

    outdir = Path(__file__).parent / "frames_out" / bv
    outdir.mkdir(parents=True, exist_ok=True)
    args = ["video", "frames", bv, "-q", "hd", "--danmaku", "--sheet", "--out", str(outdir)]
    for t in times:
        args += ["--at", f"{t:.1f}"]
    r = bili(*args)
    if not r.get("ok"):
        sys.exit("抽帧失败: " + json.dumps(r.get("error", {}), ensure_ascii=False)[:300])

    data = r["data"]
    sheet = data.get("sheet") or data.get("sheet_path")
    print(f"标题: {meta.get('title', '?')}  |  {duration:.0f}s  |  选了 {len(times)} 帧")
    print(f"拼图: {sheet}")

    print("\n--- 每帧位置与当时的台词 ---")
    for t in times:
        seg = next((s for s in segs if s.get("from", 0) <= t <= s.get("to", 0)), None)
        line = (seg or {}).get("content", "").strip()[:48]
        near = [(pt, cnt, top) for pt, cnt, top in pk if abs(pt - t) <= 8]
        mark = f"  ⚡弹幕{near[0][1]}条「{near[0][2]}」" if near else ""
        print(f"  {int(t)//60}:{int(t)%60:02d}  {line}{mark}")


if __name__ == "__main__":
    main()
