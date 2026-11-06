#!/usr/bin/env python3
"""dm_peaks.py —— 用弹幕时间戳找视频的高光时刻。

一句话：B 站每条弹幕都带精确到秒的时间戳，按固定窗口分桶数一遍，
就得到「观众在哪一秒集体反应」的曲线。

用法:
    python dm_peaks.py BV1pGnn67EC2
    python dm_peaks.py BV1pGnn67EC2 --win 2 --top 5 --shift 2 --json out.json
    python dm_peaks.py --times times.json --duration 83      # 离线

它多做了一件容易被忽略的事：**把相邻的桶合并成「事件」**。
2 秒窗口会把同一个尖峰切成两格（比如 32 秒 50 条 + 34 秒 52 条，
其实是同一波反应），只看单桶排名会误判「哪个才是最大的」。

依赖:
    bili CLI（bili video danmaku）取数；或用 --times 喂本地时间戳
    times.json 两种格式都行:
        [1.05, 63.6, 68.17]                       # 纯时间戳
        [{"time": 1.05, "text": "爷青回"}, ...]    # 带文本（能出每格热评）

关于 --shift（默认 2 秒）:
    观众是先看到画面才打字，弹幕发出后还要在屏幕上滚 6~8 秒。
    所以统计出的峰值时间天然晚于「引发它的那一帧」。统一往前减 2 秒，
    峰值才落回画面上。经验值，不是精确值。

关于它的边界（写进片子里了，别忘）:
    弹幕只反映「还在看的人」的反应，测不出谁走了。
    某一段安静，可能是无聊，也可能是干货、大家都在认真看。
    所以它是高光定位器，不是流失曲线。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def fetch_with_bili(bv: str, limit: int = 5000) -> list[dict]:
    """带登录态取弹幕（条数最全）。不带登录态会少四成左右。"""
    r = subprocess.run(["bili", "video", "danmaku", bv, "--limit", str(limit)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"取弹幕失败（先看 bili auth status）：\n{(r.stdout or '')[-400:]}{(r.stderr or '')[-400:]}")
    data = json.loads(r.stdout.strip().splitlines()[-1])
    if not data.get("ok"):
        sys.exit(f"取弹幕失败：{data.get('error')}")
    return data["data"]["items"]


def load_times(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return raw
    return [{"time": t, "text": ""} for t in raw]


def bucketize(items: list[dict], win: float) -> tuple[Counter, dict[int, Counter], float]:
    counts: Counter = Counter()
    texts: dict[int, Counter] = defaultdict(Counter)
    last = 0.0
    for it in items:
        t = float(it.get("time") or 0)
        last = max(last, t)
        b = int(t // win)
        counts[b] += 1
        txt = (it.get("text") or "").strip()
        if txt:
            texts[b][txt] += 1
    return counts, texts, last


def merge_peaks(counts: Counter, win: float, top: int) -> list[list[int]]:
    """找出「一波一波」的峰值：桶条数超过 mean+1.5σ 算热点，
    相邻（允许隔一个冷桶）的热点合并成一个事件。返回 [[start_bucket, end_bucket], ...]
    """
    if not counts:
        return []
    vals = list(counts.values())
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    thresh = max(3.0, mean + 1.5 * var ** 0.5)

    hot = sorted(b for b, v in counts.items() if v >= thresh)
    if not hot:  # 太平了，退回单桶前 N
        hot = sorted(b for b, _ in counts.most_common(top))

    groups: list[list[int]] = []
    for b in hot:
        if groups and b - groups[-1][1] <= 2:
            groups[-1][1] = b
        else:
            groups.append([b, b])

    def total(g):
        return sum(counts.get(b, 0) for b in range(g[0], g[1] + 1))

    groups.sort(key=total, reverse=True)
    return groups[:top]


def analyze(items: list[dict], win: float, top: int, shift: float, duration: float | None):
    counts, texts, last = bucketize(items, win)
    total = sum(counts.values())
    dur = duration or (last if last else 0.0)
    density = round(total / dur, 2) if dur else 0.0

    events = []
    for lo_b, hi_b in merge_peaks(counts, win, top):
        c = sum(counts.get(b, 0) for b in range(lo_b, hi_b + 1))
        hot = Counter()
        for b in range(lo_b, hi_b + 1):
            hot.update(texts.get(b, {}))
        start = lo_b * win
        events.append({
            "start": round(start, 1),
            "end": round((hi_b + 1) * win, 1),
            "on_screen_at": round(max(0.0, start - shift), 1),
            "count": c,
            "pct": round(c / total * 100, 1) if total else 0.0,
            "per_sec": round(c / ((hi_b - lo_b + 1) * win), 1),
            "top_texts": [t for t, _ in hot.most_common(3)],
        })

    singles = [{
        "bucket_start": round(b * win, 1),
        "bucket_end": round((b + 1) * win, 1),
        "count": c,
        "on_screen_at": round(max(0.0, b * win - shift), 1),
    } for b, c in counts.most_common(max(top, 5))]

    return {
        "total": total,
        "duration": round(dur, 1),
        "density_per_sec": density,
        "window": win,
        "shift": shift,
        "events": events,
        "singles": singles,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", help="BV 号")
    ap.add_argument("--times", help="本地 times.json（离线模式）")
    ap.add_argument("--win", type=float, default=2.0, help="分桶秒数，默认 2")
    ap.add_argument("--top", type=int, default=5, help="返回几个事件，默认 5")
    ap.add_argument("--shift", type=float, default=2.0, help="峰值前移秒数，默认 2")
    ap.add_argument("--duration", type=float, help="视频时长（不传就用最后一条弹幕估）")
    ap.add_argument("--limit", type=int, default=5000, help="最多取多少条弹幕")
    ap.add_argument("--json", help="把结果写成 json")
    a = ap.parse_args()

    if a.times:
        items = load_times(Path(a.times))
    elif a.video:
        items = fetch_with_bili(a.video, a.limit)
    else:
        ap.error("需要 BV 号，或 --times times.json")

    res = analyze(items, a.win, a.top, a.shift, a.duration)

    print(f"弹幕 {res['total']} 条 · 时长约 {res['duration']:g}s · 平均 {res['density_per_sec']} 条/秒")
    print(f"（{a.win:g}s 窗口，相邻峰已合并成事件；画面对应 = 起点 − {a.shift:g}s）\n")
    print(f"{'#':<3}{'事件区间':<16}{'条数':<7}{'占比':<8}{'条/秒':<8}{'画面对应':<10}最热弹幕")
    for i, e in enumerate(res["events"], 1):
        span = f"{e['start']:g}s-{e['end']:g}s"
        hot = " / ".join(e["top_texts"])[:34]
        print(f"{i:<3}{span:<16}{e['count']:<7}{str(e['pct']) + '%':<8}"
              f"{e['per_sec']:<8}{str(e['on_screen_at']) + 's':<10}{hot}")

    print(f"\n单桶前五（看精确到哪一秒）")
    print(f"{'#':<3}{'时间':<14}{'条数':<7}{'画面对应'}")
    for i, s in enumerate(res["singles"][:5], 1):
        span = f"{s['bucket_start']:g}s-{s['bucket_end']:g}s"
        print(f"{i:<3}{span:<14}{s['count']:<7}{str(s['on_screen_at']) + 's'}")

    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写入 {a.json}")


if __name__ == "__main__":
    main()


