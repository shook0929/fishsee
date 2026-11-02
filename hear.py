"""hear.py —— 用阿里百炼 omni 模型"听懂"一段音频（不是只转写）。

用法：
  python hear.py <BV> --window 3:30-3:45                 # 默认问：有什么声音、在说什么、情绪
  python hear.py <BV> --window 0:00-0:15 --model qwen3-asr-flash   # 纯转写
  python hear.py <BV> --window 3:30-3:45 --prompt "这段配乐适合什么情绪的视频？"

输出：模型回答 + 本次请求 token 用量。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from audio_util import ensure_audio

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).parent
BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODEL = "qwen3.5-omni-plus"
DEFAULT_PROMPT = (
    "请仔细听这段音频，用中文回答三件事：\n"
    "1) 有哪些声音（人声/音乐/机械/环境音），分别出现在什么时候；\n"
    "2) 人声在说什么（尽量逐句）；\n"
    "3) 情绪和氛围怎么样（紧张/轻松/燃/平淡），配乐是什么类型的乐器或风格。"
)


def key() -> str:
    env = os.environ.get("DASHSCOPE_API_KEY")
    if env:
        return env.strip()
    p = Path(os.environ["APPDATA"]) / "dsh-secrets" / "dashscope.key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    sys.exit("没找到 DASHSCOPE_API_KEY")


def ts(s: str) -> float:
    if ":" in s:
        v = 0.0
        for p in s.split(":"):
            v = v * 60 + float(p)
        return v
    return float(s)


def clip(bv: str, start: float, dur: float) -> Path:
    src = ensure_audio(bv)
    if not src.exists():
        sys.exit(f"缺音频，先跑: python {HERE/'listen.py'} {bv}")
    out = HERE / "audio_out" / bv / f"clip_{int(start)}_{int(dur)}.wav"
    if not out.exists():
        r = subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                            "-ac", "1", "-ar", "16000", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.exit("切片失败: " + r.stderr[-200:])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bv")
    ap.add_argument("--window", required=True, help="如 3:30-3:45")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    a = ap.parse_args()

    s, e = a.window.split("-")
    start, dur = ts(s), max(1.0, ts(e) - ts(s))
    wav = clip(a.bv, start, dur)
    b64 = base64.b64encode(wav.read_bytes()).decode()

    body = {"model": a.model, "messages": [{"role": "user", "content": [
        {"type": "input_audio", "input_audio": {"data": f"data:audio/wav;base64,{b64}"}},
        {"type": "text", "text": a.prompt},
    ]}], "stream": False}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key()}",
                                          "Content-Type": "application/json"})
    print(f"片段 {a.window}（{dur:.0f}s，{wav.stat().st_size/1024:.0f} KB）｜模型 {a.model}\n")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            j = json.loads(r.read().decode())
    except Exception as ex:
        t = getattr(ex, "read", lambda: b"")()[:300].decode("utf-8", "replace")
        print("调用失败:", type(ex).__name__)
        print(t)
        return
    msg = j["choices"][0]["message"]
    print(msg.get("content") or "(空)")
    u = j.get("usage") or {}
    if u:
        print(f"\n[用量] 输入 {u.get('prompt_tokens')} / 输出 {u.get('completion_tokens')} tokens")


if __name__ == "__main__":
    main()
