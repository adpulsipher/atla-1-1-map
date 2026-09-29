"""Village layout helpers: site search, house clusters and paths."""
from __future__ import annotations

import math

import numpy as np

from ..palettes import Palette
from ..terrain import NONE
from . import kit
from .common import BuildContext, facing_from_vector


def find_flat(ctx: BuildContext, cx: int, cz: int, search: int, foot: int, ymin: int, ymax: int,
              water_within: int | None = None, step: int = 8, avoid_water: bool = True):
    """Grid-search the flattest dry spot; returns (x, z, y) or None."""
    best = None
    for ox in range(-search, search + 1, step):
        for oz in range(-search, search + 1, step):
            x, z = cx + ox, cz + oz
            g = ctx.field(x - foot, z - foot, 2 * foot + 1, 2 * foot + 1)[::3, ::3]
            w = ctx.field(x - foot, z - foot, 2 * foot + 1, 2 * foot + 1, "water")[::3, ::3]
            if avoid_water and (w != NONE).mean() > 0.05:
                continue
            med = float(np.median(g))
            if not (ymin <= med <= ymax):
                continue
            score = -float(np.std(g)) - 0.004 * math.hypot(ox, oz)
            if water_within is not None:
                ww = ctx.field(x - water_within, z - water_within, 2 * water_within + 1,
                               2 * water_within + 1, "water")[::4, ::4]
                if not (ww != NONE).any():
                    continue
            if best is None or score > best[0]:
                best = (score, x, z, int(round(med)))
    return None if best is None else best[1:]


def place_houses(ctx: BuildContext, cx: int, cz: int, r_min: float, r_max: float, n: int,
                 pals: list[Palette], sizes=((7, 6), (9, 7), (11, 8)), stories=(1, 1, 2),
                 roof: str = "hip", avoid: list | None = None, max_slope: int = 5,
                 face_center: bool = True, stilts: int = 0, mode_pad: bool = True,
                 tries: int = 400, y_clamp: tuple[int, int] | None = None) -> list[tuple]:
    """Scatter houses in an annulus, each on its own blended pad, facing inward."""
    rng = ctx.rng
    placed: list[tuple] = []
    avoid = list(avoid or [])
    t = 0
    while len(placed) < n and t < tries:
        t += 1
        a = rng.uniform(0, 2 * math.pi)
        r = math.sqrt(rng.uniform(r_min ** 2, r_max ** 2))
        x, z = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        k = int(rng.integers(0, len(sizes)))
        w, d = sizes[k]
        rad = math.hypot(w, d) / 2 + 2
        if any(math.hypot(x - ax, z - az) < rad + ar for ax, az, ar in avoid):
            continue
        if any(math.hypot(x - px, z - pz) < rad + pr + 2 for px, pz, pr, *_ in placed):
            continue
        R = int(rad)
        g = ctx.field(x - R, z - R, 2 * R + 1, 2 * R + 1)
        wat = ctx.field(x - R, z - R, 2 * R + 1, 2 * R + 1, "water")
        if (wat != NONE).any() and not stilts:
            continue
        if g.max() - g.min() > max_slope and not stilts:
            continue
        y = int(np.median(g))
        if y_clamp:
            y = int(np.clip(y, *y_clamp))
        facing = facing_from_vector(cx - x, cz - z) if face_center else \
            ["north", "south", "east", "west"][int(rng.integers(0, 4))]
        pal = pals[int(rng.integers(0, len(pals)))]
        if mode_pad and not stilts:
            ctx.level_pad(x, z, rad - 1, rad + 4, y)
        cv = kit.house_canvas(ctx.reg, w, d, pal, stories=stories[k % len(stories)], roof=roof,
                              stilts=stilts)
        ctx.place(cv, x, z, y + (1 if stilts else 0), facing, anchor=(cv.size[0] // 2, 0, cv.size[2] // 2),
                  foundation=None if stilts else pal.foundation)
        placed.append((x, z, rad, y, facing))
    return placed


def paint_path(ctx: BuildContext, x0: int, z0: int, x1: int, z1: int, width: int = 3,
               mat: str = "minecraft:dirt_path", mat2: str | None = "minecraft:coarse_dirt") -> None:
    """Surface path following the (current) terrain, clearing plants above."""
    n = int(max(abs(x1 - x0), abs(z1 - z0))) + 1
    hw = width / 2
    xs, zs = [], []
    for i in range(n):
        t = i / max(n - 1, 1)
        x = x0 + (x1 - x0) * t
        z = z0 + (z1 - z0) * t
        for dx in range(-int(hw), int(math.ceil(hw)) + 1):
            for dz in range(-int(hw), int(math.ceil(hw)) + 1):
                if dx * dx + dz * dz <= hw * hw + 0.5:
                    xs.append(int(round(x)) + dx)
                    zs.append(int(round(z)) + dz)
    if not xs:
        return
    xs, zs = np.array(xs), np.array(zs)
    key = np.unique(np.stack([xs, zs], 1), axis=0)
    xs, zs = key[:, 0], key[:, 1]
    bx0, bz0 = xs.min(), zs.min()
    W, L = xs.max() - bx0 + 1, zs.max() - bz0 + 1
    g = ctx.field(int(bx0), int(bz0), int(W), int(L))
    wat = ctx.field(int(bx0), int(bz0), int(W), int(L), "water")
    top = ctx.field(int(bx0), int(bz0), int(W), int(L), "top")
    ys = g[xs - bx0, zs - bz0]
    dry = wat[xs - bx0, zs - bz0] == NONE
    xs, zs, ys = xs[dry], zs[dry], ys[dry]
    tops = top[xs - bx0, zs - bz0]
    ids = np.full(xs.shape, ctx.reg.id(mat), np.uint16)
    if mat2:
        alt = (xs * 7 + zs * 13) % 5 == 0
        ids[alt] = ctx.reg.id(mat2)
    ctx.terrain.points(xs, ys, zs, ids)
    # clear up to 4 blocks of vegetation above the path
    for k in range(1, 5):
        m = tops >= ys + k
        if m.any():
            ctx.terrain.points(xs[m], ys[m] + k, zs[m], "minecraft:air")
