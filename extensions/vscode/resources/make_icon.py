#!/usr/bin/env python3
"""Rasterise the gitundo mark into the marketplace/extension icon (PNG).

Pure Pillow, no system deps. Draws the same design as assets/logo.svg:
a dark rounded square, a teal undo-arrow arc with arrowhead, and a check.

Usage:  python3 make_icon.py [size]
"""
import math
import sys

from PIL import Image, ImageDraw

SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 512
S = SIZE / 512.0  # scale factor relative to a 512 canvas

DARK = (11, 18, 32, 255)
TEAL = (45, 212, 191, 255)
BLUE = (37, 99, 235, 255)
BG = (15, 23, 42, 255)


def lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# background rounded square with subtle gradient-ish border
d.rounded_rectangle([10 * S, 10 * S, 502 * S, 502 * S], radius=110 * S, fill=DARK)
d.rounded_rectangle([13 * S, 13 * S, 499 * S, 499 * S], radius=107 * S,
                    outline=lerp(TEAL, BLUE, 0.45), width=max(3, int(8 * S)))

cx, cy, r = 210 * S, 205 * S, 150 * S
w = max(14, int(40 * S))

# undo arc: from 135 deg sweeping ~300 deg clockwise? Draw arc portion of circle
d.arc([cx - r, cy - r, cx + r, cy + r], start=140, end=395, fill=TEAL, width=w)

# arrowhead at the start of the arc
a = math.radians(140)
tip = (cx + r * math.cos(a), cy + r * math.sin(a))
# pointing backward along the arc
spread = 0.62
for side in (-1, 1):
    ang = a + side * spread
    pt = (tip[0] + 46 * S * math.cos(ang), tip[1] + 46 * S * math.sin(ang))
    d.line([tip, pt], fill=TEAL, width=w)
# small fill dot under arrow for clarity
d.ellipse([tip[0] - 16 * S, tip[1] - 16 * S, tip[0] + 16 * S, tip[1] + 16 * S], fill=TEAL)

# check mark inside lower-right
c1 = (300 * S, 265 * S)
c2 = (335 * S, 302 * S)
c3 = (430 * S, 190 * S)
d.line([c1, c2], fill=(255, 255, 255, 255), width=max(10, int(34 * S)))
d.line([c2, c3], fill=(255, 255, 255, 255), width=max(10, int(34 * S)))

img.save("gitundo-icon.png")
print(f"wrote gitundo-icon.png ({SIZE}x{SIZE})")
