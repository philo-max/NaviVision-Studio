"""
Generate the NaviVision Studio logo: a viewfinder (corner brackets) around a camera lens.

One set of geometry constants drives both outputs so they stay identical:
  branding/logo.svg  -> web favicon / vector source
  branding/app.ico   -> Windows exe / window icon (16..256 px)
  branding/logo.png  -> 512 px preview
Requires Pillow (development-time only).
"""

import os
from PIL import Image, ImageDraw

SIZE = 1024
CORNER_RADIUS = 220
BG_TOP = (10, 16, 34)
BG_BOTTOM = (18, 32, 66)
CYAN = (0, 240, 255)
ACCENT = (255, 51, 102)
BORDER_ALPHA = 90
BRACKET_INSET = 190
BRACKET_ARM = 170
BRACKET_STROKE = 44
RING_RADIUS = 175
RING_STROKE = 46
LENS_RADIUS = 78
GLINT_RADIUS = 26
GLINT_OFFSET = (-30, -30)
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CENTER = SIZE // 2


def bracket_segments():
    lo, hi = BRACKET_INSET, SIZE - BRACKET_INSET
    arm = BRACKET_ARM
    return [
        ((lo, lo + arm), (lo, lo), (lo + arm, lo)),
        ((hi - arm, lo), (hi, lo), (hi, lo + arm)),
        ((lo, hi - arm), (lo, hi), (lo + arm, hi)),
        ((hi - arm, hi), (hi, hi), (hi, hi - arm)),
    ]


def render_png() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (SIZE, SIZE))
    gd = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        gd.line([(0, y), (SIZE, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), CORNER_RADIUS, fill=255)
    img.paste(gradient, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, SIZE - 7, SIZE - 7), CORNER_RADIUS, outline=CYAN + (BORDER_ALPHA,), width=8)
    for a, b, c in bracket_segments():
        d.line([a, b, c], fill=CYAN, width=BRACKET_STROKE, joint="curve")
        for p in (a, c):
            r = BRACKET_STROKE // 2
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=CYAN)
    d.ellipse((CENTER - RING_RADIUS, CENTER - RING_RADIUS, CENTER + RING_RADIUS, CENTER + RING_RADIUS),
              outline=CYAN, width=RING_STROKE)
    d.ellipse((CENTER - LENS_RADIUS, CENTER - LENS_RADIUS, CENTER + LENS_RADIUS, CENTER + LENS_RADIUS), fill=ACCENT)
    gx, gy = CENTER + GLINT_OFFSET[0], CENTER + GLINT_OFFSET[1]
    d.ellipse((gx - GLINT_RADIUS, gy - GLINT_RADIUS, gx + GLINT_RADIUS, gy + GLINT_RADIUS), fill=(255, 255, 255, 230))
    return img


def render_svg() -> str:
    hexc = lambda c: "#%02x%02x%02x" % c
    paths = "".join(
        f'<polyline points="{a[0]},{a[1]} {b[0]},{b[1]} {c[0]},{c[1]}"/>' for a, b, c in bracket_segments()
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{hexc(BG_TOP)}"/><stop offset="1" stop-color="{hexc(BG_BOTTOM)}"/>'
        f'</linearGradient></defs>'
        f'<rect width="{SIZE}" height="{SIZE}" rx="{CORNER_RADIUS}" fill="url(#bg)"/>'
        f'<rect x="6" y="6" width="{SIZE - 12}" height="{SIZE - 12}" rx="{CORNER_RADIUS}" fill="none" '
        f'stroke="{hexc(CYAN)}" stroke-opacity="{BORDER_ALPHA / 255:.2f}" stroke-width="8"/>'
        f'<g fill="none" stroke="{hexc(CYAN)}" stroke-width="{BRACKET_STROKE}" stroke-linecap="round" '
        f'stroke-linejoin="round">{paths}</g>'
        f'<circle cx="{CENTER}" cy="{CENTER}" r="{RING_RADIUS - RING_STROKE // 2}" fill="none" '
        f'stroke="{hexc(CYAN)}" stroke-width="{RING_STROKE}"/>'
        f'<circle cx="{CENTER}" cy="{CENTER}" r="{LENS_RADIUS}" fill="{hexc(ACCENT)}"/>'
        f'<circle cx="{CENTER + GLINT_OFFSET[0]}" cy="{CENTER + GLINT_OFFSET[1]}" r="{GLINT_RADIUS}" '
        f'fill="#fff" fill-opacity="0.9"/></svg>'
    )


def main() -> None:
    img = render_png()
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT_DIR, "logo.png"))
    img.save(os.path.join(OUT_DIR, "app.ico"), sizes=ICO_SIZES)
    with open(os.path.join(OUT_DIR, "logo.svg"), "w", encoding="utf-8") as f:
        f.write(render_svg())
    print("generated logo.svg, logo.png, app.ico in", OUT_DIR)


if __name__ == "__main__":
    main()
