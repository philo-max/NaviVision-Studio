"""
Generate a synthetic social-security card (社保卡) sample for the digit-recognition exercise.

The card number is pure black (gray value 0) on a light card, all other card content is
lighter, so `threshold (Image, Region, 0, 10)` isolates exactly the digits.
Requires Pillow (development-time only; the app itself does not need it).
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CARD_W, CARD_H = 640, 400
CARD_NUMBER = "44030120020815123X"
NUMBER_ORIGIN = (60, 300)
DIGIT_PITCH = 29
DIGIT_FONT_SIZE = 24
TEXT_GRAY = 70
CJK_FONT = r"C:\Windows\Fonts\msyhbd.ttc"
DIGIT_FONT = r"C:\Windows\Fonts\consolab.ttf"
OUTPUT_PATH = "samples/social_card.png"


def make_card_background() -> Image.Image:
    gradient = np.linspace(238, 205, CARD_W, dtype=np.float32)
    base = np.tile(gradient, (CARD_H, 1))
    noise = np.random.default_rng(7).normal(0, 2, (CARD_H, CARD_W))
    gray = np.clip(base + noise, 160, 255).astype(np.uint8)
    return Image.fromarray(gray, mode="L")


def draw_card_decoration(draw: ImageDraw.ImageDraw) -> None:
    title_font = ImageFont.truetype(CJK_FONT, 34)
    label_font = ImageFont.truetype(CJK_FONT, 20)
    draw.rounded_rectangle((8, 8, CARD_W - 9, CARD_H - 9), 22, outline=TEXT_GRAY + 40, width=3)
    draw.text((60, 40), "中华人民共和国社会保障卡", fill=TEXT_GRAY, font=title_font)
    draw.text((60, 110), "姓名  张  三", fill=TEXT_GRAY, font=label_font)
    draw.text((60, 150), "性别  男          民族  汉", fill=TEXT_GRAY, font=label_font)
    draw.text((60, 260), "社会保障号码", fill=TEXT_GRAY, font=label_font)
    draw.rectangle((470, 100, 580, 230), outline=TEXT_GRAY + 40, width=2)
    draw.text((492, 150), "照片", fill=TEXT_GRAY + 40, font=label_font)


def draw_card_number(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    font = ImageFont.truetype(DIGIT_FONT, DIGIT_FONT_SIZE)
    x, y = NUMBER_ORIGIN
    for i, ch in enumerate(CARD_NUMBER):
        draw.text((x + i * DIGIT_PITCH, y), ch, fill=0, font=font)


def main() -> None:
    img = make_card_background()
    draw_card_decoration(ImageDraw.Draw(img))
    draw_card_number(img)
    ok, enc = cv2.imencode(".png", cv2.cvtColor(np.array(img), cv2.COLOR_GRAY2BGR))
    if not ok:
        raise RuntimeError("PNG 编码失败")
    with open(OUTPUT_PATH, "wb") as f:
        f.write(enc.tobytes())
    print(f"saved {OUTPUT_PATH}, number={CARD_NUMBER}")


if __name__ == "__main__":
    main()
