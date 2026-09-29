"""Turn reference-map anchors into concrete, terrain-checked world sites."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage

from .geo import GeoRef
from .terrain import NONE, S_RED_SAND, S_SAND, S_SANDSTONE, TerrainModel

ROOT = Path(__file__).resolve().parents[1]
FACINGS = ("east", "south", "west", "north")  # angle 0, 90, 180, 270 deg (x east, z south)


def angle_to_facing(theta: float) -> str:
    k = int(round((math.degrees(theta) % 360) / 90.0)) % 4
    return FACINGS[k]


@dataclass
class Site:
    id: str
    x: int
    y: int
    z: int
    facing: str
    angle: float
    fit_radius: float
    strategy: str
    anchor: tuple[int, int]
    path: list[tuple[int, int]] | None = None
    sea_level: int = 62
    notes: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["angle_deg"] = round(math.degrees(self.angle), 1)
        del d["angle"]
        return d


def load_landmarks(path: str | Path | None = None) -> list[dict]:
    with open(path or ROOT / "config" / "landmarks.json") as f:
        return json.load(f)["landmarks"]


class Locator:
    CELL = 4

    def __init__(self, tm: TerrainModel, geo: GeoRef):
        self.tm = tm
        self.geo = geo
        self.claimed: list[tuple[float, float, float]] = []

    # ------------------------------------------------------------------
    def _window(self, cx: float, cz: float, R: float):
        c = self.CELL
        x0 = int(cx - R) // c * c
        z0 = int(cz - R) // c * c
        n = int(2 * R) // c + 1
        xs = np.clip(x0 + np.arange(n) * c - self.tm.x0, 0, self.tm.shape[0] - 1)
        zs = np.clip(z0 + np.arange(n) * c - self.tm.z0, 0, self.tm.shape[1] - 1)
        ix = np.ix_(xs, zs)
        g = self.tm.ground[ix].astype(np.float32)
        w = self.tm.water[ix]
        s = self.tm.surf[ix]
        inside = self.tm.inside(x0 + np.arange(n)[:, None] * c, z0 + np.arange(n)[None, :] * c)
        land = (w == NONE) & (g != NONE) & inside
        g[g == NONE] = self.tm.sea_level - 30
        X = x0 + np.arange(n)[:, None] * c + c / 2
        Z = z0 + np.arange(n)[None, :] * c + c / 2
        return dict(x0=x0, z0=z0, g=g, water=w, surf=s, land=land, X=X, Z=Z, n=n)

    def _claim_penalty(self, X, Z, r):
        pen = np.zeros(np.broadcast(X, Z).shape, np.float32)
        for (px, pz, pr) in self.claimed:
            d = np.hypot(X - px, Z - pz)
            pen += np.clip((pr + r) - d, 0, None)
        return pen

    def _pick(self, W, score, valid):
        score = np.where(valid, score, -np.inf)
        if not np.isfinite(score).any():
            return None
        i, j = np.unravel_index(np.argmax(score), score.shape)
        return float(W["X"][i, 0]), float(W["Z"][0, j]), (i, j)

    def _ground_y(self, x: float, z: float, r: float = 6) -> int:
        tm = self.tm
        g = tm.window(int(x - r), int(z - r), int(2 * r) + 1, int(2 * r) + 1).astype(np.float32)
        g = g[g != NONE]
        return int(np.median(g)) if g.size else tm.sea_level

    # ------------------------------------------------------------------
    def locate(self, lm: dict) -> Site:
        ax, az = self.geo.to_world(*lm["anchor_px"])
        bpp = self.geo.blocks_per_px
        search = lm.get("search_px", 10) * bpp
        foot = float(lm.get("footprint_r", 60))
        strategy = lm.get("strategy", "anchor")
        R = search + foot + 32
        W = self._window(ax, az, R)
        land = W["land"]
        dist_anchor = np.hypot(W["X"] - ax, W["Z"] - az)
        in_search = dist_anchor <= max(search, self.CELL)
        edt_land = ndimage.distance_transform_edt(land) * self.CELL
        edt_water = ndimage.distance_transform_edt(~land) * self.CELL
        claim = self._claim_penalty(W["X"], W["Z"], foot * 0.6)
        gs = ndimage.gaussian_filter(W["g"], 2.0)
        notes: dict = {}
        facing_angle = None
        path = None

        if strategy == "peak":
            score = ndimage.gaussian_filter(W["g"], 3.0) - 0.02 * dist_anchor - 3 * claim
            pick = self._pick(W, score, in_search & land)
        elif strategy in ("flat", "desert"):
            k = max(3, int(foot / self.CELL / 2))
            mean = ndimage.uniform_filter(gs, k)
            var = ndimage.uniform_filter(gs * gs, k) - mean * mean
            land_frac = ndimage.uniform_filter(land.astype(np.float32), 2 * k + 1)
            score = -np.sqrt(np.maximum(var, 0)) - 0.01 * dist_anchor - 20 * (1 - land_frac) - 3 * claim
            valid = in_search & land
            if strategy == "desert":
                sandy = np.isin(W["surf"], (S_SAND, S_RED_SAND, S_SANDSTONE)).astype(np.float32)
                sand_frac = ndimage.uniform_filter(sandy, 2 * k + 1)
                score = score + 30 * sand_frac
                notes["sand_fraction"] = float(sand_frac[in_search].max()) if in_search.any() else 0.0
            pick = self._pick(W, score, valid)
        elif strategy == "island":
            lab, n = ndimage.label(land)
            near = lab[in_search & land]
            if near.size:
                ids, counts = np.unique(near[near > 0], return_counts=True)
                # prefer the component closest to the anchor, then the larger one
                best, best_s = None, -np.inf
                for comp, cnt in zip(ids, counts):
                    dmin = dist_anchor[lab == comp].min()
                    s = -dmin + 0.02 * cnt * self.CELL
                    if s > best_s:
                        best, best_s = comp, s
                comp_mask = lab == best
                score = edt_land - 0.005 * dist_anchor - 3 * claim
                pick = self._pick(W, score, comp_mask)
                notes["island_area_blocks"] = int(comp_mask.sum() * self.CELL ** 2)
            else:
                pick = None
        elif strategy == "coast":
            coastal = land & (edt_land <= 3 * self.CELL + 1)
            score = -dist_anchor - 3 * claim
            pick = self._pick(W, score, coastal & in_search)
            if pick is None:
                pick = self._pick(W, -dist_anchor, land)
        elif strategy == "coast_flat":
            k = max(3, int(foot / self.CELL / 2))
            mean = ndimage.uniform_filter(gs, 2 * k + 1)
            var = ndimage.uniform_filter(gs * gs, 2 * k + 1) - mean * mean
            land_frac = ndimage.uniform_filter(land.astype(np.float32), 2 * k + 1)
            near_coast = land & (edt_land <= foot * 0.9) & (edt_land >= 6)
            score = (-np.sqrt(np.maximum(var, 0)) - 0.6 * np.abs(mean - (self.tm.sea_level + 5))
                     - 0.004 * dist_anchor - 10 * np.abs(land_frac - 0.7) - 3 * claim)
            pick = self._pick(W, score, near_coast & in_search)
        elif strategy == "inland_max":
            score = edt_land - 0.25 * dist_anchor - 3 * claim
            pick = self._pick(W, score, in_search & land)
        elif strategy == "sea":
            open_water = edt_water - 0.3 * dist_anchor - 3 * claim
            pick = self._pick(W, open_water, in_search | (~land))
        elif strategy == "ravine":
            k = max(3, int(40 / self.CELL))
            mx = ndimage.maximum_filter(gs, k)
            mn = ndimage.minimum_filter(gs, k)
            relief = mx - mn
            score = relief + 0.3 * gs - 0.02 * dist_anchor - 3 * claim
            pick = self._pick(W, score, in_search & land)
        elif strategy == "canyon":
            score = -0.02 * dist_anchor + 0.01 * edt_land - 3 * claim
            pick = self._pick(W, score, in_search & land)
            facing_angle = math.radians(lm.get("orientation_deg", 0))
        elif strategy == "path":
            path = [tuple(int(round(v)) for v in self.geo.to_world(*p)) for p in lm["path_px"]]
            pick = (ax, az, None)
        else:
            pick = (ax, az, None)

        if pick is None:
            pick = (ax, az, None)
            notes["fallback"] = "no candidate satisfied the strategy; using raw anchor"
        x, z, ij = pick
        x, z = int(round(x)), int(round(z))

        # usable radius around the site and direction to the nearest water
        if ij is not None:
            fit = float(edt_land[ij]) if land[ij] else float(edt_water[ij])
        else:
            fit = foot
        if facing_angle is None:
            facing_angle = self._water_direction(W, land, ij) if ij is not None else 0.0
        if strategy == "sea":
            notes["open_water_radius"] = fit
        site = Site(id=lm["id"], x=x, y=self._ground_y(x, z), z=z, facing=angle_to_facing(facing_angle),
                    angle=facing_angle, fit_radius=round(fit, 1), strategy=strategy,
                    anchor=(int(ax), int(az)), path=path, sea_level=self.tm.sea_level, notes=notes)
        self.claimed.append((x, z, foot))
        return site

    def _water_direction(self, W, land, ij) -> float:
        """Angle (radians, x east / z south) pointing from the site to open water."""
        edt = ndimage.distance_transform_edt(land)
        gx, gz = np.gradient(ndimage.gaussian_filter(edt, 3.0))
        i, j = ij
        vx, vz = -gx[i, j], -gz[i, j]
        if abs(vx) + abs(vz) < 1e-6:
            wi, wj = np.nonzero(~land)
            if wi.size == 0:
                return 0.0
            k = np.argmin((wi - i) ** 2 + (wj - j) ** 2)
            vx, vz = wi[k] - i, wj[k] - j
        return math.atan2(vz, vx)


def locate_all(tm: TerrainModel, geo: GeoRef, landmarks: list[dict], only=None, log=print):
    loc = Locator(tm, geo)
    # big footprints claim space first so small neighbours get pushed aside
    order = sorted(range(len(landmarks)), key=lambda i: -landmarks[i].get("footprint_r", 60))
    sites: dict[str, Site] = {}
    for i in order:
        lm = landmarks[i]
        if only and lm["id"] not in only:
            continue
        s = loc.locate(lm)
        sites[lm["id"]] = s
        log(f"  located {lm['id']:24s} at x={s.x:6d} y={s.y:4d} z={s.z:6d}  "
            f"fit_r={s.fit_radius:6.0f}  facing={s.facing}")
    return sites
