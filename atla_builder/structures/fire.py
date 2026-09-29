"""Fire Nation landmarks."""
from __future__ import annotations

import math

import numpy as np

from ..buffer import SOFT, Canvas
from ..palettes import FIRE, FIRE_COMMON
from ..terrain import NONE
from . import kit
from .common import BuildContext, facing_from_vector, unit, water_direction
from .village import find_flat, place_houses

AIR_S = "minecraft:air"
WATER_S = "minecraft:water[level=0]"
BLK = "minecraft:polished_blackstone_bricks"
MAX_Y = 318


def _fire_hall(p, x0, y0, z0, w, d, stories=2, story_h=6, tiers=2, pal=FIRE):
    """Fire Nation hall: black stone plinth, red walls & pillars, stacked dark-red roofs."""
    p.box(x0 - 2, y0 - 2, z0 - 2, x0 + w + 1, y0, z0 + d + 1, BLK)
    kit.house(p, x0, y0 + 1, z0, w, d, pal, stories=stories, story_h=story_h, overhang=2)
    top = y0 + 2 + stories * story_h
    for t in range(1, tiers):
        inset = 3 * t + 2
        if w - 2 * inset < 3 or d - 2 * inset < 3:
            break
        p.box(x0 + inset, top, z0 + inset, x0 + w - 1 - inset, top + 4, z0 + d - 1 - inset, pal.wall)
        kit.hip_roof(p, x0 + inset, z0 + inset, x0 + w - 1 - inset, z0 + d - 1 - inset, top + 5,
                     pal.roof_stairs, pal.roof, overhang=2, ridge=pal.ridge)
        top += 6
    return top


# ==========================================================================
def fire_nation_capital(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    Rf, Rr = 150, 225
    peak = ctx.ground_max(cx, cz, 30)
    yF = int(np.clip(peak - 110, ctx.sea + 70, 190))
    rim = yF + 62
    R = Rr + 70
    n = 2 * R + 1
    x0, z0 = cx - R, cz - R
    dx = np.arange(n)[:, None] - R
    dz = np.arange(n)[None, :] - R
    d = np.hypot(dx, dz)
    nat = ctx.field(x0, z0, n, n).astype(np.float32)
    new_h = np.where(d <= Rf, yF, 0).astype(np.float32)
    # inner slope: four residential terraces
    t = np.clip((d - Rf) / (Rr - Rf), 0, 1)
    terr = yF + np.floor(t * 5) / 5 * (rim - yF)
    new_h = np.where((d > Rf) & (d <= Rr), terr, new_h)
    # outer flank blends down to the island
    t2 = np.clip((d - Rr) / 70.0, 0, 1)
    outer = rim * (1 - t2 * t2 * (3 - 2 * t2)) + nat * (t2 * t2 * (3 - 2 * t2))
    new_h = np.where(d > Rr, np.minimum(np.maximum(outer, nat * 0 + outer), np.maximum(outer, nat)), new_h)
    new_h = np.where(d > Rr, np.where(nat > outer, nat, outer), new_h)
    mask = d < R
    tops = np.where(d <= Rf, ctx.reg.id(BLK), ctx.reg.id("minecraft:blackstone"))
    tops = np.where(d > Rr, ctx.reg.id("minecraft:basalt[axis=y]"), tops).astype(np.uint16)
    tops = np.where(d > Rr + 30, 0, tops).astype(np.uint16)
    ctx.shape_terrain(x0, z0, np.rint(new_h).astype(np.int32), mask,
                      top=np.where(tops == 0, ctx.reg.id("minecraft:grass_block[snowy=false]"), tops).astype(np.uint16),
                      sub=np.full((n, n), ctx.reg.id("minecraft:blackstone"), np.uint16))
    ctx.integration.append(f"volcano summit hollowed into the Royal Caldera: floor y={yF}, rim y={rim}, "
                           f"floor r={Rf}, rim r={Rr}; 5 residential terraces on the inner slope")
    # --- palace grounds (north of centre) raised on a black stone platform
    px, pz = cx, cz - 45
    py = yF + 8
    B.box(px - 60, yF, pz - 48, px + 60, py, pz + 40, BLK)
    B.walls(px - 60, py + 1, pz - 48, px + 60, py + 7, pz + 40, "minecraft:red_terracotta")
    B.box(px - 60, py + 8, pz - 48, px + 60, py + 8, pz + 40, "minecraft:red_nether_brick_slab[type=bottom,waterlogged=false]")
    B.box(px - 60, py + 8, pz - 47, px + 60, py + 8, pz + 39, AIR_S)
    B.box(px - 8, py + 1, pz + 40, px + 8, py + 6, pz + 40, AIR_S)  # palace gate
    top = _fire_hall(B, px - 30, py, pz - 36, 61, 36, stories=3, story_h=7, tiers=3)
    kit.pagoda(B, px, pz - 18, top, 13, 4, FIRE, tier_h=6, spire="minecraft:gold_block")
    for sx in (-45, 45):
        _fire_hall(B, px + sx - 9, py, pz - 30, 18, 24, stories=2, story_h=6)
    for k in range(-56, 57, 8):  # colonnade of crimson pillars along the front
        B.box(px + k, py + 1, pz + 6, px + k, py + 9, pz + 6, "minecraft:stripped_crimson_stem[axis=y]")
        B.set(px + k, py + 10, pz + 6, "minecraft:gold_block")
    ctx.poi("fire_lord_palace", px, py + 1, pz - 18, "Throne room with the wall of fire")
    ctx.poi("war_room", px + 20, py + 1, pz - 25, "Zuko's war meeting (1x12 flashback)")
    # grand stairs from the plaza up to the palace gate
    for k in range(9):
        B.box(px - 10, yF + k, pz + 49 - k, px + 10, yF + k, pz + 49 - k,
              kit.stair(B, "minecraft:polished_blackstone_brick_stairs", "north"))
    # --- Royal Plaza
    B.box(px - 45, yF, pz + 50, px + 45, yF, pz + 120, "minecraft:polished_blackstone")
    B.box(px - 40, yF, pz + 55, px + 40, yF, pz + 115, "minecraft:red_terracotta")
    B.box(px - 36, yF, pz + 59, px + 36, yF, pz + 111, "minecraft:polished_blackstone_bricks")
    for (u, v) in ((-38, 60), (38, 60), (-38, 110), (38, 110)):
        B.box(px + u, yF + 1, pz + v, px + u, yF + 12, pz + v, "minecraft:red_nether_bricks")
        B.set(px + u, yF + 13, pz + v, "minecraft:magma_block")
    ctx.poi("royal_plaza", px, yF + 1, pz + 85, "Royal Plaza (Day of Black Sun)")
    # --- Agni Kai arena west of the plaza
    ax_, az_ = px - 80, pz + 80
    B.box(ax_ - 18, yF + 1, az_ - 24, ax_ + 18, yF + 16, az_ + 24, "minecraft:red_terracotta")
    B.box(ax_ - 17, yF + 1, az_ - 23, ax_ + 17, yF + 15, az_ + 23, AIR_S)
    B.box(ax_ - 17, yF, az_ - 23, ax_ + 17, yF, az_ + 23, "minecraft:polished_blackstone")
    kit.hip_roof(B, ax_ - 18, az_ - 24, ax_ + 18, az_ + 24, yF + 17, FIRE.roof_stairs, FIRE.roof, overhang=2,
                 ridge=FIRE.ridge, max_levels=4)
    B.box(ax_ - 17, yF + 17, az_ - 15, ax_ + 17, yF + 20, az_ + 15, AIR_S)  # open skylight
    for k in (-22, 22):
        B.box(ax_ - 3, yF, az_ + k, ax_ + 3, yF, az_ + k, "minecraft:magma_block")
    B.box(ax_ + 18, yF + 1, az_ - 3, ax_ + 18, yF + 6, az_ + 3, AIR_S)
    ctx.poi("agni_kai_arena", ax_, yF + 1, az_, "Zuko vs. Ozai (flashback), Zuko vs. Azula (3x21)")
    # --- city houses on the caldera floor ring and the terraces
    avoid = [(px, pz - 4, 80), (px, pz + 85, 60), (ax_, az_, 34)]
    place_houses(ctx, cx, cz, 95, Rf - 8, 60, [FIRE_COMMON, FIRE], stories=(1, 2, 2), avoid=avoid,
                 max_slope=4, tries=3000)
    place_houses(ctx, cx, cz, Rf + 4, Rr - 6, 110, [FIRE_COMMON], stories=(1, 1, 2), avoid=avoid,
                 max_slope=3, tries=5000, mode_pad=False)
    # --- Harbor City outside the rim and the road through the rim
    wx, wz = water_direction(ctx, cx, cz, 450)
    face = facing_from_vector(wx, wz)
    hx, hz = int(cx + wx * (Rr + 120)), int(cz + wz * (Rr + 120))
    spot = find_flat(ctx, hx, hz, 120, 20, ctx.sea + 1, ctx.sea + 30, water_within=70)
    if spot:
        hx, hz, hy = spot
        place_houses(ctx, hx, hz, 10, 70, 22, [FIRE_COMMON], stories=(1, 2, 1), max_slope=7, tries=1500)
        ctx.poi("harbor_city", hx, hy + 1, hz, "Harbor City below the Royal Caldera")
    # road tunnel through the rim toward the harbour
    ux, uz = unit(face)
    for k in range(Rf - 5, Rr + 70):
        x, z = cx + ux * k, cz + uz * k
        fy = ctx.ground(x, z) if k > Rr + 10 else yF + max(0, int((k - Rf) * 0.25))
        B.box(x - 4 * abs(uz), fy + 1, z - 4 * abs(ux), x + 4 * abs(uz), fy + 7, z + 4 * abs(ux), AIR_S)
        B.box(x - 4 * abs(uz), fy, z - 4 * abs(ux), x + 4 * abs(uz), fy, z + 4 * abs(ux), BLK)
    gx, gz = cx + ux * Rr, cz + uz * Rr
    ctx.poi("caldera_gate", gx, ctx.ground(gx, gz) + 1, gz, "Main gate through the caldera rim")
    ctx.claim(cx, cz, R)


# ==========================================================================
def crescent_island(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    cx, cz = s.x, s.z
    y = ctx.ground_median(cx, cz, 14)
    ctx.level_pad(cx, cz, 30, 46, y, top=BLK, sub="minecraft:blackstone")
    wx, wz = water_direction(ctx, cx, cz, 200)
    face = facing_from_vector(wx, wz)
    cv = Canvas(ctx.reg, (50, 120, 50))
    for k in range(3):  # stepped black plinth
        cv.box(4 + k * 2, k, 4 + k * 2, 45 - k * 2, k, 45 - k * 2, BLK)
    top = _fire_hall(cv, 12, 3, 12, 26, 26, stories=2, story_h=7, tiers=2)
    # the temple's signature tower: tall and slender, flared tiers, flame-like spire
    t = kit.pagoda(cv, 25, 25, top - 2, 11, 4, FIRE, tier_h=6)
    cv.box(25, t + 1, 25, 25, t + 16, 25, "minecraft:gold_block")
    cv.box(24, t + 1, 25, 26, t + 6, 25, "minecraft:gold_block")
    cv.box(25, t + 1, 24, 25, t + 6, 26, "minecraft:gold_block")
    # sanctuary: Avatar Roku statue behind the five-dragon door
    cv.box(15, 4, 15, 34, 12, 30, AIR_S)
    kit.blocky_statue(cv, 25, 4, 20, 1, dict(robe="minecraft:red_concrete", robe_trim="minecraft:gold_block",
                                            skin="minecraft:white_terracotta", hair="minecraft:white_wool",
                                            belt="minecraft:black_concrete", accent="minecraft:gold_block",
                                            base="minecraft:polished_blackstone"))
    cv.box(22, 4, 37, 28, 11, 37, "minecraft:polished_blackstone")
    for k in range(5):
        cv.set(22 + k + (1 if k > 1 else 0), 8, 38, "minecraft:magma_block")
    cv.box(24, 4, 38, 26, 7, 38, AIR_S)
    pl = ctx.place(cv, cx, cz, y, face, anchor=(25, 0, 25))
    ctx.poi("roku_sanctuary", *pl.to_world(25, 5, 28), "Avatar Roku's statue (winter solstice)")
    ctx.poi("fire_temple_entrance", *pl.to_world(25, 4, 40))
    # a smoking lava vent at the island's crest
    hx, hz = cx - int(wx * 60), cz - int(wz * 60)
    hy = ctx.ground_median(hx, hz, 6)
    B.cone(hx, hz, hy - 2, 18, 16, 5, "minecraft:basalt[axis=y]")
    B.cyl(hx, hz, hy + 12, hy + 15, 4, "minecraft:lava[level=0]")
    B.cyl(hx, hz, hy + 11, hy + 11, 4.5, "minecraft:magma_block")
    ctx.poi("crescent_volcano", hx, hy + 16, hz, "Erupting volcano (Roku's escape)")
    ctx.claim(cx, cz, 70)


# ==========================================================================
def sun_warriors(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    rng = ctx.rng
    cx, cz = s.x, s.z
    y = ctx.ground_median(cx, cz, 20)
    ctx.level_pad(cx, cz, 50, 80, y, top="minecraft:mossy_cobblestone", sub="minecraft:stone")
    ST = ["minecraft:stone_bricks", "minecraft:mossy_stone_bricks", "minecraft:cracked_stone_bricks"]
    face = facing_from_vector(*water_direction(ctx, cx, cz, 300))
    fx, fz = unit(face)
    # stepped pyramid with the Sun Stone chamber on top
    for k in range(8):
        h = 34 - k * 4
        for dy in range(4):
            yy = y + 1 + k * 4 + dy
            B.box(cx - h, yy, cz - h, cx + h, yy, cz + h, ST[(k + dy) % 3])
    top = y + 33
    B.box(cx - 5, top, cz - 5, cx + 5, top + 7, cz + 5, "minecraft:chiseled_stone_bricks")
    B.box(cx - 4, top, cz - 4, cx + 4, top + 6, cz + 4, AIR_S)
    B.box(cx - 1, top, cz - 1, cx + 1, top + 1, cz + 1, "minecraft:raw_gold_block")
    B.set(cx, top + 2, cz, "minecraft:shroomlight")
    ctx.poi("sun_stone_chamber", cx, top, cz, "The Sun Stone (source of the Sun Warriors' fire)")
    for k in range(34):  # front stair
        yy = y + 1 + k
        x, z = cx + fx * (35 - k), cz + fz * (35 - k)
        if fx:
            B.box(x, y + 1, z - 3, x, yy, z + 3, "minecraft:stone_bricks")
            B.box(x, yy + 1, z - 3, x, yy + 4, z + 3, AIR_S)
        else:
            B.box(x - 3, y + 1, z, x + 3, yy, z, "minecraft:stone_bricks")
            B.box(x - 3, yy + 1, z, x + 3, yy + 4, z, AIR_S)
    # Dancing Dragon plaza: red and blue step tiles in two interlocking spirals
    qx, qz = cx + fx * 70, cz + fz * 70
    B.cyl(qx, qz, y, y, 26, "minecraft:smooth_stone")
    for i in range(80):
        t = i / 80 * 4 * math.pi
        r = 3 + i * 0.28
        for col, off in (("minecraft:red_terracotta", 0), ("minecraft:blue_terracotta", math.pi)):
            B.box(int(qx + r * math.cos(t + off)), y, int(qz + r * math.sin(t + off)),
                  int(qx + r * math.cos(t + off)) + 1, y, int(qz + r * math.sin(t + off)) + 1, col)
    ctx.poi("dancing_dragon_plaza", qx, y + 1, qz, "The Dancing Dragon form")
    # ruins overgrown by the jungle
    for k in range(18):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(45, 120)
        rx, rz = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        ry = ctx.ground(rx, rz)
        w, d, h = (int(v) for v in rng.integers(6, 14, 3))
        B.box(rx, ry, rz, rx + w, ry + h, rz + d, ST[k % 3])
        B.box(rx + 1, ry + 1, rz + 1, rx + w - 1, ry + h, rz + d - 1, AIR_S)
        for j in range(8):  # collapse chunks
            B.ellipsoid(rx + int(rng.integers(0, w + 1)), ry + h, rz + int(rng.integers(0, d + 1)),
                        3, 3, 3, AIR_S)
        B.box(rx, ry + h - 1, rz - 1, rx + w, ry + h - 1, rz - 1,
              "minecraft:vine[east=false,north=false,south=true,up=false,west=false]", mode=SOFT)
    # the Eternal Flame shrine
    ex, ez = cx - fx * 60, cz - fz * 60
    ey = ctx.ground(ex, ez)
    B.box(ex - 5, ey, ez - 5, ex + 5, ey + 7, ez + 5, "minecraft:mossy_stone_bricks")
    B.box(ex - 4, ey + 1, ez - 4, ex + 4, ey + 6, ez + 4, AIR_S)
    B.set(ex, ey, ez, "minecraft:netherrack")
    B.set(ex, ey + 1, ez, "minecraft:fire[age=0,east=false,north=false,south=false,up=false,west=false]")
    B.box(ex + fx * 5 - 1, ey + 1, ez + fz * 5 - 1, ex + fx * 5 + 1, ey + 3, ez + fz * 5 + 1, AIR_S)
    ctx.poi("eternal_flame", ex, ey + 1, ez, "The Eternal Flame (first fire from the dragons)")
    # the Masters' mountain with the cave where Ran and Shaw live
    cands = [(cx - fz * 130, cz + fx * 130), (cx + fz * 130, cz - fx * 130), (cx - fx * 130, cz - fz * 130)]
    mx, mz = max(cands, key=lambda p: (-ctx.water_frac(p[0], p[1], 30), ctx.ground(p[0], p[1])))
    my = ctx.ground(mx, mz)
    B.ellipsoid(mx, my, mz, 40, 45, 32, "minecraft:stone", mode=SOFT)
    B.ellipsoid(mx, my + 30, mz, 12, 8, 12, AIR_S)
    B.box(mx - 14, my + 26, mz - 14, mx + 14, my + 26, mz + 14, "minecraft:smooth_stone")
    B.line((mx, my + 27, mz), (int(mx + fz * 40), my + 27, int(mz - fx * 40)), AIR_S, width=7)
    ctx.poi("dragon_masters_cave", mx, my + 27, mz, "Ran & Shaw emerge here")
    for k in range(40):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(80, 150)
        tx, tz = int(cx + r * math.cos(a)), int(cz + r * math.sin(a))
        kit.tree(B, tx, ctx.ground(tx, tz) + 1, tz, "jungle", int(rng.integers(8, 14)), rng=rng)
    ctx.claim(cx, cz, 150)


# ==========================================================================
def boiling_rock(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    cx, cz = s.x, s.z
    sea = ctx.sea
    r_isle, r_lake, r_rim, r_out = 30, 88, 112, 160
    rim_top = sea + 52
    R = r_out + 25
    n = 2 * R + 1
    x0, z0 = cx - R, cz - R
    dx = np.arange(n)[:, None] - R
    dz = np.arange(n)[None, :] - R
    d = np.hypot(dx, dz)
    nat = ctx.field(x0, z0, n, n).astype(np.float32)
    h = np.where(d <= r_isle, sea + 12, 0.0)
    h = np.where((d > r_isle) & (d <= r_lake), sea - 9, h)
    t = np.clip((d - r_lake) / (r_rim - r_lake), 0, 1)
    h = np.where((d > r_lake) & (d <= r_rim), sea - 9 + (rim_top - sea + 9) * np.sqrt(t), h)
    t2 = np.clip((d - r_rim) / (r_out - r_rim), 0, 1)
    h = np.where((d > r_rim) & (d <= r_out), rim_top - (rim_top - sea + 2) * t2 ** 0.8, h)
    t3 = np.clip((d - r_out) / 25.0, 0, 1)
    h = np.where(d > r_out, (sea - 2) * (1 - t3) + nat * t3, h)
    mask = d < R
    tops = np.where((d > r_isle) & (d <= r_lake), ctx.reg.id("minecraft:magma_block"),
                    ctx.reg.id("minecraft:basalt[axis=y]")).astype(np.uint16)
    ctx.shape_terrain(x0, z0, np.rint(h).astype(np.int32), mask, top=tops,
                      sub=np.full((n, n), ctx.reg.id("minecraft:blackstone"), np.uint16))
    ctx.integration.append(f"volcanic crater island raised from the sea floor (rim y={rim_top}); "
                           "magma-floored boiling lake with bubble columns")
    lake = (d > r_isle + 1) & (d <= r_lake - 1)
    ctx.struct.fill_columns(x0, z0, np.where(lake, sea - 8, 0), np.where(lake, sea + 1, 0),
                            "minecraft:bubble_column[drag=true]")
    # --- the prison on its island
    y = sea + 12
    B.cyl(cx, cz, y + 1, y + 11, 27, "minecraft:deepslate_bricks", hollow=True, thickness=2)
    B.cyl(cx, cz, y + 12, y + 12, 27.5, "minecraft:deepslate_brick_wall", hollow=True, thickness=1)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        tx, tz = int(cx + 27 * math.cos(a)), int(cz + 27 * math.sin(a))
        B.box(tx - 3, y + 1, tz - 3, tx + 3, y + 22, tz + 3, "minecraft:deepslate_bricks")
        B.box(tx - 2, y + 18, tz - 2, tx + 2, y + 21, tz + 2, AIR_S)
        kit.hip_roof(B, tx - 3, tz - 3, tx + 3, tz + 3, y + 23, FIRE.roof_stairs, FIRE.roof, overhang=1)
    # cell block: three storeys of barred cells
    B.box(cx - 18, y + 1, cz - 8, cx + 18, y + 16, cz + 8, "minecraft:polished_deepslate")
    B.box(cx - 17, y + 1, cz - 7, cx + 17, y + 15, cz + 7, AIR_S)
    for fl in range(3):
        fy = y + 1 + fl * 5
        B.box(cx - 17, fy - 1, cz - 7, cx + 17, fy - 1, cz + 7, "minecraft:polished_deepslate")
        B.box(cx - 17, fy - 1, cz - 1, cx + 17, fy - 1, cz + 1, "minecraft:polished_deepslate")
        for k in range(-16, 17, 4):
            for side in (-1, 1):
                B.box(cx + k, fy, cz + side * 7, cx + k + 2, fy + 3, cz + side * 7, AIR_S)
                B.box(cx + k, fy, cz + side * 2, cx + k + 3, fy + 3, cz + side * 2, "minecraft:iron_bars")
                B.box(cx + k + 3, fy, cz + side * 2, cx + k + 3, fy + 3, cz + side * 6, "minecraft:polished_deepslate")
    kit.hip_roof(B, cx - 18, cz - 8, cx + 18, cz + 8, y + 17, FIRE.roof_stairs, FIRE.roof, overhang=2)
    ctx.poi("cell_block", cx, y + 1, cz, "Sokka & Zuko's cells")
    # the cooler (freezing punishment cell)
    B.box(cx + 10, y + 1, cz + 12, cx + 16, y + 6, cz + 18, "minecraft:packed_ice")
    B.box(cx + 11, y + 2, cz + 13, cx + 15, y + 5, cz + 17, AIR_S)
    ctx.poi("the_cooler", cx + 13, y + 2, cz + 15)
    # warden's tower and gondola station
    wx_, wz_ = cx - 12, cz + 14
    B.box(wx_ - 4, y + 1, wz_ - 4, wx_ + 4, y + 30, wz_ + 4, "minecraft:deepslate_tiles")
    B.box(wx_ - 3, y + 1, wz_ - 3, wx_ + 3, y + 29, wz_ + 3, AIR_S)
    kit.hip_roof(B, wx_ - 4, wz_ - 4, wx_ + 4, wz_ + 4, y + 31, FIRE.roof_stairs, FIRE.roof, overhang=2,
                 ridge=FIRE.ridge)
    ctx.poi("warden_tower", wx_, y + 1, wz_, "The Warden")
    # gondola: twin cables from the tower to the crater rim, car half-way
    a = math.atan2(wz_ - cz, wx_ - cx)
    rx, rz = int(cx + (r_rim - 4) * math.cos(a)), int(cz + (r_rim - 4) * math.sin(a))
    ry = rim_top
    B.box(rx - 5, ry, rz - 5, rx + 5, ry + 8, rz + 5, "minecraft:deepslate_bricks")
    B.box(rx - 4, ry + 1, rz - 4, rx + 4, ry + 7, rz + 4, AIR_S)
    for off in (-1, 1):
        ox, oz = -math.sin(a) * off, math.cos(a) * off
        B.line((int(wx_ + ox), y + 26, int(wz_ + oz)), (int(rx + ox), ry + 7, int(rz + oz)),
               "minecraft:chain[axis=x,waterlogged=false]")
    mx, mz = (wx_ + rx) // 2, (wz_ + rz) // 2
    my = (y + 26 + ry + 7) // 2
    B.box(mx - 2, my - 5, mz - 2, mx + 2, my - 1, mz + 2, "minecraft:iron_block")
    B.box(mx - 1, my - 4, mz - 2, mx + 1, my - 2, mz + 2, AIR_S)
    ctx.poi("gondola", mx, my - 4, mz, "Escape route over the boiling lake")
    ctx.poi("gondola_rim_station", rx, ry + 1, rz)
    ctx.claim(cx, cz, r_out + 10)


# ==========================================================================
def ember_island(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    spot = find_flat(ctx, s.x, s.z, 180, 30, ctx.sea + 2, ctx.sea + 30, water_within=90)
    cx, cz, y = spot if spot else (s.x, s.z, ctx.ground_median(s.x, s.z, 10))
    wx, wz = water_direction(ctx, cx, cz, 160)
    face = facing_from_vector(wx, wz)
    # the beach: soften the shore toward the sea into sand
    R = 110
    n = 2 * R + 1
    x0, z0 = cx - R, cz - R
    dxy = np.arange(n)[:, None] - R, np.arange(n)[None, :] - R
    proj = dxy[0] * wx + dxy[1] * wz
    g = ctx.field(x0, z0, n, n)
    wat = ctx.field(x0, z0, n, n, "water") != NONE
    from scipy import ndimage
    dist_w = ndimage.distance_transform_edt(~wat)
    beach = (~wat) & (dist_w < 28) & (proj > 20)
    new_h = np.where(beach, np.minimum(g, ctx.sea + 1 + (dist_w / 7).astype(np.int32)), g)
    ctx.shape_terrain(x0, z0, new_h.astype(np.int32), beach, top="minecraft:sand", sub="minecraft:sandstone")
    ctx.integration.append("sand beach shaped along the shore facing the sea")
    ctx.poi("ember_island_beach", int(cx + wx * 70), ctx.sea + 2, int(cz + wz * 70), "3x05 The Beach")
    # Ember Island Players theatre
    tx, tz = int(cx - wz * 40), int(cz + wx * 40)
    ty = ctx.ground_median(tx, tz, 16)
    ctx.level_pad(tx, tz, 26, 36, ty, top=BLK)
    cv = Canvas(ctx.reg, (50, 50, 48))
    _fire_hall(cv, 5, 2, 4, 40, 30, stories=2, story_h=7, tiers=2)
    for k in range(6):  # portico of red pillars on the front
        cv.box(8 + k * 7, 3, 36, 8 + k * 7, 15, 36, "minecraft:red_concrete")
    cv.box(6, 16, 34, 44, 16, 38, FIRE.roof)
    kit.hip_roof(cv, 6, 34, 44, 38, 17, FIRE.roof_stairs, FIRE.roof, overhang=1, ridge=FIRE.ridge, max_levels=2)
    cv.box(8, 3, 6, 42, 5, 13, "minecraft:dark_oak_planks")  # stage
    cv.box(8, 6, 6, 42, 14, 6, "minecraft:red_wool")  # curtain
    for k in range(8):
        cv.box(9, 3 + k // 2, 16 + k * 2, 41, 3 + k // 2, 16 + k * 2,
               kit.stair(cv, "minecraft:dark_oak_stairs", "south"))
    cv.box(22, 3, 33, 28, 8, 34, AIR_S)
    pl = ctx.place(cv, tx, tz, ty - 2, face, anchor=(25, 0, 20))
    ctx.poi("ember_island_theater", *pl.to_world(25, 3, 20), "The Ember Island Players (3x17)")
    # the royal family's beach house
    bx, by_ = int(cx + wx * 10 + wz * 45), int(cz + wz * 10 - wx * 45)
    bgy = ctx.ground_median(bx, by_, 16)
    ctx.level_pad(bx, by_, 22, 32, bgy, top=BLK)
    cvb = Canvas(ctx.reg, (40, 36, 40))
    cvb.walls(0, 1, 0, 39, 4, 39, "minecraft:red_terracotta")
    cvb.box(17, 1, 39, 22, 4, 39, AIR_S)
    _fire_hall(cvb, 8, 0, 6, 24, 18, stories=2, story_h=6, tiers=2)
    cvb.box(8, 0, 27, 31, 0, 36, "minecraft:smooth_sandstone")
    pl2 = ctx.place(cvb, bx, by_, bgy, face, anchor=(20, 0, 20))
    ctx.poi("royal_beach_house", *pl2.to_world(20, 1, 15), "Fire Lord's family beach house")
    place_houses(ctx, cx, cz, 30, 95, 16, [FIRE_COMMON], stories=(1, 2, 1),
                 avoid=[(tx, tz, 40), (bx, by_, 34)], max_slope=7, tries=1500)
    ctx.poi("resort_town", cx, y + 1, cz)
    ctx.claim(cx, cz, 110)
