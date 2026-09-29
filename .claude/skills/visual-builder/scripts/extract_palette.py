#!/usr/bin/env python3
"""Measure a reference image: size, dominant colours and exact pixel values.

Usage:
    python extract_palette.py IMAGE [--colors 10] [--at X,Y ...]

Prints the image size, the dominant colours (hex, share of pixels), small but
saturated accent colours, and the hex value at each --at pixel.  Needs
Pillow (pip install pillow).
"""
import argparse
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: pip install pillow")


def hex_of(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--colors", type=int, default=10, help="number of dominant colours")
    ap.add_argument("--at", action="append", default=[], help="X,Y pixel to sample (repeatable)")
    a = ap.parse_args()

    im = Image.open(a.image)
    rgba = im.convert("RGBA")
    print(f"size: {im.width} x {im.height} px")

    rgb = rgba.convert("RGB")
    small = rgb.copy()
    small.thumbnail((400, 400))
    q = small.quantize(colors=max(a.colors, 32), method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    entries = [(c / total, tuple(pal[i * 3: i * 3 + 3])) for c, i in counts]
    print("dominant colours:")
    for share, (r, g, b) in entries[: a.colors]:
        print(f"  {hex_of((r, g, b))}  rgb({r}, {g}, {b})  {100 * share:5.1f}%")
    # small but saturated areas are usually accents (buttons, links, icons)
    listed = [c for _, c in entries[: a.colors]]
    accents = []
    for share, c in entries[a.colors:]:
        sat = max(c) - min(c)
        if share >= 0.001 and sat >= 60 and all(sum(abs(x - y) for x, y in zip(c, l)) > 60 for l in listed + accents):
            accents.append(c)
            print(f"  accent {hex_of(c)}  rgb({c[0]}, {c[1]}, {c[2]})  {100 * share:5.2f}%")

    for spec in a.at:
        x, y = (int(v) for v in spec.split(","))
        px = rgba.getpixel((x, y))
        alpha = "" if px[3] == 255 else f"  alpha {px[3] / 255:.2f}"
        print(f"pixel ({x},{y}): {hex_of(px)}  rgb({px[0]}, {px[1]}, {px[2]}){alpha}")


if __name__ == "__main__":
    main()
