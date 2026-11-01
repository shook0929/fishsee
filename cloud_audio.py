"""cloud_audio.py —— 阿里云百炼音频调用（OpenAI 兼容端点）。

用法：
  python cloud_audio.py <BV> --window 3:30-3:45 [--model qwen3-asr-flash] [--prompt "..."]
  python cloud_audio.py --selftest                 # 只检查 key 与连通性，不花钱

需要环境变量或凭证库中的 DASHSCOPE_API_KEY。
音频会自动从 video/audio_out/<BV>/audio.wav 切出指定片段（16kHz 单声道 wav）。
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import yaml

HERE = Path(__file__).parent
BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-asr-flash"


def get_key() -> str | None:
    import os
    k = os.environ.get("DASHSCOPE_API_KEY")
    if k:
        return k
    import os
    kf = Path(os.environ["APPDATA"]) / "dsh-secrets" / "dashscope.key"
    if kf.exists():
        return kf.read_text(encoding="utf-8").strip()
    cred = Path.home() / ".dsh" / ".credentials.yaml"
    if cred.exists():
        try:
            refs = yaml.safe_load(cred.read_text(encoding="utf-8")).get("refs", {})
            return refs.get("DASHSCOPE_API_KEY")
        except Exception:
            return None
    return None


def parse_ts(s: str) -> float:
    if ":" in s:
        v = 0.0
        for p in s.split(":"):
            v = v * 60 + float(p)
        return v
    return float(s)


def cut_audio(bv: str, start: float, dur: float) -> Path:
    src = HERE / "audio_out" / bv / "audio.wav"
    if not src.exists():
        sys.exit(f"缺音频，先跑: python {HERE/'listen.py'} {bv}")
    out = HERE / "audio_out" / bv / f"clip_{int(start)}_{int(dur)}.wav"
    if not out.exists():
        r = subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                            "-ac", "1", "-ar", "16000", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.exit("切片失败: " + r.stderr[-300:])
    return out


def call(model: str, wav: Path, prompt: str | None, key: str, temperature: float = 0.1) -> str:
    b64 = base64.b64encode(wav.read_bytes()).decode()
    content = [{
        "type": "input_audio",
        "input_audio": {"data": f"data:audio/wav;base64,{b64}"},
    }]
    if prompt:
        # 系统/指令提示放前面，模型按指令理解音频
        content.insert(0, {"type": "text", "text": prompt})
    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "temperature": temperature, "stream": False}
    req = urllib.request.Request(
        f"{BASE}/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read().decode())
    return j["choices"][0]["message"]["content"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bv", nargs="?")
    ap.add_argument("--window", default=None, help="如 3:30-3:45")
    ap.add_argument("--dur", type=float, default=15.0, help="窗口时长（秒），默认 15")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default=None, help="给音频理解的指令")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    key = get_key()
    if a.selftest or not key:
        print("DASHSCOPE_API_KEY:", "已配置" if key else "未配置")
        if not key:
            print("请到 https://bailian.console.aliyun.com/ 开通模型服务并创建 API Key，")
            print("然后设置环境变量 DASHSCOPE_API_KEY=sk-xxx（或告诉我，我写进凭证库）。")
        if not a.bv:
            return
    if not a.bv:
        sys.exit("需要 BV 号")

    if a.window:
        s, e = a.window.split("-")
        start, dur = parse_ts(s), max(1.0, parse_ts(e) - parse_ts(s))
    else:
        start, dur = 0.0, a.dur

    wav = cut_audio(a.bv, start, dur)
    print(f"片段: {wav.name}  {wav.stat().st_size/1024:.0f} KB  {dur:.0f}s")
    if not key:
        print("（无 key，跳过请求）")
        return
    try:
        out = call(a.model, wav, a.prompt, key)
        print("\n--- 结果 ---")
        print(out)
    except Exception as e:
        txt = getattr(e, "read", lambda: b"")()
        print("调用失败:", type(e).__name__, str(e)[:120])
        print("返回体:", txt[:400].decode("utf-8", "replace"))


if __name__ == "__main__":
    main()
