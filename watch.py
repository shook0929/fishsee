"""watch.py —— 三段式"看视频"：粗扫 → 密看指定时段 → 可选的视觉模型预读。

用法示例：
  python watch.py BV1BN411i7wB                  # 粗扫 12 帧
  python watch.py BV1BN411i7wB --window 1:00-1:40 --step 3   # 密看 1:00-1:40，每 3 秒一帧
  python watch.py BV1BN411i7wB --vlm            # 粗扫后再让 GLM-4.6V 描述一遍
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import urllib.request

import yaml

MIN_GAP = 3.0
VLM_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
VLM_MODEL = "glm-4.6v"


def bili(*args: str) -> dict:
    r = subprocess.run(["bili", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "error": {"message": (r.stdout or r.stderr)[-300:]}}


def parse_ts(s: str) -> float:
    s = s.strip()
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        v = 0.0
        for p in parts:
            v = v * 60 + p
        return v
    return float(s)


def fmt(t: float) -> str:
    return f"{int(t)//60}:{int(t)%60:02d}"


def meta_of(bv: str) -> dict:
    r = bili("video", "info", bv)
    return r.get("data", {}) if r.get("ok") else {}


def peaks_of(bv: str, n: int = 6):
    r = bili("video", "danmaku", bv, "--peaks", str(n))
    out = []
    if r.get("ok"):
        for p in (r["data"].get("peaks") or []):
            t = p.get("time")
            if isinstance(t, (int, float)):
                out.append((float(t), int(p.get("count") or 0), "、".join(p.get("top") or [])[:20]))
    return out


def transcript_of(bv: str):
    r = bili("video", "transcribe", bv)
    return r["data"].get("items") or [] if r.get("ok") else []


def pick_uniform(duration: float, pk, segs, want: int):
    cand = [(t, 3.0 + min(c, 120) / 40) for t, c, _ in pk]
    cand += [(s["from"], 1.6 + min(float(s.get("to", s["from"])) - s["from"], 12) / 6)
             for s in segs if isinstance(s.get("from"), (int, float))]
    if duration > 0:
        step = duration / (want + 1)
        cand += [(i * step, 0.9) for i in range(1, want + 1)]
    cand.sort(key=lambda x: -x[1])
    chosen = []
    for t, _ in cand:
        if duration and not (0.5 <= t <= duration - 0.4):
            continue
        if all(abs(t - c) >= max(MIN_GAP, 5.0) for c in chosen):
            chosen.append(round(t, 1))
        if len(chosen) >= want:
            break
    return sorted(chosen)


def window_times(a: float, b: float, step: float):
    out, t = [], a
    while t <= b:
        out.append(round(t, 1))
        t += step
    return out


def grab(bv: str, times: list[float], tag: str):
    outdir = Path(__file__).parent / "frames_out" / bv / tag
    outdir.mkdir(parents=True, exist_ok=True)
    args = ["video", "frames", bv, "-q", "hd", "--danmaku", "--sheet", "--out", str(outdir)]
    for t in times:
        args += ["--at", f"{t:.1f}"]
    r = bili(*args)
    if not r.get("ok"):
        sys.exit("抽帧失败: " + json.dumps(r.get("error", {}), ensure_ascii=False)[:300])
    d = r["data"]
    return d.get("sheet") or d.get("sheet_path")


def vlm_describe(sheet: str, prompt: str) -> str:
    refs = yaml.safe_load((Path.home() / ".dsh" / ".credentials.yaml").read_text(encoding="utf-8"))["refs"]
    key = refs["ZAI_CODING_CN_API_KEY"]
    b64 = base64.b64encode(Path(sheet).read_bytes()).decode()
    body = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
        "max_tokens": 700,
    }
    req = urllib.request.Request(VLM_URL, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read().decode())
    return j["choices"][0]["message"].get("content", "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bv")
    ap.add_argument("--frames", type=int, default=12, help="粗扫帧数")
    ap.add_argument("--window", help="密看时段，如 1:00-1:40")
    ap.add_argument("--step", type=float, default=3.0, help="密看间隔（秒）")
    ap.add_argument("--vlm", action="store_true", help="让视觉模型预读拼图")
    a = ap.parse_args()

    meta = meta_of(a.bv)
    duration = float(meta.get("duration") or 0)
    pk, segs = peaks_of(a.bv), transcript_of(a.bv)

    if a.window:
        s, e = a.window.split("-")
        times = window_times(parse_ts(s), parse_ts(e), a.step)
        tag = f"win_{int(parse_ts(s))}_{int(parse_ts(e))}"
    else:
        times = pick_uniform(duration, pk, segs, a.frames)
        tag = "scan"

    sheet = grab(a.bv, times, tag)
    print(f"标题: {meta.get('title', '?')} | {duration:.0f}s")
    print(f"选帧 {len(times)} 个: " + ", ".join(fmt(t) for t in times))
    print(f"拼图: {sheet}")

    print("\n--- 帧 ↔ 台词 ↔ 弹幕 ---")
    for t in times:
        seg = next((s for s in segs if s.get("from", 0) - 0.5 <= t <= s.get("to", 0) + 0.5), None)
        line = (seg or {}).get("content", "").strip()[:40]
        near = [p for p in pk if abs(p[0] - t) <= 6]
        mark = f"  ⚡{near[0][1]}条「{near[0][2]}」" if near else ""
        print(f"  {fmt(t)}  {line}{mark}")

    if a.vlm:
        print("\n--- 视觉模型预读 ---")
        try:
            print(vlm_describe(sheet, "这是视频截帧拼图（按时间顺序排列，左上到右下）。"
                                     "请用 4-6 句话说清：画面里在做什么、人物/物体、场景变化、以及视频的整体叙事。"))
        except Exception as e:
            print("视觉模型失败:", type(e).__name__, str(e)[:150])


if __name__ == "__main__":
    main()
