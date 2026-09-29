"""Air Nomad temples: Southern, Northern (Mechanist), Eastern, Western (inverted)."""
from __future__ import annotations

import math

import numpy as np

from ..buffer import SOFT, Canvas
from ..palettes import AIR
from . import kit
from .common import BuildContext, unit

MAX_Y = 318
AIR_S = "minecraft:air"


def _foundation_column(ctx: BuildContext, x, z, y_top, r, block=None) -> None:
    """Rock/masonry pillar from the terrain up to y_top under a tower."""
    block = block or AIR.foundation
    g = ctx.ground_median(x, z, int(r) + 1)
    if g < y_top:
        ctx.struct.cyl(x, z, min(g - 3, y_top - 1), y_top - 1, r + 0.5, block, mode=SOFT)


def _approach_facing(ctx: BuildContext, x, z, r=70) -> str:
    """Direction of the gentlest descent from the site (where stairs go)."""
    best, best_f = None, "south"
    for f in ("north", "south", "east", "west"):
        ux, uz = unit(f)
        g = ctx.ground_median(x + ux * r, z + uz * r, 6)
        if best is None or g > best:  # highest ground at distance = gentlest drop
            best, best_f = g, f
    return best_f


def _stairway(ctx: BuildContext, x, z, y, facing: str, steps: int, width: int = 3,
              mat="minecraft:polished_diorite") -> tuple[int, int, int]:
    """Switchback stair descending from (x,y,z) toward ``facing``; returns end."""
    ux, uz = unit(facing)
    px, pz = -uz, ux
    cx, cz, cy = x, z, y
    run = 14
    side = 1
    for k in range(steps):
        cx += ux
        cz += uz
        cy -= 1
        g = ctx.ground(cx, cz)
        if cy < g - 4:  # stairs dive into the slope: follow the terrain instead
            cy = g
        hw = width // 2
        for w in range(-hw, hw + 1):
            bx, bz = cx + px * w, cz + pz * w
            ctx.struct.set(bx, cy, bz, kit.stair(ctx.struct, "minecraft:polished_diorite_stairs",
                                                  {(1, 0): "west", (-1, 0): "east", (0, 1): "north", (0, -1): "south"}[(ux, uz)]))
            ctx.struct.box(bx, cy - 3, bz, bx, cy - 1, bz, mat, mode=SOFT)
            ctx.struct.box(bx, cy + 1, bz, bx, cy + 4, bz, AIR_S)
        if (k + 1) % run == 0:
            # landing and turn
            ctx.struct.box(cx - 2, cy - 1, cz - 2, cx + 2, cy - 1, cz + 2, mat)
            ctx.struct.box(cx - 2, cy, cz - 2, cx + 2, cy + 4, cz + 2, AIR_S)
            ux, uz, px, pz = px * side, pz * side, ux, uz
            side = -side
    return cx, cy, cz


def _air_symbol(p, x, y, z, axis: str, s: int = 1, block="minecraft:gold_block") -> None:
    """Three-swirl Air Nomad emblem on a vertical plane (axis = plane normal)."""
    pts = []
    for k in range(3):
        a0 = k * 2 * math.pi / 3
        for t in np.linspace(0, 1.0, 12):
            r = (1 + 2.5 * t) * s
            a = a0 + t * 2.4
            pts.append((round(r * math.cos(a)), round(r * math.sin(a))))
    for u, v in set(pts):
        if axis == "z":
            p.set(x + u, y + v, z, block)
        else:
            p.set(x, y + v, z + u, block)


# ==========================================================================
def southern_air_temple(ctx: BuildContext) -> None:
    s = ctx.site
    peak = ctx.ground_max(s.x, s.z, 10)
    py = min(peak - 8, 248)
    cx, cz = s.x, s.z
    ctx.level_pad(cx, cz, 26, 58, py, top="minecraft:polished_diorite", sub="minecraft:stone")
    ctx.integration.append(f"summit cut from y={peak} to a y={py} plaza; temple towers step down the flanks")
    front = _approach_facing(ctx, cx, cz)
    fx, fz = unit(front)
    B = ctx.struct
    # plaza paving pattern
    B.cyl(cx, cz, py, py, 25, AIR.floor)
    B.cyl(cx, cz, py, py, 18, "minecraft:smooth_sandstone", hollow=True, thickness=1.2)
    # --- the sanctuary: large round hall under a great turquoise cone
    B.cyl(cx, cz, py + 1, py + 22, 11, AIR.wall, hollow=True, thickness=1.5)
    B.cyl(cx, cz, py + 1, py + 22, 9.6, AIR_S)
    B.cyl(cx, cz, py + 22, py + 22, 12.5, AIR.trim)
    top = kit.cone_roof(B, cx, cz, py + 23, 13, AIR.roof_stairs, AIR.roof, height=int(min(28, MAX_Y - py - 26)),
                        tip=AIR.accent)
    # Sanctuary door with the air-horn lock (three copper horns) and gold emblem
    dx, dz = cx + fx * 11, cz + fz * 11
    if fx:
        B.box(dx, py + 1, dz - 4, dx, py + 10, dz + 4, "minecraft:cyan_terracotta")
        _air_symbol(B, dx + fx, py + 6, dz, "x")
        for k in (-3, 0, 3):
            B.box(dx + fx, py + 11, dz + k, dx + fx * 3, py + 11, dz + k, "minecraft:cut_copper")
    else:
        B.box(dx - 4, py + 1, dz, dx + 4, py + 10, dz, "minecraft:cyan_terracotta")
        _air_symbol(B, dx, py + 6, dz + fz, "z")
        for k in (-3, 0, 3):
            B.box(dx + k, py + 11, dz + fz, dx + k, py + 11, dz + fz * 3, "minecraft:cut_copper")
    ctx.poi("sanctuary_door", dx + fx * 2, py + 1, dz + fz * 2, "Air-horn lock opened by airbending")
    # Hall of Avatar statues: a spiral of figures inside the sanctuary
    for k in range(14):
        a = k * 2 * math.pi / 14
        sx, sz = int(round(cx + 7 * math.cos(a))), int(round(cz + 7 * math.sin(a)))
        sy = py + 1 + k // 2
        B.box(sx, py + 1, sz, sx, sy, sz, "minecraft:polished_andesite")
        B.box(sx, sy + 1, sz, sx, sy + 3, sz, "minecraft:smooth_stone")
        B.set(sx, sy + 4, sz, "minecraft:polished_andesite")
    B.box(cx, py + 1, cz, cx, py + 7, cz, AIR.accent)  # Aang's statue pedestal marker
    ctx.poi("avatar_statue_hall", cx, py + 1, cz, "Statues of past Avatars; Roku's statue")
    # --- ring of towers stepping down the mountain
    rng = ctx.rng
    n = 7
    for k in range(n):
        a = 2 * math.pi * k / n + 0.35
        rr = 24 + (k % 3) * 9
        tx, tz = int(cx + rr * math.cos(a)), int(cz + rr * math.sin(a))
        if (tx - cx) * fx + (tz - cz) * fz > rr * 0.85:
            continue  # keep the approach side open for the stairway
        g = ctx.ground_median(tx, tz, 3)
        base = int(min(max(g, py - 40), py + 2))
        r = [4.5, 5.5, 3.5][k % 3]
        h = int(min(rng.integers(20, 34), MAX_Y - base - 2 * r - 8))
        _foundation_column(ctx, tx, tz, base, r)
        kit.air_tower(B, tx, tz, base, r, h, AIR, roof_h=int(r * 2.4))
        # walkway from the plaza to the tower at its balcony / base
        wy = min(base + h - 1, py) if base < py else base
        kit.bridge(B, int(cx + 18 * math.cos(a)), int(cz + 18 * math.sin(a)), tx, tz, py, 3,
                   AIR.floor, "minecraft:birch_fence")
    # --- airball court beside the plaza
    ax_, az_ = int(cx - fx * 34 + fz * 6), int(cz - fz * 34 + fx * 6)
    ctx.level_pad(ax_, az_, 11, 18, py - 6, top="minecraft:smooth_stone", sub="minecraft:stone")
    for i, (ox, oz) in enumerate(((-6, -3), (-3, 2), (0, -2), (3, 3), (6, -1), (-1, 5), (2, -5))):
        B.box(ax_ + ox, py - 5, az_ + oz, ax_ + ox, py - 5 + 3 + i % 4, az_ + oz, "minecraft:spruce_fence")
        B.set(ax_ + ox, py - 5 + 4 + i % 4, az_ + oz, "minecraft:oak_planks")
    for gx in (-10, 10):  # goals: rings on posts
        B.box(ax_ + gx, py - 5, az_, ax_ + gx, py, az_, "minecraft:spruce_log[axis=y]")
        B.cyl(ax_ + gx, az_, py + 1, py + 1, 1.6, "minecraft:spruce_fence", hollow=True, thickness=1)
    ctx.poi("airball_court", ax_, py - 5, az_)
    # --- the long pilgrim stair down the approach side
    end = _stairway(ctx, cx + fx * 26, cz + fz * 26, py, front, 110)
    ctx.poi("mountain_stair_bottom", *end)
    ctx.poi("temple_plaza", cx, py + 1, cz, "Southern Air Temple; Gyatso memorial")
    ctx.claim(cx, cz, 70)
    ctx.notes.append(f"Plaza y={py}; sanctuary cone tip y={top}; {n} towers on the flanks.")


# ==========================================================================
def northern_air_temple(ctx: BuildContext) -> None:
    s = ctx.site
    peak = ctx.ground_max(s.x, s.z, 12)
    py = min(peak - 10, 258)
    cx, cz = s.x, s.z
    ctx.level_pad(cx, cz, 18, 60, py, top=AIR.floor, sub="minecraft:stone")
    ctx.integration.append(f"spire summit trimmed from y={peak} to y={py}; towers cling to the flanks")
    B = ctx.struct
    rng = ctx.rng
    # --- central tower (the Mechanist's workshop occupies its base)
    h = int(min(36, MAX_Y - py - 22))
    kit.air_tower(B, cx, cz, py + 1, 7, h, AIR, roof_h=16)
    # --- tiers of towers down the spire
    towers = []
    for k in range(9):
        a = 2 * math.pi * k / 9 + rng.uniform(-0.2, 0.2)
        rr = 18 + (k % 3) * 12
        tx, tz = int(cx + rr * math.cos(a)), int(cz + rr * math.sin(a))
        g = ctx.ground_median(tx, tz, 3)
        base = int(min(max(g + 2, py - 55), py + 4))
        r = [3.5, 4.5, 5.5][k % 3]
        th = int(min(rng.integers(14, 30), MAX_Y - base - int(r * 2.6) - 4))
        _foundation_column(ctx, tx, tz, base, r)
        kit.air_tower(B, tx, tz, base, r, th, AIR, roof_h=int(r * 2.5))
        towers.append((tx, tz, base, r, th))
    # --- Mechanist modifications: copper pipes, gears, workshop, war balloon
    for (tx, tz, base, r, th) in towers:
        # vertical steam pipe on the tower flank
        px = int(tx + (r + 1) * math.copysign(1, tx - cx))
        B.box(px, base, tz, px, base + th, tz, "minecraft:cut_copper")
        # pipe run back to the central tower
        B.line((px, base + th // 2, tz), (cx + int(math.copysign(8, px - cx)), py + 8, cz), "minecraft:cut_copper")
    for (tx, tz, base, r, th) in towers[::3]:
        gy = base + th // 2
        _gear(B, tx + int(r) + 2, gy, tz, 5)
    wx, wz = cx + 16, cz - 6
    B.box(wx - 8, py + 1, wz - 6, wx + 8, py + 9, wz + 6, "minecraft:iron_block")
    B.box(wx - 7, py + 1, wz - 5, wx + 7, py + 8, wz + 5, AIR_S)
    B.box(wx - 8, py + 10, wz - 6, wx + 8, py + 10, wz + 6, "minecraft:cut_copper_slab[type=bottom,waterlogged=false]")
    B.box(wx + 5, py + 10, wz + 3, wx + 6, py + 20, wz + 4, "minecraft:bricks")  # chimney
    B.box(wx - 1, py + 1, wz + 6, wx + 1, py + 4, wz + 6, AIR_S)
    for k in range(-6, 7, 3):
        B.box(wx + k, py + 5, wz - 6, wx + k, py + 6, wz - 6, "minecraft:glass_pane")
    ctx.poi("mechanist_workshop", wx, py + 1, wz, "The Mechanist's workshop (invention lab)")
    # war balloon prototype tethered over the plaza
    bx, bz = cx - 16, cz + 10
    B.ellipsoid(bx, py + 30, bz, 8, 10, 8, "minecraft:gray_wool", hollow=True)
    B.box(bx - 2, py + 16, bz - 2, bx + 2, py + 18, bz + 2, "minecraft:spruce_planks")
    B.box(bx - 1, py + 17, bz - 1, bx + 1, py + 18, bz + 1, AIR_S)
    for (ox, oz) in ((-2, -2), (2, -2), (-2, 2), (2, 2)):
        B.line((bx + ox, py + 19, bz + oz), (bx + ox * 3, py + 23, bz + oz * 3), "minecraft:chain[axis=y,waterlogged=false]")
    B.box(bx, py + 1, bz, bx, py + 15, bz, "minecraft:chain[axis=y,waterlogged=false]")
    B.ellipsoid(bx, py + 30, bz, 2, 2, 2, "minecraft:red_wool")  # Fire Nation insignia patch
    ctx.poi("war_balloon_prototype", bx, py + 16, bz)
    # natural-gas cavern beneath the temple (sealed by Aang)
    gy = py - 45
    B.ellipsoid(cx, gy, cz, 18, 7, 14, AIR_S)
    B.box(cx - 1, gy, cz, cx + 1, py, cz + 1, AIR_S)
    B.box(cx - 1, gy, cz, cx - 1, py, cz, "minecraft:ladder[facing=east,waterlogged=false]")
    ctx.poi("gas_cavern", cx, gy, cz, "Natural-gas cave under the temple")
    end = _stairway(ctx, cx, cz + 20, py, "south", 80)
    ctx.poi("temple_plaza", cx, py + 1, cz)
    ctx.poi("approach_stair_bottom", *end)
    ctx.claim(cx, cz, 70)


def _gear(B, x, y, z, r: int) -> None:
    B.cyl(x, z, y, y, 0.4, "minecraft:iron_block")
    for dy in range(-r, r + 1):
        for dz in range(-r, r + 1):
            d = math.hypot(dy, dz)
            if r - 1.2 <= d <= r + 0.3 or d < 1.5 or (abs(dy) == 0 or abs(dz) == 0) and d < r:
                B.set(x, y + dy, z + dz, "minecraft:iron_block")
    for k in range(8):
        a = k * math.pi / 4
        B.set(x, y + int(round((r + 1) * math.sin(a))), z + int(round((r + 1) * math.cos(a))),
              "minecraft:cut_copper")


# ==========================================================================
def eastern_air_temple(ctx: BuildContext) -> None:
    s = ctx.site
    peak = ctx.ground_max(s.x, s.z, 10)
    py = min(peak - 6, 250)
    cx, cz = s.x, s.z
    ctx.level_pad(cx, cz, 20, 48, py, top=AIR.floor, sub="minecraft:stone")
    B = ctx.struct
    rng = ctx.rng
    # --- main temple: tall round hall with two flanking spires
    B.cyl(cx, cz, py + 1, py + 18, 10, AIR.wall, hollow=True, thickness=1.5)
    B.cyl(cx, cz, py + 1, py + 18, 8.5, AIR_S)
    kit.cone_roof(B, cx, cz, py + 19, 12, AIR.roof_stairs, AIR.roof, height=24, tip=AIR.accent)
    for sx in (-15, 15):
        kit.air_tower(B, cx + sx, cz, py + 1, 3.5, 26, AIR, roof_h=12)
    # --- five natural rock spires ringed around the summit, each crowned
    spires = []
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.6
        rr = 52 + rng.uniform(-6, 6)
        tx, tz = int(cx + rr * math.cos(a)), int(cz + rr * math.sin(a))
        g = ctx.ground_median(tx, tz, 4)
        top = int(min(py - 6 + rng.integers(-10, 12), MAX_Y - 40))
        r0 = 9 + rng.uniform(-1, 2)
        for y in range(g - 4, top + 1):  # tapered, slightly noisy stone column
            t = (y - g) / max(top - g, 1)
            rr_ = r0 * (1 - 0.45 * t) + rng.uniform(-0.4, 0.4)
            B.cyl(tx, tz, y, y, rr_, "minecraft:stone" if y % 7 else "minecraft:andesite")
        B.cyl(tx, tz, top, top, r0 * 0.55 + 1, "minecraft:grass_block[snowy=false]")
        kit.air_tower(B, tx, tz, top + 1, 4, int(rng.integers(12, 20)), AIR, roof_h=10)
        spires.append((tx, tz, top))
    # rope bridges from the summit to every spire
    for (tx, tz, top) in spires:
        a = math.atan2(tz - cz, tx - cx)
        sx, sz = int(cx + 20 * math.cos(a)), int(cz + 20 * math.sin(a))
        kit.bridge(B, sx, sz, tx, tz, min(py, top + 1), 3, "minecraft:spruce_planks",
                   "minecraft:spruce_fence", arch=-3)
    # Guru Pathik's meditation ledge on the cliff edge
    a = rng.uniform(0, 2 * math.pi)
    lx, lz = int(cx + 30 * math.cos(a)), int(cz + 30 * math.sin(a))
    B.cyl(lx, lz, py - 1, py - 1, 3.5, "minecraft:smooth_stone")
    B.cyl(lx, lz, py - 4, py - 2, 2.5, "minecraft:stone", mode=SOFT)
    B.set(lx, py, lz, "minecraft:orange_carpet")
    ctx.poi("guru_pathik_ledge", lx, py, lz, "Chakra lessons (2x19 The Guru)")
    ctx.poi("temple_plaza", cx, py + 1, cz)
    end = _stairway(ctx, cx, cz, py, _approach_facing(ctx, cx, cz), 90)
    ctx.poi("approach_stair_bottom", *end)
    ctx.claim(cx, cz, 75)


# ==========================================================================
def western_air_temple(ctx: BuildContext) -> None:
    """Carve a gorge into the ridge and hang the temple upside-down from its rims."""
    s = ctx.site
    length, half_w = 280, 22
    # choose the gorge axis (through a point near the site) whose rims stay
    # highest along the whole length: the gorge must be walled on both sides
    best = None
    for ox in range(-200, 201, 25):
        for oz in range(-200, 201, 25):
            px, pz = s.x + ox, s.z + oz
            if ctx.is_water(px, pz):
                continue
            for ang in range(0, 180, 15):
                a = math.radians(ang)
                ux, uz = math.cos(a), math.sin(a)
                ts = np.linspace(-length / 2, length / 2, 15)
                rims = []
                for t in ts:
                    for side in (-1, 1):
                        rx = px + ux * t - uz * side * (half_w + 14)
                        rz = pz + uz * t + ux * side * (half_w + 14)
                        w = ctx.is_water(rx, rz)
                        rims.append(-999 if w else ctx.ground(rx, rz))
                score = float(np.percentile(rims, 15))
                if best is None or score > best[0]:
                    best = (score, px, pz, ux, uz)
    rim_est, cx, cz, ux, uz = best
    rim_y = int(rim_est)
    floor_y = max(ctx.sea + 8, rim_y - 95)
    R = int(length / 2 + half_w + 40)
    x0, z0 = cx - R, cz - R
    n = 2 * R + 1
    g = ctx.field(x0, z0, n, n)
    dx = np.arange(n)[:, None] - R
    dz = np.arange(n)[None, :] - R
    along = dx * ux + dz * uz
    across = -dx * uz + dz * ux
    # rounded gorge ends; walls vertical with a slight widening near the rim
    endcap = np.maximum(np.abs(along) - length / 2, 0)
    dist = np.hypot(endcap, np.maximum(np.abs(across) - 0, 0))
    inside = (np.abs(along) <= length / 2 + half_w) & (np.hypot(endcap, across) <= half_w)
    new_h = np.where(inside, np.minimum(g, floor_y + (np.abs(across) > half_w - 4) * 3), g)
    ctx.shape_terrain(x0, z0, new_h.astype(np.int32), inside, top="minecraft:gravel", sub="minecraft:stone")
    ctx.integration.append(f"gorge {length}x{2 * half_w} carved along the ridge, floor y={floor_y}, rim y~{rim_y}")
    B = ctx.struct
    P = lambda t, c: (int(round(cx + ux * t - uz * c)), int(round(cz + uz * t + ux * c)))  # noqa: E731
    # stream along the floor and the waterfall pouring from the rim at one end
    for t in range(int(-length / 2), int(length / 2) + 1):
        x, z = P(t, 0)
        B.box(x - 1, floor_y, z - 1, x + 1, floor_y, z + 1, "minecraft:water[level=0]")
    wx, wz = P(-length / 2 - half_w + 2, 0)
    B.box(wx - 2, floor_y + 1, wz - 2, wx + 2, rim_y, wz + 2, "minecraft:water[level=0]")
    ctx.poi("waterfall", wx, rim_y, wz)
    rng = ctx.rng
    hang_y = rim_y - 5  # attachment level under the rim
    modules = 0
    for k in range(int(-length / 2) + 25, int(length / 2) - 20, 30):
        for side in (-1, 1):
            if rng.random() < 0.15:
                continue
            r = float(rng.choice([4.5, 5.5, 6.5]))
            h = int(rng.integers(14, 26))
            size = int(2 * (r + 3)) + 3
            cv = Canvas(ctx.reg, (size, h + int(r * 2.5) + 6, size))
            kit.air_tower(cv, size // 2, size // 2, 0, r, h, AIR, roof_h=int(r * 2.5))
            inv = cv.flipped_y()
            X, Y, Z = inv.ids.shape
            tx, tz = P(k, side * (half_w - r + 1))
            inv.paste(B, tx - X // 2, hang_y - Y + 1, tz - Z // 2)
            ax_, az_ = P(k, side * (half_w + 4))
            B.line((tx, hang_y, tz), (ax_, hang_y, az_), "minecraft:stone_bricks", width=3)
            modules += 1
    # ledge walkways along both walls, bridges across
    for side in (-1, 1):
        for t in range(int(-length / 2) + 15, int(length / 2) - 14):
            x, z = P(t, side * (half_w - 2))
            B.box(x - 1, hang_y - 1, z - 1, x + 1, hang_y - 1, z + 1, AIR.floor)
            B.box(x - 1, hang_y, z - 1, x + 1, hang_y + 3, z + 1, AIR_S)
    for k in range(int(-length / 2) + 40, int(length / 2) - 30, 70):
        a0, a1 = P(k, -half_w + 2), P(k, half_w - 2)
        kit.bridge(B, a0[0], a0[1], a1[0], a1[1], hang_y - 1, 3, "minecraft:spruce_planks",
                   "minecraft:birch_fence", arch=-2)
    # the fountain courtyard (Pai Sho fountain) cantilevered from one wall
    fxc, fzc = P(0, -half_w + 10)
    fy = hang_y - 24
    B.cyl(fxc, fzc, fy - 3, fy, 11, AIR.floor)
    B.cone(fxc, fzc, fy - 18, 15, 1, 10, "minecraft:stone_bricks")
    B.cyl(fxc, fzc, fy + 1, fy + 1, 5, "minecraft:smooth_sandstone", hollow=True, thickness=1)
    B.cyl(fxc, fzc, fy + 1, fy + 1, 4, "minecraft:water[level=0]")
    B.box(fxc, fy + 1, fzc, fxc, fy + 4, fzc, "minecraft:smooth_quartz")
    for (ox, oz) in ((0, 2), (0, -2), (2, 0), (-2, 0)):
        B.set(fxc + ox, fy + 1, fzc + oz, "minecraft:white_terracotta")
    wx2, wz2 = P(0, -half_w - 3)
    B.line((fxc, fy + 1, fzc), (wx2, fy + 1, wz2), AIR_S, width=5)
    B.line((fxc, fy, fzc), (wx2, fy, wz2), AIR.floor, width=5)
    ctx.poi("fountain_courtyard", fxc, fy + 1, fzc, "Pai Sho table fountain")
    ex, ez = P(length / 2 - 10, half_w + 5)
    ctx.poi("rim_entrance", ex, rim_y + 1, ez, "Temple is invisible from the plateau above")
    ctx.poi("gorge_floor", cx, floor_y + 1, cz)
    ctx.site.notes["gorge_axis_deg"] = round(math.degrees(math.atan2(uz, ux)), 1)
    ctx.claim(cx, cz, length / 2 + 30)
    ctx.notes.append(f"{modules} inverted towers hang from both rims at y~{hang_y}; gorge floor y={floor_y}.")
