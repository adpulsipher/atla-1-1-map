"""Earth Kingdom landmarks (Ba Sing Se lives in basingse.py)."""
from __future__ import annotations

import math

import numpy as np

from ..buffer import SET, SOFT, Canvas
from ..noise import hash01
from ..palettes import EARTH, EARTH_POOR, EARTH_RURAL, Palette
from ..terrain import NONE
from . import kit
from .common import BuildContext, facing_from_vector, unit, water_direction
from .village import find_flat, paint_path, place_houses

AIR_S = "minecraft:air"
WATER_S = "minecraft:water[level=0]"

KYOSHI = Palette(
    name="kyoshi", wall="minecraft:birch_planks", wall_alt="minecraft:stripped_birch_log[axis=y]",
    trim="minecraft:dark_oak_log[axis=y]", post="minecraft:dark_oak_log[axis=y]",
    floor="minecraft:spruce_planks", foundation="minecraft:cobblestone",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:prismarine_bricks",
    window="minecraft:spruce_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:dark_oak_planks", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:dark_oak_fence",
)
DESERT = Palette(
    name="desert", wall="minecraft:smooth_sandstone", wall_alt="minecraft:cut_sandstone",
    trim="minecraft:stripped_acacia_log[axis=y]", post="minecraft:stripped_acacia_log[axis=y]",
    floor="minecraft:sandstone", foundation="minecraft:sandstone",
    roof="minecraft:smooth_sandstone", roof_stairs="minecraft:smooth_sandstone_stairs",
    roof_slab="minecraft:smooth_sandstone_slab", ridge="minecraft:cut_sandstone",
    window="minecraft:air", door_frame="minecraft:cut_sandstone", accent="minecraft:orange_wool",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:acacia_fence",
)


def _dir(ctx, site, default=(0, 1)):
    a = site.angle
    return math.cos(a), math.sin(a)


# ==========================================================================
# Foggy Swamp: the banyan-grove tree whose roots span the whole swamp
# ==========================================================================
def foggy_swamp(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    y0 = ctx.sea - 5
    top = ctx.sea + 58
    wood = "minecraft:mangrove_wood[axis=y]"
    logy = "minecraft:mangrove_log[axis=y]"
    lf = kit.leaves("mangrove")
    lf2 = kit.leaves("jungle")
    # fused trunk mass: a central bole plus a ring of merged trunks, flared roots
    B.cyl(cx, cz, y0, top, 7, logy)
    for k in range(7):
        a = 2 * math.pi * k / 7 + rng.uniform(-0.2, 0.2)
        tx, tz = int(cx + 7 * math.cos(a)), int(cz + 7 * math.sin(a))
        B.cyl(tx, tz, y0, top - int(rng.integers(8, 20)), 3.5, wood)
        B.cone(tx, tz, y0, 12, 7, 3.5, "minecraft:mangrove_roots")
    B.cone(cx, cz, y0, 16, 17, 8, "minecraft:muddy_mangrove_roots")
    # hollow heart where Aang's visions happen
    B.ellipsoid(cx, ctx.sea + 5, cz, 4, 4, 4, AIR_S)
    B.box(cx, ctx.sea + 2, cz + 4, cx + 1, ctx.sea + 5, cz + 12, AIR_S)
    B.set(cx, ctx.sea + 2, cz, "minecraft:shroomlight")
    ctx.poi("banyan_tree_heart", cx, ctx.sea + 2, cz, "Heart of the swamp: visions (2x04 The Swamp)")
    # great branches with drooping aerial prop roots and leaf clouds
    for k in range(11):
        a = 2 * math.pi * k / 11 + rng.uniform(-0.15, 0.15)
        by = ctx.sea + int(rng.integers(26, 48))
        ln = rng.uniform(38, 62)
        ex, ez = cx + ln * math.cos(a), cz + ln * math.sin(a)
        ey = by + int(rng.integers(-4, 8))
        B.line((cx, by, cz), (int(ex), ey, int(ez)), wood, width=3)
        for t in np.linspace(0.3, 1.0, 5):  # aerial roots
            rx = int(cx + (ex - cx) * t + rng.integers(-2, 3))
            rz = int(cz + (ez - cz) * t + rng.integers(-2, 3))
            ry = int(by + (ey - by) * t)
            B.box(rx, ctx.sea - 3, rz, rx, ry, rz, logy)
            B.cone(rx, rz, ctx.sea - 3, 5, 2.5, 0.5, "minecraft:mangrove_roots", mode=SOFT)
        B.ellipsoid(int(ex), ey + 4, int(ez), rng.uniform(11, 16), 6, rng.uniform(11, 16),
                    lf if k % 2 else lf2, mode=SOFT)
        for v in range(12):  # hanging vines
            vx, vz = int(ex + rng.integers(-10, 11)), int(ez + rng.integers(-10, 11))
            B.box(vx, ey - int(rng.integers(3, 12)), vz, vx, ey - 1, vz, "minecraft:vine[east=false,north=true,south=false,up=false,west=false]", mode=SOFT)
    B.ellipsoid(cx, top + 2, cz, 34, 12, 34, lf, mode=SOFT)
    # surface roots radiating through the swamp (the swamp is one organism)
    for k in range(18):
        a = 2 * math.pi * k / 18 + rng.uniform(-0.1, 0.1)
        px, pz = cx + 14 * math.cos(a), cz + 14 * math.sin(a)
        ln = rng.uniform(80, 170)
        segs = 8
        for i in range(segs):
            a += rng.uniform(-0.35, 0.35)
            nx, nz = px + ln / segs * math.cos(a), pz + ln / segs * math.sin(a)
            B.line((int(px), ctx.sea - 1, int(pz)), (int(nx), ctx.sea - 1 + int(rng.integers(0, 2)), int(nz)),
                   "minecraft:mangrove_log[axis=x]", width=2)
            px, pz = nx, nz
    # lily pads, small mangroves, swamp-tribe stilt huts
    for k in range(260):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(15, 190)
        x, z = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        if ctx.is_water(x, z):
            B.set(x, ctx.sea + 1, z, "minecraft:lily_pad", mode=SOFT)
    for k in range(45):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(45, 200)
        x, z = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        g = ctx.ground(x, z)
        kit.tree(B, x, max(g + 1, ctx.sea - 2), z, "mangrove", int(rng.integers(7, 12)), rng=rng)
    huts = 0
    for k in range(40):
        if huts >= 6:
            break
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(55, 120)
        x, z = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        cv = kit.house_canvas(ctx.reg, 7, 7, EARTH_RURAL, stories=1, roof="thatch", stilts=5)
        ctx.place(cv, x, z, ctx.sea - 3, facing_from_vector(cx - x, cz - z), anchor=(cv.size[0] // 2, 0, cv.size[2] // 2))
        huts += 1
        if huts == 1:
            ctx.poi("swamp_tribe_camp", x, ctx.sea + 3, z, "Huu, Due and Tho")
    ctx.claim(cx, cz, 200)
    ctx.notes.append("Giant banyan (canopy ~70 wide) with aerial roots; 18 surface roots across the painted swamp.")


# ==========================================================================
# Kyoshi Island village with the Avatar Kyoshi statue
# ==========================================================================
def kyoshi_island(ctx: BuildContext) -> None:
    s = ctx.site
    spot = find_flat(ctx, s.x, s.z, 180, 28, ctx.sea + 2, ctx.sea + 24, water_within=90)
    if spot is None:
        spot = (s.x, s.z, ctx.ground_median(s.x, s.z, 10))
    cx, cz, y = spot
    ctx.level_pad(cx, cz, 16, 30, y, top="minecraft:gravel")
    B = ctx.struct
    B.cyl(cx, cz, y, y, 15, "minecraft:stone_bricks")
    B.cyl(cx, cz, y, y, 12, "minecraft:polished_andesite", hollow=True, thickness=1)
    wx, wz = water_direction(ctx, cx, cz, 120)
    sea_face = facing_from_vector(wx, wz)
    # Avatar Kyoshi statue facing the harbour
    cv = Canvas(ctx.reg, (23, 32, 19))
    kit.blocky_statue(cv, 11, 0, 9, 1, dict(robe="minecraft:green_concrete", robe_trim="minecraft:lime_terracotta",
                                            skin="minecraft:white_concrete", hair="minecraft:black_wool",
                                            belt="minecraft:yellow_terracotta", accent="minecraft:gold_block",
                                            eyes="minecraft:red_concrete", base="minecraft:polished_andesite"))
    ctx.place(cv, cx, cz, y + 1, sea_face, anchor=(11, 0, 9))
    ctx.poi("kyoshi_statue", cx, y + 1, cz, "Avatar Kyoshi statue (village square)")
    houses = place_houses(ctx, cx, cz, 22, 85, 18, [KYOSHI], stories=(1, 1, 2), avoid=[(cx, cz, 18)],
                          max_slope=9, tries=1500)
    for (hx, hz, *_r) in houses:
        paint_path(ctx, cx, cz, hx, hz, 2)
    # Kyoshi Warriors' dojo on the landward side
    dx, dz = int(cx - wx * 40), int(cz - wz * 40)
    gy = ctx.ground_median(dx, dz, 12)
    ctx.level_pad(dx, dz, 14, 20, gy)
    cvd = kit.house_canvas(ctx.reg, 19, 13, KYOSHI, stories=2, story_h=5)
    ctx.place(cvd, dx, dz, gy, facing_from_vector(cx - dx, cz - dz), foundation=KYOSHI.foundation)
    paint_path(ctx, cx, cz, dx, dz, 3)
    ctx.poi("kyoshi_warriors_dojo", dx, gy + 1, dz, "Suki & the Kyoshi Warriors")
    # harbour pier toward the sea
    px, pz = int(cx + wx * 30), int(cz + wz * 30)
    for k in range(0, 120):
        x, z = int(cx + wx * (20 + k)), int(cz + wz * (20 + k))
        if ctx.is_water(x, z):
            for j in range(40):
                qx, qz = int(x + wx * j), int(z + wz * j)
                B.box(qx - 1, ctx.sea + 1, qz - 1, qx + 1, ctx.sea + 1, qz + 1, "minecraft:spruce_planks")
                if j % 4 == 0:
                    B.box(qx, ctx.sea - 6, qz, qx, ctx.sea, qz, "minecraft:spruce_log[axis=y]")
            ctx.poi("harbour_pier", int(x + wx * 39), ctx.sea + 2, int(z + wz * 39), "Unagi waters beyond")
            break
    ctx.claim(cx, cz, 90)


# ==========================================================================
# Omashu: tiered mountain city, chasm & bridge, palace, mail chutes
# ==========================================================================
OMASHU = Palette(
    name="omashu", wall="minecraft:smooth_sandstone", wall_alt="minecraft:cut_sandstone",
    trim="minecraft:stripped_spruce_log[axis=y]", post="minecraft:stripped_spruce_log[axis=y]",
    floor="minecraft:spruce_planks", foundation="minecraft:stone_bricks",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:prismarine_bricks",
    window="minecraft:spruce_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:spruce_planks", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:spruce_fence",
)


def omashu(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    R = int(min(110, max(70, s.fit_radius * 0.45)))
    cx, cz = s.x, s.z
    ring_g = ctx.field(cx - R - 60, cz - R - 60, 2 * R + 121, 2 * R + 121)
    base = int(np.percentile(ring_g, 40))
    T = [base + 8, base + 26, base + 44, base + 62]
    radii = [R, R - 30, R - 58, R - 82]
    # approach from the gentlest side
    front = "south"
    best = None
    for f in ("north", "south", "east", "west"):
        ux, uz = unit(f)
        g = ctx.ground_median(cx + ux * (R + 60), cz + uz * (R + 60), 10)
        if best is None or abs(g - base) < best:
            best, front = abs(g - base), f
    fx, fz = unit(front)
    n = 2 * (R + 70) + 1
    x0, z0 = cx - (R + 70), cz - (R + 70)
    dx = np.arange(n)[:, None] - (R + 70)
    dz = np.arange(n)[None, :] - (R + 70)
    d = np.hypot(dx, dz)
    nat = ctx.field(x0, z0, n, n).astype(np.float32)
    new_h = nat.copy()
    for k in range(4):
        new_h = np.where(d <= radii[k], T[k], new_h)
    along = dx * fx + dz * fz
    across = np.abs(-dx * fz + dz * fx)
    bridge = (along > 0) & (across <= 5)
    chasm = (d > R + 3) & (d < R + 24) & ~bridge
    new_h = np.where(chasm, base - 30, new_h)
    blend = (d >= R + 24) & (d < R + 60)
    t = np.clip((d - (R + 24)) / 36.0, 0, 1)
    new_h = np.where(blend, base * (1 - t) + nat * t, new_h)
    new_h = np.where(bridge & (d > R) & (d < R + 24), T[0], new_h)  # causeway plinth under bridge deck
    mask = d < R + 60
    ctx.shape_terrain(x0, z0, np.rint(new_h).astype(np.int32), mask, top="minecraft:stone_bricks",
                      sub="minecraft:stone")
    ctx.integration.append(f"peak reshaped into a 4-tier mesa (y {T[0]}..{T[3]}) ringed by a 21-wide chasm")
    # cliff faces between tiers: dress them in tan stone
    for k in range(1, 4):
        B.cyl(cx, cz, T[k - 1] + 1, T[k], radii[k] + 0.5, "minecraft:sandstone", hollow=True, thickness=2)
    # outer city wall with gate facing the bridge
    B.cyl(cx, cz, T[0] + 1, T[0] + 14, R + 0.5, "minecraft:stone_bricks", hollow=True, thickness=3)
    B.cyl(cx, cz, T[0] + 15, T[0] + 15, R + 0.5, "minecraft:stone_brick_wall", hollow=True, thickness=1)
    gx, gz = cx + fx * R, cz + fz * R
    if fx:
        B.box(gx - 3, T[0] + 1, gz - 5, gx + 3, T[0] + 12, gz + 5, AIR_S)
        B.box(gx + fx * 3, T[0] + 13, gz - 7, gx + fx * 3, T[0] + 18, gz + 7, "minecraft:chiseled_stone_bricks")
        B.box(gx + fx * 3, T[0] + 19, gz - 8, gx + fx * 3, T[0] + 19, gz + 8, EARTH.roof)
    else:
        B.box(gx - 5, T[0] + 1, gz - 3, gx + 5, T[0] + 12, gz + 3, AIR_S)
        B.box(gx - 7, T[0] + 13, gz + fz * 3, gx + 7, T[0] + 18, gz + fz * 3, "minecraft:chiseled_stone_bricks")
        B.box(gx - 8, T[0] + 19, gz + fz * 3, gx + 8, T[0] + 19, gz + fz * 3, EARTH.roof)
    ctx.poi("city_gate", gx, T[0] + 1, gz, "Omashu gate (bridge over the chasm)")
    # the bridge across the chasm
    kit.bridge(B, cx + fx * (R + 1), cz + fz * (R + 1), cx + fx * (R + 34), cz + fz * (R + 34), T[0], 9,
               "minecraft:stone_bricks", "minecraft:stone_brick_wall")
    # ramps linking the tiers (switchback ramps against each cliff)
    for k in range(1, 4):
        for side in (1, -1):
            a = math.atan2(fz, fx) + side * (0.5 + 0.3 * k)
            rr = radii[k] + 3
            for i in range(T[k] - T[k - 1] + 1):
                aa = a + side * i / rr
                x = int(round(cx + rr * math.cos(aa)))
                z = int(round(cz + rr * math.sin(aa)))
                B.box(x - 1, T[k - 1], z - 1, x + 1, T[k - 1] + i, z + 1, "minecraft:stone_bricks")
                B.box(x - 1, T[k - 1] + i + 1, z - 1, x + 1, T[k - 1] + i + 4, z + 1, AIR_S)
    # houses on each tier
    avoid = [(cx + fx * R, cz + fz * R, 18)]
    for k in range(3):
        rin, rout = radii[k + 1] + 6, radii[k] - 8
        count = int(math.pi * (rout ** 2 - rin ** 2) / 170)
        hs = place_houses(ctx, cx, cz, rin, rout, count, [OMASHU], sizes=((7, 6), (8, 7), (10, 8)),
                          stories=(1, 2, 2), avoid=avoid, max_slope=3, face_center=False, mode_pad=False,
                          y_clamp=(T[k], T[k]), tries=6000)
        avoid += [(x, z, r) for x, z, r, *_ in hs]
    # King Bumi's palace on the summit tier
    pv = kit.house_canvas(ctx.reg, 27, 21, OMASHU, stories=3, story_h=5)
    ctx.place(pv, cx, cz, T[3], front, foundation="minecraft:stone_bricks")
    kit.pagoda(B, cx, cz, T[3] + 22, 9, 2, OMASHU, spire="minecraft:gold_block")
    ctx.poi("king_bumi_palace", cx, T[3] + 1, cz, "Throne room; Bumi's riddles")
    # mail delivery chutes: stone channels spiralling down to the outer ring
    for k in range(3):
        a = math.atan2(fz, fx) + math.pi + (k - 1) * 0.9
        x_prev = None
        steps = 170
        for i in range(steps):
            t = i / (steps - 1)
            rr = (radii[3] - 2) + (R - 12 - (radii[3] - 2)) * t
            aa = a + t * 2.2
            y = int(round(T[3] + 6 - (T[3] + 6 - (T[0] + 3)) * t))
            x = int(round(cx + rr * math.cos(aa)))
            z = int(round(cz + rr * math.sin(aa)))
            B.box(x - 1, y - 1, z - 1, x + 1, y - 1, z + 1, "minecraft:smooth_stone")
            B.box(x - 1, y, z - 1, x + 1, y + 2, z + 1, AIR_S)
            if i % 3 == 0:
                B.cyl(x, z, y - 1, y, 2.2, "minecraft:stone_brick_wall", hollow=True, thickness=0.8, mode=SOFT)
            if i % 9 == 0:
                B.box(x, T[0], z, x, y - 2, z, "minecraft:stone_bricks", mode=SOFT)
        ctx.poi(f"mail_chute_{k + 1}_top", int(cx + (radii[3] - 2) * math.cos(a)), T[3] + 6,
                int(cz + (radii[3] - 2) * math.sin(a)), "Mail delivery chute (ride it!)")
    ctx.poi("outer_ring", cx + fx * (R - 10), T[0] + 1, cz + fz * (R - 10))
    ctx.claim(cx, cz, R + 60)
    ctx.notes.append(f"City radius {R}, tiers {T}; gate/bridge face {front}.")


# ==========================================================================
# Senlin Village and the burnt Spirit Forest with Hei Bai's statue
# ==========================================================================
def senlin_village(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    y = ctx.ground_median(cx, cz, 10)
    ctx.level_pad(cx, cz, 10, 18, y, top="minecraft:dirt_path")
    kit.pagoda(B, cx, cz, y + 1, 7, 2, EARTH)  # village shrine
    ctx.poi("village_square", cx, y + 1, cz)
    hs = place_houses(ctx, cx, cz, 16, 55, 12, [EARTH_RURAL, EARTH_POOR], roof="thatch", avoid=[(cx, cz, 12)],
                      max_slope=8, tries=1500)
    for (hx, hz, *_r) in hs:
        paint_path(ctx, cx, cz, hx, hz, 2)
    # burnt Spirit Forest beside the village
    best = None
    for f in ("north", "south", "east", "west"):
        ux, uz = unit(f)
        if ctx.water_frac(cx + ux * 85, cz + uz * 85, 30) < 0.05:
            g = abs(ctx.ground_median(cx + ux * 85, cz + uz * 85, 20) - y)
            if best is None or g < best[0]:
                best = (g, ux, uz)
    _, ux, uz = best or (0, 1, 0)
    fx, fz = int(cx + ux * 90), int(cz + uz * 90)
    ctx.clear_vegetation(fx, fz, 48)
    R = 48
    n = 2 * R + 1
    g = ctx.field(fx - R, fz - R, n, n)
    h = hash01(np.arange(n)[:, None] + fx, np.arange(n)[None, :] + fz, 7)
    d = np.hypot(np.arange(n)[:, None] - R, np.arange(n)[None, :] - R)
    m = d <= R
    ash = np.where(h < 0.45, ctx.reg.id("minecraft:coarse_dirt"),
                   np.where(h < 0.7, ctx.reg.id("minecraft:podzol"),
                            np.where(h < 0.85, ctx.reg.id("minecraft:gravel"), ctx.reg.id("minecraft:black_concrete_powder"))))
    ctx.terrain.fill_columns(fx - R, fz - R, np.where(m, g, 0), np.where(m, g + 1, 0), ash.astype(np.uint16))
    for k in range(70):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(8, R)
        tx, tz = int(fx + r * math.cos(a)), int(fz + r * math.sin(a))
        kit.tree(B, tx, ctx.ground(tx, tz) + 1, tz, "burnt", int(rng.integers(5, 13)), rng=rng, mode=SET)
    # Hei Bai statue: black & white panda spirit on a plinth in a small shrine
    gy = ctx.ground(fx, fz)
    B.box(fx - 5, gy, fz - 5, fx + 5, gy, fz + 5, "minecraft:stone_bricks")
    B.box(fx - 2, gy + 1, fz - 2, fx + 2, gy + 2, fz + 2, "minecraft:polished_andesite")
    W_, K_ = "minecraft:white_concrete", "minecraft:black_concrete"
    B.box(fx - 2, gy + 3, fz - 2, fx + 2, gy + 7, fz + 2, W_)  # body
    B.box(fx - 2, gy + 3, fz - 2, fx + 2, gy + 4, fz + 2, K_)  # legs
    B.box(fx - 3, gy + 5, fz - 1, fx + 3, gy + 6, fz + 1, K_)  # arms/shoulders
    B.box(fx - 2, gy + 8, fz - 2, fx + 2, gy + 11, fz + 2, W_)  # head
    B.set(fx - 2, gy + 12, fz - 1, K_)
    B.set(fx + 2, gy + 12, fz - 1, K_)  # ears
    B.set(fx - 1, gy + 10, fz + 2, K_)
    B.set(fx + 1, gy + 10, fz + 2, K_)  # eye patches
    for (ox, oz) in ((-5, -5), (5, -5), (-5, 5), (5, 5)):
        B.box(fx + ox, gy + 1, fz + oz, fx + ox, gy + 9, fz + oz, "minecraft:dark_oak_log[axis=y]")
    kit.hip_roof(B, fx - 5, fz - 5, fx + 5, fz + 5, gy + 10, "minecraft:dark_prismarine_stairs",
                 "minecraft:dark_prismarine", overhang=1)
    B.box(fx - 4, gy + 1, fz - 4, fx + 4, gy + 9, fz + 4, AIR_S, mode=SOFT)
    B.set(fx + 3, gy + 1, fz + 6, "minecraft:oak_sapling[stage=0]")
    ctx.poi("hei_bai_statue", fx, gy + 1, fz, "Hei Bai, the forest spirit (panda form)")
    ctx.poi("acorn_sapling", fx + 3, gy + 1, fz + 6, "Aang's acorn: the forest will regrow")
    ctx.claim(cx, cz, 60)
    ctx.claim(fx, fz, R)


# ==========================================================================
# The Great Divide: a terraced red-rock canyon
# ==========================================================================
STRATA = ["minecraft:orange_terracotta", "minecraft:terracotta", "minecraft:red_terracotta",
          "minecraft:yellow_terracotta", "minecraft:white_terracotta", "minecraft:orange_terracotta",
          "minecraft:brown_terracotta", "minecraft:light_gray_terracotta", "minecraft:red_terracotta"]


def great_divide(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    cx, cz = s.x, s.z
    a = s.angle
    ux, uz = math.cos(a), math.sin(a)
    length, half_top, half_floor = 640, 64, 14
    R = int(length / 2 + half_top + 20)
    x0, z0 = cx - R, cz - R
    n = 2 * R + 1
    g = ctx.field(x0, z0, n, n).astype(np.float32)
    dx = np.arange(n)[:, None] - R
    dz = np.arange(n)[None, :] - R
    along = dx * ux + dz * uz
    across = np.abs(-dx * uz + dz * ux)
    end = np.maximum(np.abs(along) - length / 2, 0)
    # canyon narrows toward the ends
    taper = np.clip(1 - end / 60.0, 0, 1)
    width = half_top * taper
    inside = across < width
    rim = float(np.percentile(g[(across > half_top) & (across < half_top + 20) & (np.abs(along) < length / 2)], 50))
    floor = int(max(ctx.sea + 4, rim - 85))
    frac = np.clip((across - half_floor) / max(half_top - half_floor, 1), 0, 1)
    prof = floor + (rim - floor) * (np.floor(frac * 7) / 7) ** 1.3  # stepped terraces
    prof = np.where(across <= half_floor, floor, prof)
    new_h = np.where(inside, np.minimum(g, prof + end * 1.2), g)
    ctx.shape_terrain(x0, z0, np.rint(new_h).astype(np.int32), inside, top="minecraft:red_sand",
                      sub="minecraft:orange_terracotta")
    # re-skin the exposed walls with horizontal strata (bands by altitude)
    nh = np.rint(new_h).astype(np.int32)
    for band in range(floor - 10, int(rim) + 12, 4):
        mat = STRATA[(band // 4) % len(STRATA)]
        lo = np.where(inside, np.maximum(nh - 22, band), 0)
        hi = np.where(inside, np.minimum(nh, band + 4), 0)
        ctx.terrain.fill_columns(x0, z0, lo, hi, mat)
    ctx.integration.append(f"canyon {length} long, {2 * half_top} wide, floor y={floor} (rim ~{int(rim)}); terracotta strata")
    # scattered boulders on the canyon floor
    rng = ctx.rng
    for k in range(40):
        t = rng.uniform(-length / 2, length / 2)
        c = rng.uniform(-half_floor, half_floor)
        bx, bz = int(cx + ux * t - uz * c), int(cz + uz * t + ux * c)
        B.ellipsoid(bx, floor + 1, bz, rng.uniform(1.5, 3.5), rng.uniform(1.5, 3), rng.uniform(1.5, 3.5),
                    "minecraft:terracotta", mode=SOFT)
    # ranger station at the rim and the switchback guide trail down the wall
    rx, rz = int(cx - uz * (half_top + 14) + ux * (-length / 3)), int(cz + ux * (half_top + 14) + uz * (-length / 3))
    ry = ctx.ground_median(rx, rz, 8)
    ctx.level_pad(rx, rz, 8, 14, ry)
    cv = kit.house_canvas(ctx.reg, 9, 7, EARTH_RURAL, roof="gable")
    ctx.place(cv, rx, rz, ry, facing_from_vector(cx - rx, cz - rz), foundation="minecraft:cobblestone")
    ctx.poi("canyon_ranger_station", rx, ry + 1, rz, "Canyon guide; Gan Jin & Zhang tribes")
    tx, tz, ty = rx - uz * 10 * 0, rz, ry
    px, pz = -uz, ux
    y = ry
    x, z = int(cx - uz * (half_top - 2) + ux * (-length / 3)), int(cz + ux * (half_top - 2) + uz * (-length / 3))
    dir_ = 1
    while y > floor + 1:
        for i in range(22):
            x += int(round(ux * dir_))
            z += int(round(uz * dir_))
            y -= 1 if i % 2 == 0 else 0
            B.box(x - 1, y - 1, z - 1, x + 1, y - 1, z + 1, "minecraft:red_sandstone")
            B.box(x - 1, y, z - 1, x + 1, y + 3, z + 1, AIR_S)
            if y <= floor + 1:
                break
        x += int(round(px * 3))
        z += int(round(pz * 3))
        dir_ = -dir_
    ctx.poi("canyon_floor", int(cx), floor + 1, int(cz))
    ctx.claim(cx, cz, length / 2)


# ==========================================================================
# Gaoling: town, Beifong estate, Earth Rumble VI arena (underground)
# ==========================================================================
def gaoling(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    y = ctx.ground_median(cx, cz, 12)
    ctx.level_pad(cx, cz, 14, 22, y, top="minecraft:dirt_path")
    B.cyl(cx, cz, y, y, 13, "minecraft:stone_bricks")
    for k in range(6):  # market stalls with coloured awnings
        a = 2 * math.pi * k / 6
        mx, mz = int(cx + 9 * math.cos(a)), int(cz + 9 * math.sin(a))
        B.box(mx - 1, y + 1, mz - 1, mx + 1, y + 1, mz + 1, "minecraft:spruce_planks")
        for (ox, oz) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            B.box(mx + ox, y + 1, mz + oz, mx + ox, y + 3, mz + oz, "minecraft:spruce_fence")
        B.box(mx - 2, y + 4, mz - 2, mx + 2, y + 4, mz + 2, ["minecraft:green_wool", "minecraft:yellow_wool", "minecraft:red_wool"][k % 3])
    ctx.poi("market_square", cx, y + 1, cz)
    hs = place_houses(ctx, cx, cz, 18, 100, 30, [EARTH, EARTH, EARTH_POOR], stories=(1, 2, 1), avoid=[(cx, cz, 15)],
                      max_slope=8, tries=2500)
    for (hx, hz, *_r) in hs:
        paint_path(ctx, cx, cz, hx, hz, 2)
    # --- Beifong estate: walled compound on flat ground away from town
    spot = find_flat(ctx, cx, cz, 170, 36, y - 12, y + 12)
    ex, ez, ey = spot if spot else (cx + 120, cz, y)
    if math.hypot(ex - cx, ez - cz) < 110:
        a = math.atan2(ez - cz, ex - cx) if (ex, ez) != (cx, cz) else 0.0
        ex, ez = int(cx + 120 * math.cos(a)), int(cz + 120 * math.sin(a))
        ey = ctx.ground_median(ex, ez, 20)
    ctx.level_pad(ex, ez, 36, 50, ey, square=True, top="minecraft:grass_block[snowy=false]")
    face = facing_from_vector(cx - ex, cz - ez)
    cv = Canvas(ctx.reg, (70, 34, 56))
    cv.walls(0, 1, 0, 69, 6, 55, "minecraft:stone_bricks")
    kit.hip_roof(cv, 0, 0, 69, 0, 7, EARTH.roof_stairs, EARTH.roof, overhang=1, flare=False, max_levels=1)
    kit.hip_roof(cv, 0, 55, 69, 55, 7, EARTH.roof_stairs, EARTH.roof, overhang=1, flare=False, max_levels=1)
    kit.hip_roof(cv, 0, 0, 0, 55, 7, EARTH.roof_stairs, EARTH.roof, overhang=1, flare=False, max_levels=1)
    kit.hip_roof(cv, 69, 0, 69, 55, 7, EARTH.roof_stairs, EARTH.roof, overhang=1, flare=False, max_levels=1)
    cv.box(31, 1, 55, 38, 5, 55, AIR_S)  # main gate (front = +z)
    cv.box(30, 6, 55, 39, 9, 56, "minecraft:dark_oak_planks")
    # the flying-boar crest over the gate
    for (u, v) in ((33, 7), (34, 7), (35, 7), (36, 7), (32, 8), (37, 8), (34, 8), (35, 8)):
        cv.set(u, v, 57, "minecraft:green_concrete")
    kit.house(cv, 20, 1, 12, 30, 16, EARTH, stories=2, story_h=5)
    kit.hip_roof(cv, 27, 17, 42, 23, 13, EARTH.roof_stairs, EARTH.roof, overhang=1)
    kit.house(cv, 4, 1, 6, 12, 10, EARTH, stories=1)
    kit.house(cv, 54, 1, 6, 12, 10, EARTH, stories=1)
    cv.box(8, 0, 36, 22, 0, 48, "minecraft:water[level=0]")
    cv.box(9, -0, 37, 21, 0, 47, "minecraft:water[level=0]")
    for (u, v) in ((6, 34), (24, 50), (48, 40), (60, 46)):
        kit.tree(cv, u, 1, v, "cherry", 5, rng=rng, mode=SET)
    cv.box(33, 0, 29, 36, 0, 54, "minecraft:polished_andesite")
    pl = ctx.place(cv, ex, ez, ey, face, anchor=(35, 0, 28), foundation="minecraft:stone_bricks")
    ctx.poi("beifong_estate", *pl.to_world(35, 1, 30), "Toph's family estate (flying-boar crest)")
    paint_path(ctx, cx, cz, *pl.to_world(35, 0, 60)[::2], 3)
    # --- Earth Rumble VI: underground arena reached through a hillside cave
    a = math.atan2(ez - cz, ex - cx) + math.pi * 0.8
    ax_, az_ = int(cx + 110 * math.cos(a)), int(cz + 110 * math.sin(a))
    gy = ctx.ground_median(ax_, az_, 30)
    fy = gy - 34
    B.box(ax_ - 30, fy, az_ - 24, ax_ + 30, fy + 22, az_ + 24, AIR_S)
    B.box(ax_ - 31, fy - 1, az_ - 25, ax_ + 31, fy - 1, az_ + 25, "minecraft:stone")
    B.box(ax_ - 9, fy, az_ - 9, ax_ + 9, fy + 2, az_ + 9, "minecraft:polished_andesite")  # the ring
    B.box(ax_ - 9, fy + 3, az_ - 9, ax_ + 9, fy + 3, az_ + 9, "minecraft:smooth_stone")
    for k in range(7):  # spectator stands on three sides
        B.box(ax_ - 28 + k, fy + k, az_ - 22, ax_ + 28 - k, fy + k, az_ - 22 + k,
              kit.stair(B, "minecraft:stone_brick_stairs", "north"))
        B.box(ax_ - 28, fy + k, az_ - 20, ax_ - 28 + k, fy + k, az_ + 22,
              kit.stair(B, "minecraft:stone_brick_stairs", "west"))
        B.box(ax_ + 28 - k, fy + k, az_ - 20, ax_ + 28, fy + k, az_ + 22,
              kit.stair(B, "minecraft:stone_brick_stairs", "east"))
    for (ox, oz) in ((-12, -12), (12, -12), (-12, 12), (12, 12)):
        B.box(ax_ + ox, fy, az_ + oz, ax_ + ox, fy + 21, az_ + oz, "minecraft:stone_bricks")
        B.set(ax_ + ox + 1, fy + 12, az_ + oz, "minecraft:glowstone")
    B.box(ax_ - 3, fy, az_ + 18, ax_ + 3, fy + 4, az_ + 22, "minecraft:polished_andesite")  # announcer stage
    ctx.poi("earth_rumble_arena", ax_, fy + 4, az_, "Earth Rumble VI (The Blind Bandit vs The Boulder)")
    # sloping tunnel from a cave mouth down into the arena
    ux, uz = math.cos(a), math.sin(a)
    for i in range(80):
        x = int(ax_ + ux * (24 + i))
        z = int(az_ + uz * (24 + i))
        yy = fy + int(i * 0.45)
        B.box(x - 2, yy, z - 2, x + 2, yy + 4, z + 2, AIR_S)
        B.box(x - 2, yy - 1, z - 2, x + 2, yy - 1, z + 2, "minecraft:cobblestone")
        if yy + 4 >= ctx.ground(x, z):
            ctx.poi("earth_rumble_entrance", x, yy, z, "Hidden cave entrance")
            break
    ctx.claim(cx, cz, 100)
    ctx.claim(ex, ez, 50)


# ==========================================================================
# Serpent's Pass: a narrow rock spine with water on both sides
# ==========================================================================
def serpents_pass(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    pts = s.path or [(s.x, s.z - 200), (s.x, s.z + 200)]
    rng = ctx.rng
    spine_top = ctx.sea + 7
    for (xa, za), (xb, zb) in zip(pts[:-1], pts[1:]):
        L = int(math.hypot(xb - xa, zb - za))
        ux, uz = (xb - xa) / max(L, 1), (zb - za) / max(L, 1)
        pad = 40
        x0, z0 = int(min(xa, xb)) - pad, int(min(za, zb)) - pad
        W, Lz = int(abs(xb - xa)) + 2 * pad + 1, int(abs(zb - za)) + 2 * pad + 1
        g = ctx.field(x0, z0, W, Lz)
        wtr = ctx.field(x0, z0, W, Lz, "water")
        X = np.arange(W)[:, None] + x0 - xa
        Z = np.arange(Lz)[None, :] + z0 - za
        along = X * ux + Z * uz
        across = -X * uz + Z * ux
        seg = (along >= -2) & (along <= L + 2)
        from ..noise import fbm
        n1 = fbm(g.shape, 40, 11, 3, origin=(x0, z0))
        n2 = fbm(g.shape, 70, 23, 3, origin=(x0, z0))
        wobble = 7 * fbm(g.shape, 90, 5, 2, origin=(x0, z0))
        across = across + wobble  # meandering spine
        half = 4.5 + 2.5 * n1
        spine = seg & (np.abs(across) <= half)
        flood = seg & (np.abs(across) > half + 1) & (np.abs(across) <= 24 + 12 * n2)
        # gaps where the path dips under the water
        gap = np.zeros_like(seg)
        for c in rng.uniform(0.25, 0.85, size=2):
            gap |= seg & (np.abs(along - c * L) < 5) & (np.abs(across) <= 4)
        h = (spine_top + 4 * n2 + (np.abs(across) > half - 2) * -2 + (np.abs(across) > half - 1) * -3).astype(np.int32)
        h = np.where(gap, ctx.sea - 1, h)
        h = np.where(flood, np.minimum(g, ctx.sea - 5), h)
        m = spine | flood
        ctx.shape_terrain(x0, z0, h.astype(np.int32), m, top="minecraft:stone", sub="minecraft:andesite")
        newly = flood & (wtr == NONE)
        ctx.terrain.fill_columns(x0, z0, np.where(newly | (gap & (wtr == NONE)), h + 1, 0),
                                 np.where(newly | (gap & (wtr == NONE)), ctx.sea + 1, 0), WATER_S)
        # the trail itself: rough cobble & gravel along the crest
        path = seg & (np.abs(across) <= 1.2) & ~gap
        ctx.terrain.fill_columns(x0, z0, np.where(path, h, 0), np.where(path, h + 1, 0), "minecraft:cobblestone")
    ctx.integration.append("rock spine raised to y=%d; 27-block moats flooded to sea level on both sides" % spine_top)
    # carved stair entrance and the warning sign at the south end
    (xa, za), (xb, zb) = pts[0], pts[1]
    ux, uz = (xb - xa), (zb - za)
    n = math.hypot(ux, uz) or 1
    ux, uz = ux / n, uz / n
    for i in range(12):
        x, z = int(xa - ux * (i + 1)), int(za - uz * (i + 1))
        B.box(x - 2, spine_top - 12 + (12 - i) - 1, z - 2, x + 2, spine_top - i, z + 2, "minecraft:stone_bricks")
    sx, sz = int(xa - ux * 3 + uz * 3), int(za - uz * 3 - ux * 3)
    B.set(sx, spine_top + 1, sz, "minecraft:oak_sign[rotation=0,waterlogged=false]")
    B.add_block_entity(sx, spine_top + 1, sz, _sign_factory(["Serpent's Pass", "", "Abandon hope", ""]))
    ctx.poi("pass_entrance_sign", sx, spine_top + 1, sz, "'Abandon hope' sign (2x12)")
    mx, mz = pts[len(pts) // 2]
    ctx.poi("serpent_lair", int(mx + uz * 20), ctx.sea - 10, int(mz - ux * 20), "The serpent (spawn in the moat)")
    ctx.poi("pass_north_end", pts[-1][0], spine_top + 1, pts[-1][1])
    ctx.claim(mx, mz, 200)


def _sign_factory(lines: list[str]):
    import json

    from nbtlib import tag as T

    def make(dv: int):
        if dv >= 4325:  # 1.21.5+: text components stored as NBT strings
            msgs = [T.String(t) for t in lines]
        else:
            msgs = [T.String(json.dumps({"text": t})) for t in lines]
        side = lambda m: T.Compound({"messages": T.List[T.String](m), "color": T.String("black"),  # noqa: E731
                                     "has_glowing_text": T.Byte(0)})
        return T.Compound({"id": T.String("minecraft:sign"), "keepPacked": T.Byte(0), "is_waxed": T.Byte(1),
                           "front_text": side(msgs), "back_text": side([T.String('""') if dv < 4325 else T.String("")] * 4)})
    return make


# ==========================================================================
# Full Moon Bay: hidden ferry station in a sheltered cove
# ==========================================================================
def full_moon_bay(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    wx, wz = water_direction(ctx, s.x, s.z, 100)
    face = facing_from_vector(wx, wz)
    fx, fz = unit(face)
    cx, cz = int(s.x - fx * 30), int(s.z - fz * 30)
    y = ctx.sea + 3
    ctx.level_pad(cx, cz, 34, 48, y, top="minecraft:stone_bricks", sub="minecraft:stone")
    # sheltering cliff crescent behind the station ("hidden" cove)
    for k in range(-70, 71, 2):
        a = math.atan2(-fz, -fx) + math.radians(k)
        rx, rz = int(cx + 46 * math.cos(a)), int(cz + 46 * math.sin(a))
        h = int(26 - abs(k) * 0.18)
        B.cyl(rx, rz, ctx.ground(rx, rz) - 2, y + h, 5, "minecraft:stone", mode=SOFT)
    cv = kit.house_canvas(ctx.reg, 27, 15, EARTH, stories=2, story_h=5)
    ctx.place(cv, cx - fx * 8, cz - fz * 8, y, face, foundation="minecraft:stone_bricks")
    ctx.poi("ferry_terminal", cx - fx * 8, y + 1, cz - fz * 8, "Tickets & passports for Ba Sing Se")
    cv2 = kit.house_canvas(ctx.reg, 9, 7, EARTH, stories=1)
    ctx.place(cv2, cx + fz * 22, cz - fx * 22, y, face, foundation="minecraft:stone_bricks")
    ctx.poi("passport_office", cx + fz * 22, y + 1, cz - fx * 22)
    for side in (-14, 0, 14):  # three piers with moored ferries
        px, pz = cx + fz * side, cz - fx * side
        for k in range(20, 70):
            x, z = px + fx * k, pz + fz * k
            B.box(x - 1, ctx.sea + 1, z - 1, x + 1, ctx.sea + 1, z + 1, "minecraft:spruce_planks")
            if k % 5 == 0:
                B.box(x, ctx.sea - 8, z, x, ctx.sea, z, "minecraft:spruce_log[axis=y]")
    for side in (-7, 7):
        bcv = Canvas(ctx.reg, (34, 16, 13))
        kit.boat(bcv, 1, 3, 6, 32, 11, cabin_pal=EARTH)
        ctx.place(bcv, cx + fz * side + fx * 45, cz - fx * side + fz * 45, ctx.sea - 3,
                  {"north": "east", "south": "west", "east": "south", "west": "north"}[face], anchor=(17, 0, 6))
    ctx.poi("ferry_dock", cx + fx * 60, ctx.sea + 2, cz + fz * 60, "Ferries across the lake to Ba Sing Se")
    ctx.claim(cx, cz, 60)


# ==========================================================================
# Si Wong Desert: Wan Shi Tong's Library, Misty Palms Oasis, the rock
# ==========================================================================
def wan_shi_tong_library(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    cx, cz = s.x, s.z
    g = ctx.ground_median(cx, cz, 20)
    roof = g - 6
    bot = roof - 64
    SS, CS, DO = "minecraft:smooth_sandstone", "minecraft:cut_sandstone", "minecraft:dark_oak_planks"
    # buried shell
    B.box(cx - 50, bot, cz - 38, cx + 50, roof, cz + 38, CS)
    B.box(cx - 48, bot + 1, cz - 36, cx + 48, roof - 2, cz + 36, AIR_S)
    B.box(cx - 50, bot, cz - 38, cx + 50, bot, cz + 38, DO)
    # grand atrium and galleried floors of stacks
    for fy in range(bot + 10, roof - 4, 10):
        B.box(cx - 48, fy, cz - 36, cx + 48, fy, cz + 36, DO)
        B.box(cx - 20, fy, cz - 20, cx + 20, fy, cz + 20, AIR_S)
        B.box(cx - 20, fy + 1, cz - 20, cx + 20, fy + 1, cz + 20, "minecraft:dark_oak_fence")
        B.box(cx - 19, fy + 1, cz - 19, cx + 19, fy + 1, cz + 19, AIR_S)
    for fy in range(bot + 1, roof - 4, 10):
        for x in range(cx - 46, cx + 47, 4):  # rows of shelves
            if abs(x - cx) <= 22:
                continue
            B.box(x, fy, cz - 34, x, fy + 7, cz + 34, "minecraft:bookshelf")
            B.box(x, fy, cz - 2, x, fy + 3, cz + 2, AIR_S)
        for z in range(cz - 34, cz + 35, 4):
            if abs(z - cz) <= 22:
                continue
            B.box(cx - 22, fy, z, cx + 22, fy + 7, z, "minecraft:bookshelf")
            B.box(cx - 2, fy, z, cx + 2, fy + 3, z, AIR_S)
    for (ox, oz) in ((-21, -21), (21, -21), (-21, 21), (21, 21)):
        B.box(cx + ox, bot + 1, cz + oz, cx + ox, roof - 2, cz + oz, "minecraft:chiseled_sandstone")
    ctx.poi("main_atrium", cx, bot + 1, cz, "Wan Shi Tong's collection")
    # planetarium: dark domed room with the brass sun/moon dial
    px, pz = cx + 34, cz
    B.box(px - 12, bot + 1, pz - 12, px + 12, bot + 22, pz + 12, "minecraft:black_concrete")
    B.ellipsoid(px, bot + 3, pz, 11, 18, 11, AIR_S)
    rng = ctx.rng
    for k in range(60):
        a, e = rng.uniform(0, 2 * math.pi), rng.uniform(0.2, 1.4)
        B.set(int(px + 11.5 * math.cos(a) * math.cos(e)), int(bot + 3 + 18.5 * math.sin(e)),
              int(pz + 11.5 * math.sin(a) * math.cos(e)), "minecraft:glowstone")
    B.cyl(px, pz, bot + 1, bot + 1, 6, "minecraft:cut_copper", hollow=True, thickness=1)
    B.cyl(px, pz, bot + 2, bot + 2, 2, "minecraft:gold_block")
    B.box(px - 12, bot + 1, pz - 2, px - 12, bot + 4, pz + 2, AIR_S)
    ctx.poi("planetarium", px, bot + 1, pz, "Solar-eclipse date revealed (Day of Black Sun)")
    # the one visible tower: rises through the dunes with a pointed dome
    tb = roof + 1
    B.box(cx - 7, roof - 2, cz - 7, cx + 7, g + 32, cz + 7, SS)
    B.box(cx - 5, roof - 2, cz - 5, cx + 5, g + 31, cz + 5, AIR_S)
    for y in range(g + 6, g + 30, 8):  # arched windows
        for (ox, oz) in ((0, 7), (0, -7), (7, 0), (-7, 0)):
            B.box(cx + ox - (1 if oz else 0), y, cz + oz - (1 if ox else 0),
                  cx + ox + (1 if oz else 0), y + 4, cz + oz + (1 if ox else 0), AIR_S)
    kit.hip_roof(B, cx - 7, cz - 7, cx + 7, cz + 7, g + 33, "minecraft:dark_oak_stairs", DO, overhang=1)
    B.cone(cx, cz, g + 41, 10, 2.5, 0.3, "minecraft:dark_oak_planks")
    for i in range(roof - 2, g + 30):  # spiral stair down the tower
        a = (i - roof) * 0.6
        B.box(cx + int(4 * math.cos(a)), i, cz + int(4 * math.sin(a)), cx + int(4 * math.cos(a)), i,
              cz + int(4 * math.sin(a)), "minecraft:sandstone")
    B.box(cx - 5, roof - 2, cz - 5, cx + 5, roof, cz + 5, AIR_S)
    ctx.poi("library_tower_top", cx, g + 30, cz, "Only the spire shows above the dunes")
    ctx.claim(cx, cz, 60)


def misty_palms_oasis(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    y = ctx.ground_median(cx, cz, 10)
    ctx.level_pad(cx, cz, 20, 34, y, top="minecraft:sand", sub="minecraft:sandstone")
    B.cyl(cx, cz, y - 3, y, 13, WATER_S)
    B.cyl(cx, cz, y - 4, y - 4, 13, "minecraft:sand")
    B.cyl(cx, cz, y, y, 14.3, "minecraft:grass_block[snowy=false]", hollow=True, thickness=1.2)
    for k in range(12):
        a = 2 * math.pi * k / 12 + rng.uniform(-0.2, 0.2)
        tx, tz = int(cx + 17 * math.cos(a)), int(cz + 17 * math.sin(a))
        kit.tree(B, tx, y + 1, tz, "palm", int(rng.integers(7, 11)), rng=rng)
    hs = place_houses(ctx, cx, cz, 26, 52, 9, [DESERT], roof="flat", avoid=[(cx, cz, 22)], max_slope=6)
    ctx.poi("oasis_pool", cx, y, cz, "Misty Palms Oasis")
    if hs:
        hx, hz, *_ = hs[0]
        ctx.poi("misty_palms_inn", hx, y + 1, hz, "Where the group met Professor Zei")
    # sand sailer parked at the edge
    a = rng.uniform(0, 2 * math.pi)
    sx, sz = int(cx + 60 * math.cos(a)), int(cz + 60 * math.sin(a))
    sy = ctx.ground(sx, sz)
    B.box(sx - 6, sy + 1, sz - 1, sx + 6, sy + 1, sz + 1, "minecraft:spruce_planks")
    B.box(sx, sy + 2, sz, sx, sy + 10, sz, "minecraft:spruce_fence")
    B.box(sx - 4, sy + 5, sz, sx - 1, sy + 10, sz, "minecraft:white_wool")
    ctx.poi("sand_sailer", sx, sy + 1, sz, "Sandbender sailer")
    ctx.claim(cx, cz, 55)


def si_wong_rock(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    g = ctx.ground_median(cx, cz, 15)
    for k in range(9):
        B.ellipsoid(cx + int(rng.integers(-18, 19)), g + int(rng.integers(4, 18)), cz + int(rng.integers(-12, 13)),
                    rng.uniform(10, 18), rng.uniform(8, 16), rng.uniform(8, 13),
                    ["minecraft:sandstone", "minecraft:terracotta", "minecraft:smooth_sandstone"][k % 3])
    B.ellipsoid(cx, g + 3, cz + 14, 12, 7, 9, AIR_S)
    B.box(cx - 12, g, cz + 5, cx + 12, g, cz + 22, "minecraft:sand")
    ctx.poi("rock_shelter", cx, g + 1, cz + 14, "Appa was taken by sandbenders here")
    ctx.claim(cx, cz, 45)


# ==========================================================================
# Wulong Forest: karst rock pillars
# ==========================================================================
def wulong_forest(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    R = int(min(200, max(120, s.fit_radius)))
    pts: list[tuple[int, int, float]] = []
    for _ in range(900):
        a, r = rng.uniform(0, 2 * math.pi), R * math.sqrt(rng.uniform(0, 1))
        x, z = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        pr = rng.uniform(5, 13)
        if ctx.is_water(x, z):
            continue
        if any(math.hypot(x - px, z - pz) < pr + qr + 6 for px, pz, qr in pts):
            continue
        pts.append((x, z, pr))
        if len(pts) >= 60:
            break
    tallest = None
    for (x, z, pr) in pts:
        g = ctx.ground_median(x, z, int(pr))
        h = int(min(rng.uniform(35, 100), 300 - g))
        broken = rng.random() < 0.12
        if broken:
            h = int(h * 0.35)
        for yy in range(g - 3, g + h + 1):
            t = (yy - g) / max(h, 1)
            r_ = pr * (1.0 - 0.25 * t) * (1 + 0.12 * math.sin(yy * 0.4 + x)) + (1.2 if t < 0.08 else 0)
            mat = "minecraft:stone" if (yy // 5) % 3 else "minecraft:andesite"
            if t > 0.85 and rng.random() < 0.3:
                mat = "minecraft:mossy_cobblestone"
            B.cyl(x, z, yy, yy, r_, mat)
        B.cyl(x, z, g + h, g + h, pr * 0.72, "minecraft:grass_block[snowy=false]")
        if not broken:
            for k in range(int(pr // 4) + 1):
                kit.tree(B, x + int(rng.integers(-2, 3)), g + h + 1, z + int(rng.integers(-2, 3)),
                         "spruce" if rng.random() < 0.5 else "oak", int(rng.integers(5, 9)), rng=rng)
        else:
            for k in range(6):
                B.ellipsoid(x + int(rng.integers(-12, 13)), g + 1, z + int(rng.integers(-12, 13)),
                            rng.uniform(1.5, 3.5), rng.uniform(1.5, 3), rng.uniform(1.5, 3.5),
                            "minecraft:cobblestone", mode=SOFT)
        if tallest is None or g + h > tallest[2]:
            tallest = (x, z, g + h)
    if tallest:
        ctx.poi("final_battle_pillar", tallest[0], tallest[2] + 1, tallest[1],
                "Aang vs. Fire Lord Ozai; Avatar State unlocked on the rock")
    ctx.poi("forest_center", cx, ctx.ground(cx, cz) + 1, cz, "Ozai's airship fleet flies over Wulong")
    ctx.notes.append(f"{len(pts)} karst pillars within r={R}.")
    ctx.claim(cx, cz, R)
