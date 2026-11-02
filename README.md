# 让 AI 真正"看"视频 —— 工具包

一套在**没有显卡的普通 Windows 电脑**上跑的看片流水线，全程免费（只有可选的一层要几分钱）。

配套视频：B 站《AI 真的能「看」视频吗？大肥鱼拆了六层流水线》

## 它解决什么

以前 AI"看"视频，拿到的只有：标题、简介、字幕、热评、弹幕、9 张缩略图。
**没字幕就失明，动作全靠脑补，说不出"第几分几秒发生了什么"。**

这套东西补上六层：**转写 → 弹幕峰值 → 分镜 → 关键帧 → 声音事件 → 音频理解**。

## 环境准备

```
# 1) Python 3.10+（不要用 3.8，很多库不兼容）
# 2) 建立一个干净环境
python -m venv .venv
.venv\Scripts\activate
pip install pillow numpy onnxruntime edge-tts imageio-ffmpeg pyyaml

# 3) 下载 ffmpeg（imageio-ffmpeg 自带，或自己装）
# 4) B 站数据：本包自带 audio_util.py（纯 HTTP，不需要 bilibili-api）
#    想拿弹幕/字幕再装：uv tool install bili-agent && bili auth login
```

## 六个脚本

| 脚本 | 作用 | 依赖 |
| --- | --- | --- |
| `listen.py <BV>` | 下载音轨 + 画音量包络 + 标出高能时刻 | ffmpeg |
| `hear.py <BV> --window 3:30-3:45` | 把一段音频发给大模型"听懂"（情绪/乐器/语气） | 通义百炼 omni（可选） |
| `scene.py <BV>` | aHash 分镜，自动找镜头切换点 | pillow, numpy |
| `storyboard.py <BV>` | 生成故事板：几个镜头 + 每镜代表帧 | pillow |
| `sound_events.py <BV>` | YAMNet 每 0.48 秒判一次：说话/音乐/机械 | onnxruntime + yamnet.onnx |
| `bgm.py out.wav --mood calm` | 用代码合成背景音乐（免版权） | numpy |

配音那两个：

| 脚本 | 作用 |
| --- | --- |
| `voice.py` | 逐句不同语速 + 句间停顿 + 垫 BGM，做"像在说话"的配音 |
| `build_day4.py` | 完整成片范例：卡片 + 配音 + ffmpeg 合成 |

## 最小可跑示例

```bash
# 1) 拿到音轨和音量包络
python listen.py BV1BN411i7wB

# 2) 自动分镜，出故事板
python scene.py BV1BN411i7wB
python storyboard.py BV1BN411i7wB --budget 10

# 3) 听声音类型（需要先下载 yamnet.onnx，见下）
python sound_events.py BV1BN411i7wB

# 4) 让大模型听懂某一段（需要 API key，可跳过）
python hear.py BV1BN411i7wB --window 3:30-3:45
```

## 需要的模型文件

| 文件 | 大小 | 从哪来 |
| --- | --- | --- |
| `yamnet.onnx` | ~15 MB | TF Hub 的 YAMNet 转 ONNX：下载 `yamnet` → `python -m tf2onnx.convert --saved-model ... --output yamnet.onnx`；或直接找现成的 ONNX 版本 |
| `yamnet_class_map.csv` | ~50 KB | 与 YAMNet 同级目录 |

没有它也能跑，只是少了"声音事件"这一层。

## 音频理解那一层（可选，要花钱）

用阿里百炼的 `qwen3.5-omni-plus`：

```python
# 15 秒音频 ≈ 150 input token ≈ 不到一分钱
# 5 分钟视频全听完 ≈ ¥0.02~0.05
```

廉价的替代：`qwen3-asr-flash` 只做转写（更便宜）。

## 一定要带登录态（实测 4.6 倍差距）

同一条视频的弹幕：**不带 cookie 只有 803 条，带上 4599 条**。

弹幕峰值那一层靠的就是"观众在哪一秒炸了"，数据少 4 倍，结论基本等于没做。

```powershell
# 方式一：环境变量
$env:BILI_COOKIE = "SESSDATA=xxx; bili_jct=xxx; buvid3=xxx"
# 方式二：让 audio_util 自己读 %APPDATA%\bili-cli 里的凭证（跑过 bili auth login 就有）
```

音轨同理：匿名能拿到普通音质，登录后码率更高。

## 成本总结

| 环节 | 成本 |
| --- | --- |
| 转写（SenseVoice 本地） | 0 |
| 分镜 / 关键帧 / 声音事件 / 频谱 | 0 |
| 云模型听懂情绪 | 5 分钟视频约 ¥0.05 |

## 已知局限（别信我吹）

- **秒内的动作看不见**：3 秒一帧，快速动作靠推理
- **听不出音色和旋律**：知道是钢琴，说不出弹得好不好
- **会听错**：实测把微型转子发动机认成摩托车引擎
- **云模型贵且慢**：只能挑重点片段送

## 踩过的坑（省你几小时）

1. edge-tts 负速率必须写 `--rate=-8%`，写 `--rate -8%` 会被当参数解析失败
2. ffmpeg concat 清单里的相对路径按**清单所在目录**解析，要用绝对路径
3. 同名图片覆盖后界面/模型仍显示旧图，改图要**换文件名**
4. `ffmpeg overlay + stream_loop` 在 PNG 序列上会**静默失败**，换 PIL 合成
5. PowerShell 里单引号会阻止 `\n` 转义
6. `.bat` 里含中文会 GBK 乱码，要纯 ASCII
7. B 站 CDN 音频 403：ffmpeg 要带 `Referer: https://www.bilibili.com/` 和 Chrome UA
8. YAMNet 的 ONNX 输入是**一维波形**，不是 `[1, N]`

## 授权

随便用、随便改。出了事别找我，尤其是别拿它刷量。


## 更新记录

- **v1.1**（2026-11-02）按 @酱油路人丙0 的实测反馈修了四处：
  1. 补上 `audio_util.py`，去掉对 `audio_url.py` + bilibili-api + 写死 venv 路径的依赖
  2. 五个脚本不再要求"先跑过 listen.py"，缺音频自动补齐
  3. `models/` 直接带 YAMNet 两个文件；缺文件时给明确提示，而不是裸 Traceback
  4. README 补上 yamnet 出处、cookie 必要性（弹幕 803 → 4599）

- **v1.0** 初版
