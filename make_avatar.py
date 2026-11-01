"""从角色立绘裁一张头像：只取头肩，居中，深色底。"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SRC = HERE / "char_full.png"
OUT = HERE / "avatar_char.png"
SIZE = 800


def main():
    src = Image.open(SRC).convert("RGBA")

    # 整幅缩放到画布内，底部对齐，留出边距
    S = SIZE
    target_h = int(S * 0.98)
    scale = target_h / src.height
    ch = src.resize((int(src.width * scale), target_h), Image.LANCZOS)

    bg = Image.new("RGB", (S, S), (11, 13, 18))
    d = ImageDraw.Draw(bg)
    # 背后一点点冷色光，别太花
    for r in range(S // 2, 0, -8):
        k = 1 - r / (S / 2)
        c = int(11 + 20 * k)
        d.ellipse([S / 2 - r, S * 0.32 - r, S / 2 + r, S * 0.32 + r], fill=(c, c + 1, c + 4))

    x = (S - ch.width) // 2
    y = S - ch.height
    bg.paste(ch, (x, y), ch)

    bg.save(OUT)
    print("已生成:", OUT, bg.size)


if __name__ == "__main__":
    main()
