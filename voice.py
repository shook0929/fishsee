"""voice.py —— 更像人说话的 TTS：逐句变速 + 句间停顿 + 可选 BGM。

为什么这样做：edge-tts 整段只支持统一 rate，听起来像念稿。逐句设不同 rate、
句间插不同长度静音，能做出"想事情时停顿"的节奏（已用 omni 模型盲听验证：
从"念稿"变为"像在说话"）。

用法（作为库）：
    from voice import speak
    speak([("第一句。", "+2%", 0.55), ("第二句，", "-8%", 0.35)], out_wav)

命令行：
    python voice.py out.wav "第一句|+2%|0.5" "第二句|-6%|0.3"
    python voice.py out.wav --bgm calm "第一句|+2%|0.5" ...
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = "zh-CN-XiaoxiaoNeural"
SR = 22050


def _tts(text: str, rate: str, path: Path) -> None:
    mp3 = path.with_suffix(".mp3")
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOICE,
                    f"--rate={rate}", "--text", text, "--write-media", str(mp3)],
                   check=True, capture_output=True)
    subprocess.run([FF, "-y", "-i", str(mp3), "-ar", str(SR), "-ac", "1", str(path)],
                   check=True, capture_output=True)
    mp3.unlink(missing_ok=True)


def speak(parts, out: Path, bgm: str | None = None, bgm_db: str = "-16dB") -> Path:
    """parts: [(text, rate, pause_after_seconds), ...]"""
    out = Path(out).resolve()
    work = out.parent / (out.stem + "_parts")
    work.mkdir(parents=True, exist_ok=True)

    pieces = []
    for i, (text, rate, pause) in enumerate(parts):
        wav = work / f"v{i}.wav"
        _tts(text, rate, wav)
        pieces.append(wav)
        if pause and pause > 0:
            gap = work / f"g{i}.wav"
            subprocess.run([FF, "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono",
                            "-t", str(pause), str(gap)], check=True, capture_output=True)
            pieces.append(gap)

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-ar", str(SR), "-ac", "1", str(out)], check=True, capture_output=True)

    if bgm:
        from bgm import make, save  # noqa: WPS433
        import wave
        with wave.open(str(out), "rb") as w:
            dur = w.getnframes() / w.getframerate()
        pad = out.parent / f"_bgm_{bgm}.wav"
        save(pad, make(dur, bgm))
        mixed = out.with_name(out.stem + "_mix.wav")
        subprocess.run([FF, "-y", "-i", str(out), "-i", str(pad),
                        "-filter_complex",
                        f"[1:a]volume={bgm_db}[b];[0:a][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[m]",
                        "-map", "[m]", "-ar", str(SR), "-ac", "1", str(mixed)],
                       check=True, capture_output=True)
        pad.unlink(missing_ok=True)
        return mixed
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("lines", nargs="+", help='每句格式 "文本|rate|停顿秒"，如 "你好。|+2%|0.5"')
    ap.add_argument("--bgm", default=None, choices=["calm", "warm", "tense"])
    a = ap.parse_args()

    parts = []
    for ln in a.lines:
        bits = ln.split("|")
        text = bits[0]
        rate = bits[1] if len(bits) > 1 else "+0%"
        pause = float(bits[2]) if len(bits) > 2 else 0.3
        parts.append((text, rate, pause))
    out = speak(parts, Path(a.out), bgm=a.bgm)
    print("输出:", out)


if __name__ == "__main__":
    main()
