"""Georeferencing between reference-map pixels and world block coordinates."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage

from .reference import CONTENT_RECT, land_mask


@dataclass
class GeoRef:
    """world_x = ax * px + bx ; world_z = az * py + bz  (axis aligned)."""

    ax: float
    bx: float
    az: float
    bz: float
    method: str = "bounds"
    score: float | None = None

    @classmethod
    def from_bounds(cls, bounds: tuple[int, int, int, int], rect=CONTENT_RECT) -> "GeoRef":
        min_x, min_z, max_x, max_z = bounds
        x0, y0, x1, y1 = rect
        ax = (max_x - min_x) / (x1 - x0)
        az = (max_z - min_z) / (y1 - y0)
        return cls(float(ax), float(min_x - ax * x0), float(az), float(min_z - az * y0), "bounds")

    def to_world(self, px: float, py: float) -> tuple[float, float]:
        return self.ax * px + self.bx, self.az * py + self.bz

    def to_ref(self, x, z):
        return (np.asarray(x) - self.bx) / self.ax, (np.asarray(z) - self.bz) / self.az

    @property
    def blocks_per_px(self) -> float:
        return float(np.sqrt(abs(self.ax * self.az)))

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "GeoRef":
        return cls(**{k: d[k] for k in ("ax", "bx", "az", "bz", "method", "score") if k in d})

    def save(self, path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_json(), f, indent=2)


def sample_ref_land(geo: GeoRef, xs: np.ndarray, zs: np.ndarray, ref_land: np.ndarray) -> np.ndarray:
    px, py = geo.to_ref(xs, zs)
    h, w = ref_land.shape
    pxi = np.clip(np.floor(px).astype(int), 0, w - 1)
    pyi = np.clip(np.floor(py).astype(int), 0, h - 1)
    inside = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    return ref_land[pyi, pxi] & inside


def register(world_land: np.ndarray, origin: tuple[int, int], cell: int,
             initial: GeoRef, ref_land: np.ndarray | None = None) -> GeoRef:
    """Fit the reference land mask onto a (downsampled) world land mask.

    ``world_land`` is indexed [x, z] with cell size ``cell`` blocks starting at
    world ``origin``.  Maximises intersection-over-union with a coarse-to-fine
    pattern search over the four affine parameters, starting from both the
    bounds-based guess and a moment-matching guess.
    """
    ref_land = land_mask() if ref_land is None else ref_land
    W, L = world_land.shape
    xs = origin[0] + (np.arange(W) + 0.5) * cell
    zs = origin[1] + (np.arange(L) + 0.5) * cell
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    # subsample for speed
    step = max(1, int(np.sqrt(W * L / 250_000)))
    X, Z, target = X[::step, ::step], Z[::step, ::step], world_land[::step, ::step]

    def iou(p):
        g = GeoRef(*p)
        pred = sample_ref_land(g, X, Z, ref_land)
        inter = np.count_nonzero(pred & target)
        union = np.count_nonzero(pred | target)
        return inter / union if union else 0.0

    # moment matching guess
    cands = [np.array([initial.ax, initial.bx, initial.az, initial.bz])]
    if target.any():
        ry, rx = np.nonzero(ref_land)
        wx, wz = X[target], Z[target]
        ax = wx.std() / max(rx.std(), 1e-6)
        az = wz.std() / max(ry.std(), 1e-6)
        cands.append(np.array([ax, wx.mean() - ax * (rx.mean() + 0.5),
                               az, wz.mean() - az * (ry.mean() + 0.5)]))
    best_p, best_s = None, -1.0
    for p in cands:
        s = iou(p)
        if s > best_s:
            best_p, best_s = p.copy(), s
    # pattern search
    scale_steps = [0.08, 0.04, 0.02, 0.01, 0.005, 0.0025]
    for frac in scale_steps:
        improved = True
        while improved:
            improved = False
            span_x = best_p[0] * 580 * frac
            span_z = best_p[2] * 490 * frac
            deltas = [(frac * best_p[0], 0, 0, 0), (0, span_x, 0, 0),
                      (0, 0, frac * best_p[2], 0), (0, 0, 0, span_z)]
            for d in deltas:
                for sgn in (1, -1):
                    p = best_p + sgn * np.array(d)
                    if abs(d[0]) > 0:  # keep the map centred while scaling
                        p[1] -= sgn * d[0] * 293
                    if abs(d[2]) > 0:
                        p[3] -= sgn * d[2] * 253
                    s = iou(p)
                    if s > best_s + 1e-5:
                        best_p, best_s, improved = p, s, True
    return GeoRef(*map(float, best_p), method="registered", score=round(float(best_s), 4))


def coast_distance(land: np.ndarray, cell: float = 1.0) -> np.ndarray:
    """Signed distance to the coastline in blocks (+ on land, - in water)."""
    d_land = ndimage.distance_transform_edt(land) * cell
    d_water = ndimage.distance_transform_edt(~land) * cell
    return np.where(land, d_land, -d_water)
