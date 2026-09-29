"""Derive reference/terrain_classes.png from the painted world map.

Usage: python tools/make_reference_classes.py painted_map.png

The painted map (586x505, 'Painted by Cannonman1605') is only used to derive a
coarse terrain-class raster.  That raster is what the georeferencer registers
against the real world's land mask and what the synthetic stand-in world is
generated from; the artwork itself is not stored in the repository.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atla_builder.reference import CLASS_COLORS, CLASSES  # noqa: E402

# painted content area inside the decorative frame: x 6..579, y 7..498
CONTENT = (6, 7, 580, 499)


def classify(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    out = np.full(r.shape, CLASSES["plains"], np.uint8)
    water = (b >= np.maximum(r, g) + 20) & (b > 110)
    deep = water & (b > 175) & (r < 30) & (g < 90)
    snow = (mn > 185) & (mx - mn < 40)
    rock = ~snow & (mn > 110) & (mx - mn < 30)
    sand = (r > 160) & (g > 140) & (b < 170) & (r - b > 35) & ~snow
    red = (r > g + 35) & (r > 120) & (g < 130) & ~sand
    dark = (g > r) & (g > b) & (g < 105) & (r < 60)
    forest = (g > r) & (g > b) & ~dark & (r < 90)
    swamp = (abs(r - g) < 25) & (b > r - 15) & (g < 125) & (r > 85) & ~water
    brown = (r > b + 30) & (g > b + 20) & (r < 150) & (g < 125) & ~red & ~sand
    out[forest] = CLASSES["forest"]
    out[dark] = CLASSES["dense_forest"]
    out[swamp] = CLASSES["swamp"]
    out[brown] = CLASSES["hills"]
    out[red] = CLASSES["red_rock"]
    out[sand] = CLASSES["desert"]
    out[rock] = CLASSES["mountain"]
    out[snow] = CLASSES["snow"]
    out[water] = CLASSES["shallow"]
    out[deep] = CLASSES["ocean"]
    return out


def main(src: str) -> None:
    rgb = np.asarray(Image.open(src).convert("RGB"))
    cls = classify(rgb)
    # the frame is decorative: treat it as ocean
    x0, y0, x1, y1 = CONTENT
    cls[:y0, :] = cls[y1:, :] = CLASSES["ocean"]
    cls[:, :x0] = cls[:, x1:] = CLASSES["ocean"]
    # The title lettering sits on water; any tiny 'land' specks fully
    # surrounded by water are removed, then small holes are closed.
    land = ~np.isin(cls, [CLASSES["ocean"], CLASSES["shallow"]])
    lab, n = ndimage.label(land)
    sizes = ndimage.sum(land, lab, range(1, n + 1))
    for i, s in enumerate(sizes, start=1):
        if s < 4:
            cls[lab == i] = CLASSES["shallow"]
    # smooth isolated misclassified pixels on land with a mode filter
    land = ~np.isin(cls, [CLASSES["ocean"], CLASSES["shallow"]])

    def mode(values):
        v = values.astype(int)
        return np.bincount(v).argmax()

    sm = ndimage.generic_filter(cls, mode, size=3)
    cls = np.where(land, sm, cls).astype(np.uint8)
    # keep land/water topology from the unfiltered mask
    water_now = np.isin(cls, [CLASSES["ocean"], CLASSES["shallow"]])
    cls[land & water_now] = CLASSES["plains"]
    out = Path(__file__).resolve().parents[1] / "reference" / "terrain_classes.png"
    out.parent.mkdir(exist_ok=True)
    img = Image.fromarray(cls, mode="P")
    pal = []
    for i in range(256):
        pal += list(CLASS_COLORS.get(i, (0, 0, 0)))
    img.putpalette(pal)
    img.save(out, optimize=True)
    counts = np.bincount(cls.ravel(), minlength=len(CLASSES))
    inv = {v: k for k, v in CLASSES.items()}
    for i, c in enumerate(counts):
        if c:
            print(f"{inv.get(i, i):14s} {c}")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
