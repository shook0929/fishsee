"""audio_util.py —— 公共音频获取层（补齐别人的环境就能直接跑）

解决四个坑：
1. 不再依赖 bilibili-api / 某个写死的 venv python —— 纯 HTTP + 系统 ffmpeg
2. 不再依赖"先跑过 listen.py" —— 任何脚本调用 ensure_audio() 会自动补齐
3. 支持登录态 cookie（不带 cookie 拿到的音画/弹幕会显著变少）
4. 路径不写死：缓存目录跟着脚本走

用法（其他脚本里）:
    from audio_util import ensure_audio
    wav = ensure_audio("BV1xx411c7mD")     # -> Path，16kHz 单声道 wav
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
CACHE = HERE / "audio_out"
SR = 16000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# cookie 优先级：环境变量 BILI_COOKIE > bili-cli 的凭证文件
def _cookie() -> str:
    env = os.environ.get("BILI_COOKIE")
    if env:
        return env.strip()
    cand = Path(os.environ.get("APPDATA", "")) / "bili-cli" / "credential.json"
    for p in (cand, Path(os.environ.get("APPDATA", "")) / "bili-cli" / "cookies.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # 常见结构：{"cookies": {"SESSDATA": "...", ...}} 或扁平字典
        ck = j.get("cookies") if isinstance(j.get("cookies"), dict) else j
        pairs = [f"{k}={v}" for k, v in ck.items()
                 if isinstance(v, (str, int)) and k in
                 ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4")]
        if pairs:
            return "; ".join(pairs)
    return ""


def _get_json(url: str, cookie: str = "") -> dict:
    headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def get_audio_url(bv: str) -> str:
    """view 拿 cid → playurl(fnval=16) → dash.audio 里码率最高的一条。"""
    cookie = _cookie()
    view = _get_json(
        "https://api.bilibili.com/x/web-interface/view?" + urlencode({"bvid": bv}), cookie)
    if view.get("code") != 0:
        raise RuntimeError(f"取视频信息失败: {view.get('message')}")
    cid = view["data"]["cid"]

    q = urlencode({"bvid": bv, "cid": cid, "fnval": 16, "fourk": 1})
    play = _get_json("https://api.bilibili.com/x/player/playurl?" + q, cookie)
    if play.get("code") != 0:
        raise RuntimeError(f"取播放地址失败: {play.get('message')}")

    dash = (play.get("data") or {}).get("dash") or {}
    audio = dash.get("audio") or []
    if not audio:
        raise RuntimeError("没有可用的音频流（可能是充电/大会员专属）")
    best = max(audio, key=lambda a: a.get("bandwidth", 0))
    return best["baseUrl"] or best.get("backupUrl", [""])[0]


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:  # imageio-ffmpeg 自带一份
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("找不到 ffmpeg：装 ffmpeg 或用 pip install imageio-ffmpeg")


def ensure_audio(bv: str, force: bool = False) -> Path:
    """确保 audio_out/<BV>/audio.wav 存在（16kHz 单声道），返回路径。"""
    d = CACHE / bv
    d.mkdir(parents=True, exist_ok=True)
    wav = d / "audio.wav"
    if wav.exists() and wav.stat().st_size > 1000 and not force:
        return wav

    url = get_audio_url(bv)
    cmd = [_ffmpeg(), "-y",
           "-headers", "Referer: https://www.bilibili.com/\r\n",
           "-user_agent", UA,
           "-i", url, "-vn", "-ac", "1", "-ar", str(SR), "-f", "wav", str(wav)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not wav.exists() or wav.stat().st_size < 1000:
        raise RuntimeError("音轨下载失败：" + (r.stderr or "")[-300:])
    print(f"[audio] 已缓存 {wav.relative_to(HERE)}  ({wav.stat().st_size/1024:.0f} KB)")
    return wav


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    print(ensure_audio(sys.argv[1]))
