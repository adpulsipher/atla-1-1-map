"""Reusable architectural pieces shared by the landmark builders.

All functions draw on a :class:`~atla_builder.buffer.Primitives` target (a
local Canvas or a world EditBuffer) in that target's coordinates.
"""
from __future__ import annotations

import math

import numpy as np

from ..buffer import SET, SOFT, Canvas
from ..palettes import Palette

AIR_S = "minecraft:air"
WATER_S = "minecraft:water[level=0]"
LEAF_PROPS = "[distance=1,persistent=true,waterlogged=false]"


def stair(p, name: str, facing: str, half: str = "bottom", shape: str = "straight") -> int:
    return p.reg(name, facing=facing, half=half, shape=shape, waterlogged=False)


def leaves(name: str) -> str:
    return f"minecraft:{name}_leaves{LEAF_PROPS}"


def log(name: str, axis: str = "y") -> str:
    return f"minecraft:{name}[axis={axis}]"


def toward_center(dx: float, dz: float) -> str:
    """Facing that points from offset (dx, dz) back to the centre."""
    if abs(dx) >= abs(dz):
        return "west" if dx > 0 else "east"
    return "north" if dz > 0 else "south"


# --------------------------------------------------------------------------
# roofs
# --------------------------------------------------------------------------
def hip_roof(p, x0, z0, x1, z1, y, stairs: str, full: str, overhang: int = 1, flare: bool = True,
             ridge: str | None = None, fill_top: bool = True, max_levels: int = 99, mode=SET) -> int:
    """East-Asian hip roof with upturned corners. Returns the ridge y."""
    xa, za, xb, zb = x0 - overhang, z0 - overhang, x1 + overhang, z1 + overhang
    lvl = 0
    ridge = ridge or full
    while lvl < max_levels:
        yy = y + lvl
        if xb - xa < 1 or zb - za < 1:
            p.box(xa, yy, za, xb, yy, zb, ridge, mode)
            return yy
        if xb - xa == 1 or zb - za == 1:
            p.box(xa, yy, za, xb, yy, zb, full, mode)
            p.box(xa, yy + 1, za, xb, yy + 1, zb, p.slab(stairs.replace("_stairs", "_slab")) if
                  "stairs" in stairs else ridge, mode)
            return yy + 1
        for x in range(xa + 1, xb):
            p.set(x, yy, za, stair(p, stairs, "south"), mode)
            p.set(x, yy, zb, stair(p, stairs, "north"), mode)
        for z in range(za + 1, zb):
            p.set(xa, yy, z, stair(p, stairs, "east"), mode)
            p.set(xb, yy, z, stair(p, stairs, "west"), mode)
        p.set(xa, yy, za, stair(p, stairs, "south", shape="outer_left"), mode)
        p.set(xb, yy, za, stair(p, stairs, "south", shape="outer_right"), mode)
        p.set(xa, yy, zb, stair(p, stairs, "north", shape="outer_right"), mode)
        p.set(xb, yy, zb, stair(p, stairs, "north", shape="outer_left"), mode)
        if lvl == 0 and flare:
            # upturned eave tips: raise the four corners one block
            for (cx, cz, f) in ((xa, za, "south"), (xb, za, "west"), (xa, zb, "east"), (xb, zb, "north")):
                p.set(cx, yy, cz, full, mode)
                p.set(cx, yy + 1, cz, stair(p, stairs, f, half="bottom"), mode)
        if fill_top:
            p.box(xa + 1, yy, za + 1, xb - 1, yy, zb - 1, full, mode)
        xa, za, xb, zb = xa + 1, za + 1, xb - 1, zb - 1
        lvl += 1
    return y + lvl


def gable_roof(p, x0, z0, x1, z1, y, stairs: str, full: str, axis: str = "x", overhang: int = 1,
               gable: str | None = None, mode=SET) -> int:
    """Pitched roof; ridge runs along ``axis``. Gable ends filled with ``gable``."""
    xa, za, xb, zb = x0 - overhang, z0 - overhang, x1 + overhang, z1 + overhang
    lvl = 0
    if axis == "x":
        lo, hi = za, zb
        while hi - lo >= 0:
            yy = y + lvl
            if hi - lo <= 1:
                p.box(xa, yy, lo, xb, yy, hi, full, mode)
                return yy
            p.box(xa, yy, lo, xb, yy, lo, stair(p, stairs, "south"), mode)
            p.box(xa, yy, hi, xb, yy, hi, stair(p, stairs, "north"), mode)
            if gable and lvl > 0:
                p.box(x0, yy, lo + 1, x0, yy, hi - 1, gable, mode)
                p.box(x1, yy, lo + 1, x1, yy, hi - 1, gable, mode)
            lo, hi, lvl = lo + 1, hi - 1, lvl + 1
    else:
        lo, hi = xa, xb
        while hi - lo >= 0:
            yy = y + lvl
            if hi - lo <= 1:
                p.box(lo, yy, za, hi, yy, zb, full, mode)
                return yy
            p.box(lo, yy, za, lo, yy, zb, stair(p, stairs, "east"), mode)
            p.box(hi, yy, za, hi, yy, zb, stair(p, stairs, "west"), mode)
            if gable and lvl > 0:
                p.box(lo + 1, yy, z0, hi - 1, yy, z0, gable, mode)
                p.box(lo + 1, yy, z1, hi - 1, yy, z1, gable, mode)
            lo, hi, lvl = lo + 1, hi - 1, lvl + 1
    return y + lvl


def cone_roof(p, cx, cz, y, r: float, stairs: str, full: str, height: int | None = None,
              tip: str | None = "minecraft:gold_block", mode=SET) -> int:
    """Steep conical roof (Air Nomad towers). Returns top y."""
    height = height or int(round(r * 1.8))
    for i in range(height):
        rr = r * (1 - i / height)
        if rr < 0.6:
            p.set(cx, y + i, cz, full, mode)
            continue
        R = int(math.ceil(rr))
        xs = np.arange(-R, R + 1)
        dx, dz = np.meshgrid(xs, xs, indexing="ij")
        d = np.hypot(dx, dz)
        ring = (d <= rr + 0.5) & (d > rr - 0.9)
        inner = d <= rr - 0.9
        if inner.any():
            p.column_mask(cx - R, cz - R, inner, y + i, y + i, full, mode)
        for a, b in zip(*np.nonzero(ring)):
            ox, oz = int(xs[a]), int(xs[b])
            p.set(cx + ox, y + i, cz + oz, stair(p, stairs, toward_center(ox, oz)), mode)
    top = y + height
    if tip:
        p.set(cx, top, cz, tip, mode)
        p.set(cx, top + 1, cz, "minecraft:lightning_rod[facing=up,powered=false,waterlogged=false]", mode)
        top += 1
    return top


def dome(p, cx, cy, cz, r: float, block, mode=SET, ry: float | None = None) -> None:
    p.ellipsoid(cx, cy, cz, r, ry or r, r, block, mode, hollow=True, lower=False)


# --------------------------------------------------------------------------
# buildings
# --------------------------------------------------------------------------
def house(p, x0, y0, z0, w: int, d: int, pal: Palette, stories: int = 1, story_h: int = 4,
          roof: str = "hip", door: bool = True, windows: bool = True, overhang: int = 1,
          rng=None, lantern: bool = True, mode=SET) -> int:
    """Generic East-Asian timber house; front (door) on the +z side.

    Returns the top y of the roof.
    """
    x1, z1 = x0 + w - 1, z0 + d - 1
    h = stories * story_h
    p.box(x0, y0, z0, x1, y0, z1, pal.foundation, mode)
    p.box(x0 + 1, y0, z0 + 1, x1 - 1, y0, z1 - 1, pal.floor, mode)
    p.box(x0 + 1, y0 + 1, z0 + 1, x1 - 1, y0 + h, z1 - 1, AIR_S, mode)
    p.walls(x0, y0 + 1, z0, x1, y0 + h, z1, pal.wall, mode)
    for (x, z) in ((x0, z0), (x1, z0), (x0, z1), (x1, z1)):
        p.box(x, y0 + 1, z, x, y0 + h, z, pal.post, mode)
    # mid posts on long walls
    for x in range(x0 + 4, x1 - 1, 4):
        p.box(x, y0 + 1, z0, x, y0 + h, z0, pal.post, mode)
        p.box(x, y0 + 1, z1, x, y0 + h, z1, pal.post, mode)
    for z in range(z0 + 4, z1 - 1, 4):
        p.box(x0, y0 + 1, z, x0, y0 + h, z, pal.post, mode)
        p.box(x1, y0 + 1, z, x1, y0 + h, z, pal.post, mode)
    for s in range(1, stories + 1):
        yb = y0 + s * story_h
        beam_x = pal.trim.replace("axis=y", "axis=x")
        beam_z = pal.trim.replace("axis=y", "axis=z")
        p.box(x0, yb, z0, x1, yb, z0, beam_x, mode)
        p.box(x0, yb, z1, x1, yb, z1, beam_x, mode)
        p.box(x0, yb, z0, x0, yb, z1, beam_z, mode)
        p.box(x1, yb, z0, x1, yb, z1, beam_z, mode)
        if s < stories:
            p.box(x0 + 1, yb, z0 + 1, x1 - 1, yb, z1 - 1, pal.floor, mode)
        if windows:
            wy = yb - story_h + 2
            for x in range(x0 + 2, x1 - 1, 4):
                p.box(x, wy, z0, x, wy + 1, z0, "minecraft:air", mode)
                p.box(x, wy, z1, x, wy + 1, z1, "minecraft:air", mode)
                p.set(x, wy, z0, _win(pal, "north"), mode)
                p.set(x, wy, z1, _win(pal, "south"), mode)
            for z in range(z0 + 2, z1 - 1, 4):
                p.set(x0, wy, z, _win(pal, "west"), mode)
                p.set(x1, wy, z, _win(pal, "east"), mode)
    if door:
        cx = (x0 + x1) // 2
        p.box(cx, y0 + 1, z1, cx, y0 + 2, z1, AIR_S, mode)
        p.box(cx - 1, y0 + 3, z1, cx + 1, y0 + 3, z1, pal.door_frame, mode)
        if lantern:
            p.set(cx + 1, y0 + 3, z1 + 1, "minecraft:lantern[hanging=true,waterlogged=false]", mode)
        p.set(cx, y0 + 1, z1 + 1, "minecraft:air", mode)
    ry = y0 + h + 1
    if roof == "hip":
        top = hip_roof(p, x0, z0, x1, z1, ry, pal.roof_stairs, pal.roof, overhang=overhang,
                       ridge=pal.ridge, mode=mode)
    elif roof == "gable":
        axis = "x" if w >= d else "z"
        top = gable_roof(p, x0, z0, x1, z1, ry, pal.roof_stairs, pal.roof, axis=axis,
                         overhang=overhang, gable=pal.wall, mode=mode)
    elif roof == "thatch":
        axis = "x" if w >= d else "z"
        top = gable_roof(p, x0, z0, x1, z1, ry, "minecraft:dark_oak_stairs", "minecraft:hay_block[axis=y]",
                         axis=axis, overhang=overhang, gable=pal.wall, mode=mode)
    else:
        p.box(x0 - overhang, ry, z0 - overhang, x1 + overhang, ry, z1 + overhang, pal.roof_slab, mode)
        top = ry
    return top


def _win(pal: Palette, facing: str) -> str:
    if "trapdoor" in pal.window:
        return pal.window.replace("facing=north", f"facing={facing}")
    return pal.window


def house_canvas(reg, w: int, d: int, pal: Palette, stories: int = 1, story_h: int = 4,
                 roof: str = "hip", overhang: int = 1, stilts: int = 0, **kw) -> Canvas:
    """A house on its own canvas; anchor = (w//2 + overhang, stilts, d//2 + overhang)."""
    H = stilts + stories * story_h + max(w, d) // 2 + 6
    c = Canvas(reg, (w + 2 * overhang + 2, H, d + 2 * overhang + 2))
    ox = oz = overhang + 1
    if stilts:
        for (x, z) in ((ox, oz), (ox + w - 1, oz), (ox, oz + d - 1), (ox + w - 1, oz + d - 1),
                       (ox + w // 2, oz), (ox + w // 2, oz + d - 1)):
            c.box(x, 0, z, x, stilts - 1, z, pal.post)
    house(c, ox, stilts, oz, w, d, pal, stories, story_h, roof, overhang=overhang, **kw)
    return c


def pagoda(p, cx, cz, y, base: int, tiers: int, pal: Palette, tier_h: int = 5, shrink: int = 2,
           spire: str | None = None, mode=SET) -> int:
    """Stacked multi-eave pagoda tower. Returns top y."""
    half = base // 2
    yy = y
    for t in range(tiers):
        hw = max(1, half - t * shrink // 2 * 1 - t)
        x0, z0, x1, z1 = cx - hw, cz - hw, cx + hw, cz + hw
        p.box(x0, yy, z0, x1, yy + tier_h - 1, z1, pal.wall, mode)
        p.box(x0 + 1, yy + 1, z0 + 1, x1 - 1, yy + tier_h - 1, z1 - 1, AIR_S, mode) if hw > 2 else None
        for (x, z) in ((x0, z0), (x1, z0), (x0, z1), (x1, z1)):
            p.box(x, yy, z, x, yy + tier_h - 1, z, pal.post, mode)
        if hw > 1:
            for x in range(x0 + 2, x1 - 1, 3):
                p.box(x, yy + 1, z1, x, yy + 2, z1, AIR_S, mode)
                p.box(x, yy + 1, z0, x, yy + 2, z0, AIR_S, mode)
        top = hip_roof(p, x0, z0, x1, z1, yy + tier_h, pal.roof_stairs, pal.roof, overhang=2,
                       max_levels=2, ridge=pal.ridge, mode=mode)
        yy = yy + tier_h + 2
    top = hip_roof(p, cx - 1, cz - 1, cx + 1, cz + 1, yy - 1, pal.roof_stairs, pal.roof, overhang=1,
                   ridge=pal.ridge, mode=mode)
    if spire:
        p.box(cx, top + 1, cz, cx, top + 3, cz, spire, mode)
        top += 3
    return top


def air_tower(p, cx, cz, y, r: float, h: int, pal: Palette, roof_h: int | None = None,
              windows: bool = True, balcony: bool = True, mode=SET) -> int:
    """Cylindrical Air Nomad tower with a steep turquoise cone roof."""
    p.cyl(cx, cz, y, y + h - 1, r, pal.wall, mode, hollow=True, thickness=1.0)
    p.cyl(cx, cz, y, y, r - 0.5, pal.floor, mode)
    if r > 2.5:
        p.cyl(cx, cz, y + 1, y + h - 1, r - 1.2, AIR_S, mode)
    # trim bands
    p.cyl(cx, cz, y + h - 1, y + h - 1, r + 0.2, pal.trim, mode, hollow=True, thickness=1.0)
    if windows and r >= 3:
        R = int(r)
        for (dx, dz) in ((R, 0), (-R, 0), (0, R), (0, -R)):
            for wy in range(y + 3, y + h - 3, 6):
                p.box(cx + dx, wy, cz + dz, cx + dx, wy + 2, cz + dz, AIR_S, mode)
    if balcony and h > 12:
        p.cyl(cx, cz, y + h, y + h, r + 1.6, pal.trim, mode)
    top = cone_roof(p, cx, cz, y + h + (1 if balcony and h > 12 else 0), r + (1.6 if balcony and h > 12 else 1.0),
                    pal.roof_stairs, pal.roof, height=roof_h, tip=pal.accent, mode=mode)
    return top


def igloo(p, cx, y, cz, r: int, door: str = "south", mode=SET) -> None:
    p.ellipsoid(cx, y, cz, r, r, r, "minecraft:snow_block", mode, hollow=True, lower=False)
    p.ellipsoid(cx, y, cz, r - 1, r - 1, r - 1, AIR_S, mode, lower=False)
    p.cyl(cx, cz, y, y, r - 1, "minecraft:white_wool", mode)
    dx, dz = {"south": (0, 1), "north": (0, -1), "east": (1, 0), "west": (-1, 0)}[door]
    for k in range(r - 1, r + 3):
        x, z = cx + dx * k, cz + dz * k
        if abs(dx):
            p.box(x, y, z - 2, x, y + 3, z + 2, "minecraft:snow_block", mode)
            p.box(x, y + 1, z - 1, x, y + 2, z + 1, AIR_S, mode)
        else:
            p.box(x - 2, y, z, x + 2, y + 3, z, "minecraft:snow_block", mode)
            p.box(x - 1, y + 1, z, x + 1, y + 2, z, AIR_S, mode)
    p.set(cx, y + 1, cz, "minecraft:lantern[hanging=false,waterlogged=false]", mode)


def hide_tent(p, cx, y, cz, r: int, h: int, hide: str = "minecraft:brown_wool", mode=SET) -> None:
    for i in range(h):
        rr = r * (1 - i / h) + 0.4
        p.cyl(cx, cz, y + i, y + i, rr, hide, mode, hollow=True, thickness=1.1)
    p.box(cx, y, cz, cx, y + h + 1, cz, "minecraft:spruce_fence", mode)
    p.box(cx, y + 1, cz + r - 1, cx, y + 2, cz + r, AIR_S, mode)
    p.box(cx, y + h - 1, cz, cx, y + h + 1, cz, "minecraft:spruce_fence", mode)
    p.set(cx + r - 1, y + h // 2 + 1, cz, "minecraft:light_blue_wool", mode)


# --------------------------------------------------------------------------
# vegetation & detail
# --------------------------------------------------------------------------
def tree(p, x, y, z, kind: str = "oak", height: int = 6, rng=None, mode=SOFT) -> None:
    rng = rng or np.random.default_rng(x * 31 + z)
    if kind == "palm":
        lean = rng.integers(-1, 2, size=2)
        for i in range(height):
            p.set(x + lean[0] * i // max(height // 2, 1), y + i, z + lean[1] * i // max(height // 2, 1),
                  log("jungle_log"), mode)
        tx, tz = x + lean[0] * (height - 1) // max(height // 2, 1), z + lean[1] * (height - 1) // max(height // 2, 1)
        top = y + height
        lf = leaves("jungle")
        p.set(tx, top, tz, lf, mode)
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            for k in range(1, 4):
                p.set(tx + dx * k, top - (1 if k == 3 else 0), tz + dz * k, lf, mode)
        return
    trunk = {"oak": "oak_log", "cherry": "cherry_log", "spruce": "spruce_log", "dark_oak": "dark_oak_log",
             "jungle": "jungle_log", "mangrove": "mangrove_log", "birch": "birch_log",
             "burnt": "basalt", "acacia": "acacia_log"}[kind]
    leaf = {"oak": "oak", "cherry": "cherry", "spruce": "spruce", "dark_oak": "dark_oak", "jungle": "jungle",
            "mangrove": "mangrove", "birch": "birch", "acacia": "acacia"}.get(kind)
    p.box(x, y, z, x, y + height - 1, z, log(trunk) if kind != "burnt" else "minecraft:basalt[axis=y]", mode)
    if kind == "burnt":
        for (dx, dz) in ((1, 0), (0, -1)):
            if rng.random() < 0.6:
                h2 = int(rng.integers(height // 2, height))
                p.set(x + dx, y + h2, z + dz, "minecraft:polished_basalt[axis=x]", mode)
        return
    if kind == "spruce":
        for i in range(height - 1):
            rr = max(0.6, (height - i) / 2.5)
            if i >= 2:
                p.cyl(x, z, y + i, y + i, rr, leaves(leaf), SOFT)
        p.set(x, y + height, z, leaves(leaf), SOFT)
        return
    r = 2.6 if kind in ("oak", "birch", "acacia") else 3.2
    p.ellipsoid(x, y + height - 1, z, r, 2.2, r, leaves(leaf), SOFT)


def lantern_post(p, x, y, z, post: str = "minecraft:spruce_fence", h: int = 3, mode=SET) -> None:
    p.box(x, y, z, x, y + h - 1, z, post, mode)
    p.set(x, y + h, z, "minecraft:lantern[hanging=false,waterlogged=false]", mode)


def blocky_statue(p, cx, y, cz, scale: int, colors: dict, facing: str = "south", mode=SET) -> int:
    """A standing robed figure (used for Avatar statues). Returns top y.

    colors keys: robe, robe_trim, skin, hair, belt, accent, base.
    Built facing +z; rotate the canvas for other facings.
    """
    s = scale
    base_h = max(2, s)
    p.box(cx - 4 * s, y, cz - 3 * s, cx + 4 * s, y + base_h - 1, cz + 3 * s, colors.get("base", "minecraft:stone_bricks"), mode)
    y0 = y + base_h
    # robe (widening towards the hem)
    robe_h = 9 * s
    for i in range(robe_h):
        hw = int(round(3.2 * s - i * (0.9 * s) / robe_h * 1.0))
        hd = int(round(2.2 * s - i * (0.5 * s) / robe_h))
        p.box(cx - hw, y0 + i, cz - hd, cx + hw, y0 + i, cz + hd, colors["robe"], mode)
    # hem trim & front panel
    p.box(cx - int(3.2 * s), y0, cz - int(2.2 * s), cx + int(3.2 * s), y0, cz + int(2.2 * s), colors["robe_trim"], mode)
    p.box(cx - s // 2, y0, cz + int(2.2 * s) - 0, cx + s // 2, y0 + robe_h - 1, cz + int(2.2 * s), colors["robe_trim"], mode)
    yb = y0 + int(robe_h * 0.55)
    p.box(cx - int(2.6 * s), yb, cz - int(2.0 * s), cx + int(2.6 * s), yb + max(0, s - 1), cz + int(2.0 * s), colors["belt"], mode)
    # torso / shoulders
    yt = y0 + robe_h
    p.box(cx - 3 * s, yt, cz - int(1.6 * s), cx + 3 * s, yt + 3 * s - 1, cz + int(1.6 * s), colors["robe"], mode)
    p.box(cx - 3 * s, yt + 3 * s - 1, cz - int(1.6 * s), cx + 3 * s, yt + 3 * s - 1, cz + int(1.6 * s), colors["robe_trim"], mode)
    # arms forward holding fans
    for sgn in (-1, 1):
        ax = cx + sgn * 3 * s
        p.box(ax - (s - 1) * (sgn < 0), yt + s, cz - s // 2, ax + (s - 1) * (sgn > 0), yt + 3 * s - 1, cz + s // 2, colors["robe"], mode)
        p.box(ax - (s - 1) * (sgn < 0), yt + s, cz + s // 2 + 1, ax + (s - 1) * (sgn > 0), yt + 2 * s - 1, cz + 2 * s, colors["robe"], mode)
        fx = ax + sgn * s
        p.box(fx - s // 2, yt + s, cz + 2 * s, fx + s // 2, yt + 3 * s, cz + 2 * s + max(0, s // 2), colors["accent"], mode)
    # head
    yh = yt + 3 * s
    p.box(cx - s, yh, cz - s, cx + s, yh + 2 * s, cz + s, colors["skin"], mode)
    p.box(cx - s, yh + 2 * s - max(1, s // 2), cz - s, cx + s, yh + 2 * s, cz + s, colors["hair"], mode)
    # headdress (Kyoshi's gold crown)
    top = yh + 2 * s + 1
    p.box(cx - s - 1, top, cz - s, cx + s + 1, top + s, cz + s, colors["accent"], mode)
    p.box(cx, top + s + 1, cz, cx, top + 2 * s, cz, colors["accent"], mode)
    # face paint: eyes / red eye shadow
    fz = cz + s
    ey = yh + s + max(0, s // 2)
    p.set(cx - max(1, s // 2), ey, fz, colors.get("eyes", "minecraft:black_concrete"), mode)
    p.set(cx + max(1, s // 2), ey, fz, colors.get("eyes", "minecraft:black_concrete"), mode)
    p.set(cx, yh + max(1, s // 2), fz, colors.get("mouth", "minecraft:red_concrete"), mode)
    return top + 2 * s


def bridge(p, x0, z0, x1, z1, y, width: int, deck: str, rail: str, mode=SET, arch: int = 0) -> None:
    """Straight bridge between two points (axis aligned or diagonal)."""
    n = int(max(abs(x1 - x0), abs(z1 - z0))) + 1
    for i in range(n):
        t = i / max(n - 1, 1)
        x = int(round(x0 + (x1 - x0) * t))
        z = int(round(z0 + (z1 - z0) * t))
        yy = y + int(round(arch * math.sin(math.pi * t)))
        hw = width // 2
        if abs(x1 - x0) >= abs(z1 - z0):
            p.box(x, yy, z - hw, x, yy, z + hw, deck, mode)
            p.set(x, yy + 1, z - hw - 1, rail, mode)
            p.set(x, yy + 1, z + hw + 1, rail, mode)
            p.box(x, yy + 1, z - hw, x, yy + 3, z + hw, AIR_S, mode)
        else:
            p.box(x - hw, yy, z, x + hw, yy, z, deck, mode)
            p.set(x - hw - 1, yy + 1, z, rail, mode)
            p.set(x + hw + 1, yy + 1, z, rail, mode)
            p.box(x - hw, yy + 1, z, x + hw, yy + 3, z, AIR_S, mode)


def boat(p, x, y, z, length: int, beam: int, hull: str = "minecraft:spruce_planks",
         deck: str = "minecraft:spruce_slab[type=bottom,waterlogged=false]", cabin_pal: Palette | None = None,
         mode=SET) -> None:
    """Simple wooden boat along +x, keel at y (waterline y+1)."""
    hb = beam // 2
    for i in range(length):
        t = i / (length - 1)
        taper = 1.0 - (abs(t - 0.45) / 0.55) ** 2.2
        w = max(0, int(round(hb * max(taper, 0.15))))
        p.box(x + i, y, z - max(0, w - 1), x + i, y, z + max(0, w - 1), hull, mode)
        p.box(x + i, y + 1, z - w, x + i, y + 2, z + w, hull, mode)
        if w > 1:
            p.box(x + i, y + 1, z - w + 1, x + i, y + 2, z + w - 1, AIR_S, mode)
            p.box(x + i, y + 1, z - w + 1, x + i, y + 1, z + w - 1, hull, mode)
    if cabin_pal and length > 14:
        cx0 = x + length // 3
        house(p, cx0, y + 2, z - hb + 2, length // 3, beam - 4, cabin_pal, 1, 3, "hip", door=False,
              windows=True, overhang=1, lantern=False, mode=mode)
