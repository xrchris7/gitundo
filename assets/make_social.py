#!/usr/bin/env python3
"""Generate the GitHub social-preview banner (1280x640).

Same design language as assets/logo.svg & extensions/vscode resources:
a dark rounded canvas, the teal undo-arrow mark, the wordmark and tagline.

Usage:  python3 assets/make_social.py
Output: assets/social-preview.png  (PNG, 1280x640)
"""
import math

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
S = 1.0

DARK = (8, 12, 22, 255)
CARD = (13, 20, 36, 255)
TEAL = (45, 212, 191, 255)
BLUE = (59, 130, 246, 255)
TEXT = (230, 237, 247, 255)
MUTED = (148, 163, 184, 255)
WHITE = (255, 255, 255, 255)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except OSError:
        return ImageFont.load_default()


def gradient(size, c1, c2):
    img = Image.new("RGB", size)
    px = img.load()
    w, h = size
    for y in range(h):
        t = y / h
        for x in range(w):
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
    return img


img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
# background diagonal gradient
bg = gradient((W, H), (7, 10, 18), (11, 18, 32))
bg = bg.convert("RGBA")
img.paste(bg, (0, 0))

d = ImageDraw.Draw(img, "RGBA")

# subtle grid dots (tech feel)
for y in range(80, H, 44):
    for x in range(80, W, 44):
        d.ellipse([x, y, x + 3, y + 3], fill=(255, 255, 255, 14))

# big undo-arrow mark on the left
cx, cy, r = 300, 300, 120
w = 34
ring = TEAL
d.arc([cx - r, cy - r, cx + r, cy + r], start=138, end=398, fill=ring, width=w)
a = math.radians(138)
tip = (cx + r * math.cos(a), cy + r * math.sin(a))
for side in (-1, 1):
    ang = a + side * 0.66
    pt = (tip[0] + 40 * math.cos(ang), tip[1] + 40 * math.sin(ang))
    d.line([tip, pt], fill=ring, width=w)
d.ellipse([tip[0] - 13, tip[1] - 13, tip[0] + 13, tip[1] + 13], fill=ring)
# check mark under the arrow
c1, c2, c3 = (430, 330), (466, 366), (560, 250)
d.line([c1, c2], fill=WHITE, width=26)
d.line([c2, c3], fill=WHITE, width=26)

# wordmark
title = font("DejaVuSans-Bold.ttf", 96)
d.text((470, 150), "gitundo", font=title, fill=TEXT)

# tagline
tag = font("DejaVuSans.ttf", 40)
d.text((472, 268), "The undo button git never had.", font=tag, fill=MUTED)

# feature pill on the lower band (single line — guaranteed to fit 1280px)
pill_text = "snap  ·  list  ·  restore  ·  diff  ·  tag  ·  auto-guard"
pill_font = font("DejaVuSans-Bold.ttf", 30)
tw = d.textlength(pill_text, font=pill_font)
pad_x, pad_y = 28, 18
box_w = tw + pad_x * 2
box_h = 68
bx, by = 470, 372
d.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=box_h // 2,
                    outline=(45, 212, 191, 80), width=3)
d.text((bx + pad_x, by + (box_h - 42) / 2), pill_text, font=pill_font, fill=TEAL)

# footer tagline small
foot = font("DejaVuSans.ttf", 26)
d.text((470, 492), "Zero-dependency safety-net snapshots for any git repository.",
       font=foot, fill=MUTED)

img.save("assets/social-preview.png")
print("wrote assets/social-preview.png", img.size)
