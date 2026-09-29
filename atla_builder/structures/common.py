"""Build context, rotation-aware placement and terrain-integration helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..blocks import AIR, Registry
from ..buffer import SOFT, Canvas, EditBuffer
from ..locate import Site
from ..terrain import NONE, SURFACE_BLOCKS, S_GRASS, TerrainModel

TURNS = {"south": 0, "west": 1, "north": 2, "east": 3}  # canvas front (+z) -> facing


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


@dataclass
class Placement:
    """Maps canvas-local coordinates to world coordinates after rotation."""

    q: int
    size: tuple[int, int, int]  # unrotated canvas size
    origin: tuple[int, int, int]  # world coords of rotated canvas (0,0,0)

    def to_world(self, x: int, y: int, z: int) -> tuple[int, int, int]:
        X, _, Z = self.size
        for _ in range(self.q):
            x, z = Z - 1 - z, x
            X, Z = Z, X
        return x + self.origin[0], y + self.origin[1], z + self.origin[2]


@dataclass
class BuildContext:
    reg: Registry
    tm: TerrainModel
    site: Site
    lm: dict
    seed: int = 0
    terrain: EditBuffer = None  # type: ignore[assignment]
    struct: EditBuffer = None  # type: ignore[assignment]
    pois: dict = field(default_factory=dict)
    claims: list = field(default_factory=list)
    integration: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    scale: float = 1.0

    def __post_init__(self):
        self.terrain = self.terrain or EditBuffer(self.reg)
        self.struct = self.struct or EditBuffer(self.reg)
        self.rng = np.random.default_rng(self.seed)
        # working copy of the terrain around the site, updated by shape_terrain
        R = int(self.lm.get("footprint_r", 100) * 1.8) + 160
        self.hx0, self.hz0 = self.site.x - R, self.site.z - R
        n = 2 * R + 1
        g = self.tm.window(self.hx0, self.hz0, n, n, "ground").astype(np.int32)
        self.h_ground = np.where(g == NONE, self.tm.sea_level - 20, g)
        t = self.tm.window(self.hx0, self.hz0, n, n, "top").astype(np.int32)
        self.h_top = np.where(t == NONE, self.h_ground, t)
        self.h_water = self.tm.window(self.hx0, self.hz0, n, n, "water").astype(np.int32)

    def field(self, x0: int, z0: int, w: int, l: int, name: str = "ground") -> np.ndarray:
        """Current (possibly already reshaped) terrain field over a window."""
        arr = {"ground": self.h_ground, "top": self.h_top, "water": self.h_water}[name]
        xs = np.arange(x0, x0 + w) - self.hx0
        zs = np.arange(z0, z0 + l) - self.hz0
        n = arr.shape[0]
        inside = ((xs >= 0) & (xs < n))[:, None] & ((zs >= 0) & (zs < n))[None, :]
        out = arr[np.ix_(np.clip(xs, 0, n - 1), np.clip(zs, 0, n - 1))]
        if not inside.all():
            base = self.tm.window(x0, z0, w, l, name).astype(np.int32)
            if name != "water":
                base = np.where(base == NONE, self.tm.sea_level - 20, base)
            out = np.where(inside, out, base)
        return out

    def _update_field(self, x0, z0, new_h, mask):
        W, L = new_h.shape
        xs = np.arange(x0, x0 + W) - self.hx0
        zs = np.arange(z0, z0 + L) - self.hz0
        n = self.h_ground.shape[0]
        okx = (xs >= 0) & (xs < n)
        okz = (zs >= 0) & (zs < n)
        if not okx.any() or not okz.any():
            return
        ix = np.ix_(xs[okx], zs[okz])
        m = mask[np.ix_(okx, okz)]
        nh = new_h[np.ix_(okx, okz)]
        g = self.h_ground[ix]
        w = self.h_water[ix]
        self.h_ground[ix] = np.where(m, nh, g)
        self.h_top[ix] = np.where(m, nh, self.h_top[ix])
        self.h_water[ix] = np.where(m & (w != NONE) & (nh >= w), NONE, w)

    # ------------------------------------------------------------------
    @property
    def sea(self) -> int:
        return self.tm.sea_level

    def B(self, name: str, **props) -> int:
        return self.reg(name, **props)

    def poi(self, name: str, x, y, z, desc: str = "") -> None:
        self.pois[name] = {"x": int(x), "y": int(y), "z": int(z), "desc": desc}

    def claim(self, x, z, r) -> None:
        self.claims.append((int(x), int(z), float(r)))

    def ground(self, x, z) -> int:
        return int(self.field(int(x), int(z), 1, 1)[0, 0])

    def ground_median(self, x, z, r: int = 8) -> int:
        return int(np.median(self.field(int(x) - r, int(z) - r, 2 * r + 1, 2 * r + 1)))

    def ground_max(self, x, z, r: int = 8) -> int:
        return int(self.field(int(x) - r, int(z) - r, 2 * r + 1, 2 * r + 1).max())

    def is_water(self, x, z) -> bool:
        return int(self.field(int(x), int(z), 1, 1, "water")[0, 0]) != NONE

    def water_frac(self, x, z, r: int) -> float:
        w = self.field(int(x) - r, int(z) - r, 2 * r + 1, 2 * r + 1, "water")
        return float((w != NONE).mean())

    def surface_ids(self, x0: int, z0: int, w: int, l: int, fallback: int | None = None):
        surf = self.tm.window(x0, z0, w, l, "surf")
        water = self.tm.window(x0, z0, w, l, "water") != NONE
        land_cats = surf[~water]
        if fallback is None:
            if land_cats.size:
                vals, counts = np.unique(land_cats, return_counts=True)
                fallback = int(vals[counts.argmax()])
            else:
                fallback = S_GRASS
        surf = np.where(water, fallback, surf)
        top_lut = np.zeros(256, np.uint16)
        sub_lut = np.zeros(256, np.uint16)
        for cat, (t, s) in SURFACE_BLOCKS.items():
            top_lut[cat] = self.reg.id(t)
            sub_lut[cat] = self.reg.id(s)
        top_lut[top_lut == 0] = self.reg.id(SURFACE_BLOCKS[S_GRASS][0])
        sub_lut[sub_lut == 0] = self.reg.id(SURFACE_BLOCKS[S_GRASS][1])
        return top_lut[surf], sub_lut[surf]

    # ------------------------------------------------------------------
    # terrain integration
    # ------------------------------------------------------------------
    def shape_terrain(self, x0: int, z0: int, new_h: np.ndarray, mask: np.ndarray,
                      top=None, sub=None, keep_water: bool = True, buf: EditBuffer | None = None) -> None:
        """Set the ground surface of masked columns to ``new_h``.

        Raises with subsurface fill, lowers by carving, clears vegetation
        above, keeps sea/lake water where the new surface is below it.
        """
        buf = buf or self.terrain
        W, L = new_h.shape
        g = self.field(x0, z0, W, L, "ground")
        t = self.field(x0, z0, W, L, "top")
        w = self.field(x0, z0, W, L, "water")
        t = np.maximum(t, g)
        new_h = np.asarray(new_h, np.int32)
        if top is None or sub is None:
            tt, ss = self.surface_ids(x0, z0, W, L)
            top = tt if top is None else top
            sub = ss if sub is None else sub
        top = np.broadcast_to(np.asarray(top, np.uint16) if not isinstance(top, str) else
                              np.uint16(self.reg.id(top)), (W, L)).copy()
        sub = np.broadcast_to(np.asarray(sub, np.uint16) if not isinstance(sub, str) else
                              np.uint16(self.reg.id(sub)), (W, L)).copy()
        top[~mask] = 0
        sub[~mask] = 0
        ceiling = np.maximum(np.maximum(t, g), np.where(w != NONE, w, -9999)) + 1
        # 1. clear everything above the new surface
        lo = np.where(mask, new_h + 1, 0)
        hi = np.where(mask, ceiling, 0)
        buf.fill_columns(x0, z0, lo, hi, AIR)
        # 2. restore water where the new surface sits below the old water level
        if keep_water:
            wm = mask & (w != NONE) & (new_h < w)
            buf.fill_columns(x0, z0, np.where(wm, new_h + 1, 0), np.where(wm, w + 1, 0),
                             "minecraft:water[level=0]")
        # 3. subsurface (raise) - also re-skin 3 blocks under a lowered surface
        lo = np.where(mask, np.minimum(g + 1, new_h - 3), 0)
        hi = np.where(mask, new_h, 0)
        buf.fill_columns(x0, z0, lo, hi, sub)
        # 4. top block
        buf.fill_columns(x0, z0, np.where(mask, new_h, 0), np.where(mask, new_h + 1, 0), top)
        self._update_field(x0, z0, new_h, mask)

    def level_pad(self, cx: int, cz: int, r_in: float, r_out: float, y: int,
                  rz_in: float | None = None, top=None, sub=None, square: bool = False) -> None:
        """Flatten an (elliptical) pad at height y and blend to terrain by r_out."""
        rz_in = r_in if rz_in is None else rz_in
        R = int(math.ceil(max(r_out, r_out * rz_in / max(r_in, 1e-6)))) + 1
        x0, z0 = int(cx) - R, int(cz) - R
        n = 2 * R + 1
        dx = np.arange(n)[:, None] - R
        dz = np.arange(n)[None, :] - R
        if square:
            d_in = np.maximum(np.abs(dx) / max(r_in, 1e-6), np.abs(dz) / max(rz_in, 1e-6))
        else:
            d_in = np.sqrt((dx / max(r_in, 1e-6)) ** 2 + (dz / max(rz_in, 1e-6)) ** 2)
        # distance beyond the inner shape, in blocks (approx.)
        beyond = np.maximum(d_in - 1.0, 0) * max(r_in, rz_in)
        margin = max(r_out - r_in, 1.0)
        s = smoothstep(beyond / margin)
        g = self.field(x0, z0, n, n, "ground").astype(np.float32)
        new_h = np.rint(y * (1 - s) + g * s).astype(np.int32)
        mask = beyond < margin
        self.shape_terrain(x0, z0, new_h, mask, top=top, sub=sub)
        self.integration.append(f"level pad r={r_in:.0f}->{r_out:.0f} at y={y}")

    def clear_vegetation(self, cx: int, cz: int, r: float) -> None:
        R = int(r) + 1
        x0, z0 = int(cx) - R, int(cz) - R
        n = 2 * R + 1
        d = np.hypot(np.arange(n)[:, None] - R, np.arange(n)[None, :] - R)
        g = self.field(x0, z0, n, n, "ground")
        t = self.field(x0, z0, n, n, "top")
        m = (d <= r) & (t > g) & (self.field(x0, z0, n, n, "water") == NONE)
        self.terrain.fill_columns(x0, z0, np.where(m, g + 1, 0), np.where(m, t + 1, 0), AIR)
        self._update_field(x0, z0, np.where(m, g, g), m)

    # ------------------------------------------------------------------
    def place(self, canvas: Canvas, cx: int, cz: int, base_y: int, facing: str = "south",
              anchor: tuple[int, int, int] | None = None, foundation: str | None = None,
              buf: EditBuffer | None = None, connect: bool = True) -> Placement:
        """Paste ``canvas`` so that local ``anchor`` lands on (cx, base_y, cz).

        The canvas front is its +z side; ``facing`` rotates it in place.
        ``foundation`` fills from the canvas floor down to the ground under
        every column the canvas occupies at its anchor level.
        """
        buf = buf or self.struct
        X, Y, Z = canvas.size
        if anchor is None:
            anchor = (X // 2, 0, Z // 2)
        q = TURNS[facing]
        if connect:
            canvas.connect()
        rc = canvas.rotated(q) if q else canvas
        pl = Placement(q, (X, Y, Z), (0, 0, 0))
        ax, ay, az = pl.to_world(*anchor)
        origin = (int(cx) - ax, int(base_y) - ay, int(cz) - az)
        pl.origin = origin
        rc.paste(buf, *origin)
        if foundation:
            floor = rc.ids[:, anchor[1], :] != 0
            if floor.any():
                RX, _, RZ = rc.size
                g = self.field(origin[0], origin[2], RX, RZ, "ground")
                lo = np.where(floor, np.minimum(g - 2, base_y - 1), 0)
                hi = np.where(floor, base_y, 0)
                buf.fill_columns(origin[0], origin[2], lo, hi, foundation, mode=SOFT)
        return pl


def facing_from_vector(dx: float, dz: float) -> str:
    if abs(dx) > abs(dz):
        return "east" if dx > 0 else "west"
    return "south" if dz > 0 else "north"


def canvas(reg: Registry, x: int, y: int, z: int) -> Canvas:
    return Canvas(reg, (int(x), int(y), int(z)))


# --------------------------------------------------------------------------
# oriented local frames
# --------------------------------------------------------------------------
def rot2d(a: np.ndarray, q: int) -> np.ndarray:
    """Rotate an [x, z] array the same way Canvas.rotated rotates [x, y, z]."""
    for _ in range(q % 4):
        a = np.flip(a.T, axis=0)
    return a


def shape_local(ctx: BuildContext, cx: int, cz: int, facing: str, new_h_local: np.ndarray,
                mask_local: np.ndarray, anchor_xz: tuple[int, int] | None = None, top=None, sub=None) -> None:
    """shape_terrain with a height field authored in a canvas-local frame."""
    W, L = new_h_local.shape
    ax, az = anchor_xz if anchor_xz is not None else (W // 2, L // 2)
    q = TURNS[facing]
    pl = Placement(q, (W, 1, L), (0, 0, 0))
    wx, _, wz = pl.to_world(ax, 0, az)
    x0, z0 = int(cx) - wx, int(cz) - wz
    if isinstance(top, np.ndarray):
        top = rot2d(top, q)
    if isinstance(sub, np.ndarray):
        sub = rot2d(sub, q)
    ctx.shape_terrain(x0, z0, rot2d(new_h_local, q), rot2d(mask_local, q), top=top, sub=sub)


def local_field(ctx: BuildContext, cx: int, cz: int, facing: str, W: int, L: int,
                anchor_xz: tuple[int, int] | None = None, name: str = "ground") -> np.ndarray:
    """Terrain field sampled in a canvas-local frame (inverse of shape_local)."""
    ax, az = anchor_xz if anchor_xz is not None else (W // 2, L // 2)
    q = TURNS[facing]
    pl = Placement(q, (W, 1, L), (0, 0, 0))
    wx, _, wz = pl.to_world(ax, 0, az)
    RW, RL = (W, L) if q % 2 == 0 else (L, W)
    x0, z0 = int(cx) - wx, int(cz) - wz
    world = ctx.field(x0, z0, RW, RL, name)
    return rot2d(world, (4 - q) % 4)


def water_direction(ctx: BuildContext, x: int, z: int, r: int = 220) -> tuple[float, float]:
    """Unit vector from (x, z) toward the centroid of nearby water."""
    w = ctx.field(x - r, z - r, 2 * r + 1, 2 * r + 1, "water") != NONE
    if not w.any():
        return (0.0, 1.0)
    xs, zs = np.nonzero(w)
    dx, dz = xs.mean() - r, zs.mean() - r
    n = math.hypot(dx, dz) or 1.0
    return dx / n, dz / n


def facing_of(dx: float, dz: float) -> str:
    return facing_from_vector(dx, dz)


def unit(facing: str) -> tuple[int, int]:
    return {"south": (0, 1), "north": (0, -1), "east": (1, 0), "west": (-1, 0)}[facing]
