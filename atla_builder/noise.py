"""Cheap deterministic 2-D value noise (numpy only)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def value_noise(shape: tuple[int, int], cell: float, seed: int, origin=(0, 0)) -> np.ndarray:
    """Smooth noise in [-1, 1] sampled on a grid of `shape` (x, z).

    The lattice is anchored to world coordinates via ``origin`` so tiles
    generated independently line up seamlessly.
    """
    ox, oz = origin
    gx0 = int(np.floor(ox / cell)) - 1
    gz0 = int(np.floor(oz / cell)) - 1
    gw = int(np.ceil((ox + shape[0]) / cell)) + 2 - gx0
    gl = int(np.ceil((oz + shape[1]) / cell)) + 2 - gz0
    gx = np.arange(gx0, gx0 + gw, dtype=np.int64)[:, None]
    gz = np.arange(gz0, gz0 + gl, dtype=np.int64)[None, :]
    h = (gx * 374761393 + gz * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    lattice = ((h & 0xFFFF) / 32767.5 - 1.0).astype(np.float32)
    xs = (np.arange(shape[0]) + ox) / cell - gx0
    zs = (np.arange(shape[1]) + oz) / cell - gz0
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    return ndimage.map_coordinates(lattice, [X, Z], order=3, mode="nearest").astype(np.float32)


def fbm(shape, cell: float, seed: int, octaves: int = 4, origin=(0, 0)) -> np.ndarray:
    out = np.zeros(shape, np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        out += amp * value_noise(shape, cell / (2 ** o), seed + o * 101, origin)
        total += amp
        amp *= 0.5
    return out / total


def hash01(x, z, seed: int = 0):
    """Deterministic per-column pseudo random numbers in [0,1)."""
    x = np.asarray(x, dtype=np.int64)
    z = np.asarray(z, dtype=np.int64)
    h = (x * 73856093) ^ (z * 19349663) ^ (seed * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF) / float(0x1000000)
