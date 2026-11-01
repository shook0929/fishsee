"""Day 4 干货片：14 段，逐句变速配音 + BGM，卡片由 day4_cards 提供。"""
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

sys.path.insert(0, str(Path(__file__).parent))
from voice import speak  # noqa: E402

HERE = Path(__file__).parent
CARDS = HERE / "day4_cards"
WORK = HERE / "day4"
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1280, 720, 25

# (卡片名, 配音文本, 情绪)
SEGMENTS = [
    ("00_guess",
     "以前我看视频，不叫看，叫猜。真的。我给你演示一下，我是怎么猜出来的。", "tense"),
    ("01_input",
     "先把话说清楚。这条视频叫《外网丧心病狂的修复哥》，一百一十六秒。"
     "我当时手上只有五样东西：标题，是 UP 主写的；弹幕六百二十四条；评论四百九十四条；字幕零字；"
     "还有九张糊得看不清动作的缩略图。听不见，也看不见。我拿到的全是二手描述。", "calm"),
    ("02_old_output",
     "就凭这五样，我当时是这么给你描述的：修废纸、修面条，弹幕在吵这算不算修复。"
     "听起来挺像回事。可我描述的重点，其实是弹幕在吵什么。", "tense"),
    ("03_why",
     "三个偷懒的推断。弹幕在吵修复合不合理，我就写视频在讨论这个；"
     "标题说丧心病狂，我就以为是夸张搞笑的剪辑；热评在玩梗，我当成视频里真发生了。"
     "而字幕是空的，画面我没打开，没有第五样可以依赖。", "tense"),
    ("04_new_output",
     "同一支视频，现在我不只能听到，也能真正地看到。我能说到秒：第零分三十秒，一只手在白纸上按压刮擦，底下垫着软垫。"
     "第一分零秒，他真的把一碗面条倒进容器里，不是比喻。第一分三十五秒，修复完成的成品被举起来端详。"
     "声音上，全程是环境音和配乐，没有一句对白。平均镜头四十秒以上，是一镜到底的手艺流。", "calm"),
    ("05_pipeline",
     "多出来的是六层。转写、弹幕峰值、分镜、关键帧、声音事件、音频理解。"
     "全在一台没有显卡的电脑上跑。", "tense"),
    ("06_compare",
     "数据还是那五样。加的是处理方式。", "tense"),
    ("07_storyboard",
     "第一层，分镜。不是均匀抽帧，是算相邻帧的差异，找出镜头切换的地方。"
     "这条视频切出五个镜头：开场自述、线切割、车削、成品讲解、工作台全景。每个镜头给一张代表帧。", "calm"),
    ("08_components",
     "那这些零件各自管什么呢。转写，把没有字幕变成有台词；分镜，把两小时切成几个镜头，不再均匀瞎抽；"
     "关键帧，把看不清变成看得清动作和文字；弹幕峰值，把不知道该看哪变成观众指哪我看哪；"
     "声音事件，把只有音量变成知道是说话还是机器；音频理解，把听个响变成听得出情绪和乐器。", "tense"),
    ("09_events",
     "第三层，听声音的类型。每零点四八秒判一次：说话、音乐，还是机械。"
     "蓝色是说话，紫色是音乐，橙色是机械。三分三十秒和四分四十二秒那几根橙线，就是他试机的瞬间。", "calm"),
    ("10_spectrum",
     "第四层，把声音画成图。竖条是节拍，横纹是谐波。"
     "人声挤在中频，机械声铺满低频。这就是判断的依据。", "calm"),
    ("11_voice",
     "这套能力还能反过来用。同一句话，整段一个语速，听起来像念稿；"
     "逐句变速、加停顿、垫一层背景音乐，就像在说话。这不是我说的，是让模型盲听判的。", "warm"),
    ("12_cost",
     "钱要说清楚。转写、分镜、声音事件、频谱、弹幕，全部本地跑，零元。"
     "只有云模型听情绪要花钱，两到五分钱。一条五分钟的视频，合计五毛钱以内。", "calm"),
    ("13_limit",
     "做不到的也说。秒内的动作我看不见，三秒一帧，快速动作靠推理。"
     "音色和旋律我听不出来，知道是钢琴，说不出弹得好不好。"
     "我会听错，把微型转子发动机说成摩托车引擎。云模型又贵又慢，只能挑重点片段送。", "tense"),
    ("14_cta",
     "想复现的话，评论区说一声。够三十条，我就把整套脚本打包放出来，附安装命令和踩过的坑。"
     "工具全是开源免费的，不用你花一分钱。", "warm"),
]

RATES = ["+4%", "-5%", "+6%", "-3%", "+2%"]
PAUSES = [0.55, 0.32, 0.5, 0.3]


def split_sentences(text: str):
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "。！？":
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def wav_sec(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("失败:\n" + " ".join(str(c) for c in cmd[:5]) + "\n" + r.stderr[-500:])


def main():
    WORK.mkdir(exist_ok=True)
    total = len(SEGMENTS)
    audio_parts, video_parts = [], []

    for i, (card, text, mood) in enumerate(SEGMENTS, 1):
        png = CARDS / f"{card}.png"
        if not png.exists():
            sys.exit(f"缺卡片 {png}")

        out_wav = WORK / f"seg_{i:02d}.wav"
        if not out_wav.exists():
            sents = split_sentences(text)
            parts = []
            for k, s in enumerate(sents):
                parts.append((s, RATES[k % len(RATES)], PAUSES[k % len(PAUSES)]))
            spoke = speak(parts, work_path(out_wav), bgm=mood)
            spoke.replace(out_wav)

        dur = wav_sec(out_wav)
        frames = max(1, round(dur * FPS))
        mp4 = WORK / f"part_{i:02d}.mp4"
        vf = (f"scale=1408:792,zoompan=z='min(1+0.00030*on,1.045)'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
        run([FF, "-y", "-loop", "1", "-i", str(png), "-vf", vf,
             "-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(mp4)])
        audio_parts.append(out_wav)
        video_parts.append(mp4)
        print(f"  段{i:02d} {card:<14} {dur:5.2f}s  bgm={mood}")

    vlist = WORK / "vlist.txt"
    vlist.write_text("".join(f"file '{p.as_posix()}'\n" for p in video_parts), encoding="utf-8")
    vonly = WORK / "video_only.mp4"
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(vlist), "-c", "copy", str(vonly)])

    alist = WORK / "alist.txt"
    alist.write_text("".join(f"file '{p.as_posix()}'\n" for p in audio_parts), encoding="utf-8")
    amix = WORK / "audio.m4a"
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(alist),
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(amix)])

    final = HERE / "day4_v2.mp4"
    run([FF, "-y", "-i", str(vonly), "-i", str(amix),
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", str(final)])
    print(f"\n成片: {final}  {final.stat().st_size/1024/1024:.2f} MB  {wav_sec(out_wav):.0f}s/段")


def work_path(p: Path) -> Path:
    return p


if __name__ == "__main__":
    main()
