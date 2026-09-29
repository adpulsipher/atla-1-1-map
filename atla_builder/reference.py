"""The reference frame: a terrain-class raster derived from the painted map.

All landmark anchors in ``config/landmarks.json`` are given in *reference
pixels* (the 586x505 painted map).  :mod:`atla_builder.geo` turns them into
world block coordinates.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REF_PATH = ROOT / "reference" / "terrain_classes.png"

CLASSES = {
    "ocean": 0, "shallow": 1, "plains": 2, "forest": 3, "dense_forest": 4,
    "swamp": 5, "hills": 6, "red_rock": 7, "desert": 8, "mountain": 9, "snow": 10,
}
CLASS_COLORS = {
    0: (10, 60, 185), 1: (40, 100, 200), 2: (125, 146, 64), 3: (60, 110, 40),
    4: (35, 80, 25), 5: (95, 110, 85), 6: (125, 100, 50), 7: (190, 90, 40),
    8: (200, 185, 130), 9: (150, 150, 150), 10: (235, 235, 240),
}
WATER_CLASSES = (CLASSES["ocean"], CLASSES["shallow"])
# Painted area inside the decorative frame (x0, y0, x1, y1), exclusive max.
# By default this rectangle is stretched over the world's generated bounds.
CONTENT_RECT = (6, 7, 580, 499)


@lru_cache(maxsize=1)
def load_classes(path: str | None = None) -> np.ndarray:
    """uint8 array [row(z), col(x)] of class ids."""
    return np.asarray(Image.open(path or REF_PATH))


def land_mask(path: str | None = None) -> np.ndarray:
    return ~np.isin(load_classes(path), WATER_CLASSES)


def ref_size(path: str | None = None) -> tuple[int, int]:
    h, w = load_classes(path).shape
    return w, h
