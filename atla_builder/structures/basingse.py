"""Ba Sing Se: Outer Wall, Agrarian Zone, Inner Wall, Lower/Middle/Upper Rings,
the Earth King's Palace, the monorail, and Lake Laogai's hidden Dai Li base."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from ..buffer import SOFT, Canvas
from ..noise import hash01
from ..palettes import EARTH, EARTH_POOR, EARTH_RURAL, Palette
from ..terrain import NONE
from . import kit
from .common import BuildContext, facing_from_vector

AIR_S = "minecraft:air"
WATER_S = "minecraft:water[level=0]"
WALL = "minecraft:stone_bricks"
WALL2 = "minecraft:cracked_stone_bricks"
WALL3 = "minecraft:mossy_stone_bricks"
CAP = "minecraft:polished_andesite"

MIDDLE = Palette(
    name="bss_middle", wall="minecraft:white_terracotta", wall_alt="minecraft:smooth_sandstone",
    trim="minecraft:stripped_dark_oak_log[axis=y]", post="minecraft:stripped_dark_oak_log[axis=y]",
    floor="minecraft:dark_oak_planks", foundation="minecraft:stone_bricks",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:prismarine_bricks",
    window="minecraft:dark_oak_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:dark_oak_planks", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:dark_oak_fence",
)
UPPER = Palette(
    name="bss_upper", wall="minecraft:smooth_quartz", wall_alt="minecraft:smooth_sandstone",
    trim="minecraft:stripped_spruce_log[axis=y]", post="minecraft:stripped_spruce_log[axis=y]",
    floor="minecraft:polished_andesite", foundation="minecraft:polished_andesite",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:gold_block",
    window="minecraft:spruce_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:spruce_planks", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:spruce_fence",
)


def _ellipse_d(dx, dz, rx, rz):
    """Approximate distance (blocks) outside an ellipse boundary (negative inside)."""
    r = np.sqrt((dx / rx) ** 2 + (dz / rz) ** 2)
    return (r - 1.0) * (rx + rz) / 2


def ba_sing_se(ctx: BuildContext) -> None:
    s = ctx.site
    B = ctx.struct
    T = ctx.terrain
    rng = ctx.rng
    cx, cz = s.x, s.z
    RX, RZ = 560, 500          # Outer Wall ellipse radii
    R_IN = 240                 # Inner Wall radius (city proper)
    rings = [                  # (name, radius, centre z-offset, terrace height)
        ("lower", R_IN, 0, 0),
        ("middle", 150, -40, 6),
        ("upper", 90, -70, 14),
        ("palace", 48, -88, 26),
    ]
    inner = ctx.field(cx - R_IN - 40, cz - R_IN - 40, 2 * R_IN + 81, 2 * R_IN + 81)
    y0 = int(np.percentile(inner, 45))
    ctx.site.notes["city_base_y"] = y0
    wall_top = y0 + 58
    inner_top = y0 + 38
    # ------------------------------------------------------------------
    # 1. city terraces inside the Inner Wall
    n = 2 * (R_IN + 40) + 1
    x0, z0 = cx - R_IN - 40, cz - R_IN - 40
    dx = np.arange(n)[:, None] - (R_IN + 40)
    dz = np.arange(n)[None, :] - (R_IN + 40)
    new_h = np.full((n, n), y0, np.int32)
    ring_id = np.full((n, n), -1, np.int32)
    for k, (name, r, oz, dh) in enumerate(rings):
        m = np.hypot(dx, dz - oz) <= r
        new_h = np.where(m, y0 + dh, new_h)
        ring_id = np.where(m, k, ring_id)
    city = ring_id >= 0
    tops = np.where(ring_id == 0, ctx.reg.id("minecraft:packed_mud"),
                    np.where(ring_id == 1, ctx.reg.id("minecraft:stone_bricks"),
                             ctx.reg.id("minecraft:polished_andesite"))).astype(np.uint16)
    ctx.shape_terrain(x0, z0, new_h, city, top=tops, sub=np.full((n, n), ctx.reg.id("minecraft:stone"), np.uint16))
    ctx.integration.append(f"city proper flattened into 4 terraces from y={y0} (Lower Ring) to y={y0 + 26} (palace)")
    # ------------------------------------------------------------------
    # 2. Agrarian Zone: clear, then fields & irrigation between the walls
    AR = max(RX, RZ) + 30
    ax0, az0 = cx - AR, cz - AR
    na = 2 * AR + 1
    adx = np.arange(na)[:, None] - AR
    adz = np.arange(na)[None, :] - AR
    ed = _ellipse_d(adx, adz, RX, RZ)
    rd = np.hypot(adx, adz)
    zone = (ed < -24) & (rd > R_IN + 16)
    g = ctx.field(ax0, az0, na, na)
    top = ctx.field(ax0, az0, na, na, "top")
    wat = ctx.field(ax0, az0, na, na, "water") != NONE
    slope = ndimage.maximum_filter(g, 3) - ndimage.minimum_filter(g, 3)
    farm = zone & ~wat & (slope <= 2)
    near_w = ndimage.binary_dilation(wat, iterations=3)
    clear = zone & ~wat & (top > g)
    T.fill_columns(ax0, az0, np.where(clear, g + 1, 0), np.where(clear, top + 1, 0), AIR_S)
    # plots 32x22 separated by paths; irrigation ditch down every plot's middle
    px = (adx + 10000) % 34
    pz = (adz + 10000) % 24
    path = (px < 2) | (pz < 2)
    ditch = (px == 17) & ~path
    plot_hash = hash01((adx + 10000) // 34, (adz + 10000) // 24, 3)
    crop = np.where(plot_hash < 0.55, ctx.reg.id("minecraft:wheat[age=7]"),
                    np.where(plot_hash < 0.75, ctx.reg.id("minecraft:carrots[age=7]"),
                             np.where(plot_hash < 0.9, ctx.reg.id("minecraft:potatoes[age=7]"), 0))).astype(np.uint16)
    fields = farm & ~path & ~ditch & ~near_w
    fl = ctx.reg.id("minecraft:farmland[moisture=7]")
    T.fill_columns(ax0, az0, np.where(fields & (crop > 0), g, 0), np.where(fields & (crop > 0), g + 1, 0), fl)
    T.fill_columns(ax0, az0, np.where(fields, g + 1, 0), np.where(fields, g + 2, 0),
                   np.where(fields, crop, 0).astype(np.uint16))
    T.fill_columns(ax0, az0, np.where(farm & ditch, g, 0), np.where(farm & ditch, g + 1, 0), WATER_S)
    T.fill_columns(ax0, az0, np.where(farm & path, g, 0), np.where(farm & path, g + 1, 0), "minecraft:dirt_path")
    ctx.integration.append("Agrarian Zone cleared and planted: 34x24 plots, irrigation ditches, farm tracks")
    # farm hamlets across the zone
    placed = 0
    for k in range(600):
        if placed >= 70:
            break
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.55, 0.92)
        hx, hz = int(cx + RX * r * math.cos(a)), int(cz + RZ * r * math.sin(a))
        if math.hypot(hx - cx, hz - cz) < R_IN + 40:
            continue
        gg = ctx.field(hx - 6, hz - 6, 13, 13)
        if ctx.water_frac(hx, hz, 7) > 0 or gg.max() - gg.min() > 3:
            continue
        hy = int(np.median(gg))
        T.box(hx - 7, hy, hz - 7, hx + 7, hy, hz + 7, "minecraft:coarse_dirt")
        T.box(hx - 7, hy + 1, hz - 7, hx + 7, hy + 2, hz + 7, AIR_S)
        cv = kit.house_canvas(ctx.reg, 9, 7, EARTH_RURAL, roof="thatch")
        ctx.place(cv, hx, hz, hy, ["north", "south", "east", "west"][k % 4], foundation="minecraft:cobblestone")
        placed += 1
    ctx.poi("agrarian_zone", int(cx + RX * 0.75), y0 + 1, cz, "Farmland between the Outer and Inner Walls")
    # ------------------------------------------------------------------
    # 3. The Outer Wall (with towers, gates and river culverts)
    wall_band = (ed >= -10) & (ed <= 10)
    gates = {}
    for name, (ux, uz) in {"south": (0, 1), "north": (0, -1), "east": (1, 0), "west": (-1, 0)}.items():
        gx, gz = int(cx + ux * RX), int(cz + uz * RZ)
        gates[name] = (gx, gz)
    gate_cut = np.zeros_like(wall_band)
    for (gx, gz) in gates.values():
        gate_cut |= np.hypot(adx + cx - gx, adz + cz - gz) <= 14
    gfloor = np.where(wat, ctx.field(ax0, az0, na, na, "ground"), g)
    lo = np.where(wall_band, gfloor - 3, 0)
    hi = np.where(wall_band, wall_top + 1, 0)
    wall_ids = np.where(hash01(adx, adz, 9) < 0.12, ctx.reg.id(WALL2),
                        np.where(hash01(adx, adz, 10) < 0.06, ctx.reg.id(WALL3), ctx.reg.id(WALL))).astype(np.uint16)
    B.fill_columns(ax0, az0, lo, hi, np.where(wall_band, wall_ids, 0).astype(np.uint16))
    # walkway, parapets, crenellations
    walk = (ed >= -8) & (ed <= 8)
    B.fill_columns(ax0, az0, np.where(walk, wall_top, 0), np.where(walk, wall_top + 1, 0), CAP)
    para = wall_band & ~walk
    cren = para & (((adx + adz) // 3) % 2 == 0)
    B.fill_columns(ax0, az0, np.where(para, wall_top + 1, 0), np.where(para, wall_top + 2, 0), WALL)
    B.fill_columns(ax0, az0, np.where(cren, wall_top + 2, 0), np.where(cren, wall_top + 3, 0), WALL)
    # culverts where rivers cross the wall
    cul = wall_band & wat
    wl = ctx.field(ax0, az0, na, na, "water")
    B.fill_columns(ax0, az0, np.where(cul, gfloor + 1, 0), np.where(cul, wl + 1, 0), WATER_S)
    B.fill_columns(ax0, az0, np.where(cul, wl + 1, 0), np.where(cul, wl + 4, 0), AIR_S)
    # gates: tall arched openings with the green-roofed gatehouse above
    for name, (gx, gz) in gates.items():
        gy = ctx.ground_median(gx, gz, 10)
        horiz = name in ("north", "south")
        if horiz:
            B.box(gx - 7, gy + 1, gz - 12, gx + 7, gy + 22, gz + 12, AIR_S)
            B.box(gx - 11, wall_top + 1, gz - 13, gx + 11, wall_top + 12, gz + 13, WALL)
            B.box(gx - 10, wall_top + 3, gz - 12, gx + 10, wall_top + 11, gz + 12, AIR_S)
            kit.hip_roof(B, gx - 11, gz - 13, gx + 11, gz + 13, wall_top + 13, EARTH.roof_stairs, EARTH.roof,
                         overhang=2, ridge=EARTH.ridge)
        else:
            B.box(gx - 12, gy + 1, gz - 7, gx + 12, gy + 22, gz + 7, AIR_S)
            B.box(gx - 13, wall_top + 1, gz - 11, gx + 13, wall_top + 12, gz + 11, WALL)
            B.box(gx - 12, wall_top + 3, gz - 10, gx + 12, wall_top + 11, gz + 10, AIR_S)
            kit.hip_roof(B, gx - 13, gz - 11, gx + 13, gz + 11, wall_top + 13, EARTH.roof_stairs, EARTH.roof,
                         overhang=2, ridge=EARTH.ridge)
        B.box(gx - 1, gy, gz - 1, gx + 1, gy, gz + 1, "minecraft:stone_bricks")
        ctx.poi(f"outer_wall_{name}_gate", gx, gy + 1, gz, "Outer Wall gate")
    # towers every ~150 blocks along the perimeter
    per = int(2 * math.pi * math.sqrt((RX ** 2 + RZ ** 2) / 2))
    for k in range(per // 150):
        a = 2 * math.pi * k / (per // 150) + 0.2
        tx, tz = int(cx + RX * math.cos(a)), int(cz + RZ * math.sin(a))
        tg = ctx.ground_median(tx, tz, 6)
        B.box(tx - 11, tg - 3, tz - 11, tx + 11, wall_top + 12, tz + 11, WALL)
        B.box(tx - 10, wall_top + 1, tz - 10, tx + 10, wall_top + 11, tz + 10, AIR_S)
        for (ox, oz) in ((-10, 0), (10, 0), (0, -10), (0, 10)):
            B.box(tx + ox, wall_top + 4, tz + oz, tx + ox, wall_top + 7, tz + oz, AIR_S)
        kit.hip_roof(B, tx - 11, tz - 11, tx + 11, tz + 11, wall_top + 13, EARTH.roof_stairs, EARTH.roof,
                     overhang=2, ridge=EARTH.ridge)
    sx, sz = gates["south"]
    ctx.poi("drill_breach_site", sx + 60, ctx.ground(sx + 60, sz), sz, "Where the Fire Nation drill struck (2x13)")
    ctx.integration.append(f"Outer Wall: ellipse {2 * RX}x{2 * RZ}, top y={wall_top}, culverts over rivers")
    # ------------------------------------------------------------------
    # 4. Inner Wall and ring walls
    def ring_wall(r, oz, top_y, thick, name):
        W = int(r + thick + 2)
        rx0, rz0 = cx - W, cz + oz - W
        nn = 2 * W + 1
        ddx = np.arange(nn)[:, None] - W
        ddz = np.arange(nn)[None, :] - W
        dd = np.hypot(ddx, ddz)
        band = (dd >= r - thick / 2) & (dd <= r + thick / 2)
        gg = ctx.field(rx0, rz0, nn, nn)
        B.fill_columns(rx0, rz0, np.where(band, gg - 2, 0), np.where(band, top_y + 1, 0), WALL)
        edge = band & ((dd > r + thick / 2 - 1) | (dd < r - thick / 2 + 1))
        cren = edge & (((ddx + ddz) // 2) % 2 == 0)
        B.fill_columns(rx0, rz0, np.where(edge, top_y + 1, 0), np.where(edge, top_y + 2, 0), WALL)
        B.fill_columns(rx0, rz0, np.where(cren, top_y + 2, 0), np.where(cren, top_y + 3, 0), WALL)
        # four gates
        for (ux, uz) in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            gx, gz = int(cx + ux * r), int(cz + oz + uz * r)
            gy = ctx.ground(gx + ux * (thick + 3), gz + uz * (thick + 3))
            if ux:
                B.box(gx - thick, gy + 1, gz - 4, gx + thick, gy + 9, gz + 4, AIR_S)
            else:
                B.box(gx - 4, gy + 1, gz - thick, gx + 4, gy + 9, gz + thick, AIR_S)
        ctx.poi(f"{name}_wall_gate", cx, ctx.ground(cx, cz + oz + r + thick + 3) + 1, cz + oz + r + thick + 3)

    ring_wall(R_IN, 0, inner_top, 12, "inner")
    ring_wall(150, -40, y0 + 6 + 20, 6, "middle_ring")
    ring_wall(90, -70, y0 + 14 + 18, 6, "upper_ring")
    # stairs bridging each terrace step at the gates (south side of each ring)
    for (name, r, oz, dh), (_, _r2, _oz2, dh_in) in zip(rings[:-1], rings[1:]):
        r_in, oz_in = _r2, _oz2
        gx, gz = cx, cz + oz_in + r_in
        for i in range(dh_in - dh + 1):
            B.box(gx - 3, y0 + dh + i, gz + 8 - i, gx + 3, y0 + dh + i, gz + 8 - i,
                  kit.stair(B, "minecraft:stone_brick_stairs", "north"))
            B.box(gx - 3, y0 + dh, gz + 8 - i, gx + 3, y0 + dh + i - 1, gz + 8 - i, "minecraft:stone_bricks")
            B.box(gx - 3, y0 + dh + i + 1, gz + 8 - i, gx + 3, y0 + dh + i + 5, gz + 8 - i, AIR_S)
        B.box(gx - 3, y0 + dh_in, gz - 8, gx + 3, y0 + dh_in, gz + 8 - (dh_in - dh), "minecraft:stone_bricks")
        B.box(gx - 3, y0 + dh_in + 1, gz - 8, gx + 3, y0 + dh_in + 7, gz + 8 - (dh_in - dh), AIR_S)
    # ------------------------------------------------------------------
    # 5. districts: dense Lower Ring, Middle Ring (incl. the University), Upper Ring
    occ = np.zeros((n, n), bool)
    # main avenues (south-north spine & east-west) kept open
    occ |= (np.abs(dx) <= 5) | (np.abs(dz) <= 4)
    for k, (name, r, oz, dh) in enumerate(rings):
        dd = np.hypot(dx, dz - oz)
        occ |= (np.abs(dd - r) <= 10)  # clear strips along every ring wall
    district = {0: (EARTH_POOR, ((6, 5), (7, 6), (8, 6)), (1, 1, 2), 11),
                1: (MIDDLE, ((8, 7), (10, 8), (11, 9)), (2, 2, 1), 12),
                2: (UPPER, ((12, 10), (14, 11), (11, 11)), (2, 2, 3), 16)}
    # Ba Sing Se University in the Middle Ring (west)
    ux_, uz_ = cx - 105, cz - 40
    cv = kit.house_canvas(ctx.reg, 31, 21, MIDDLE, stories=3, story_h=5)
    ctx.place(cv, ux_, uz_, y0 + 6, "east", foundation="minecraft:stone_bricks")
    occ[max(0, ux_ - x0 - 22):ux_ - x0 + 22, max(0, uz_ - z0 - 18):uz_ - z0 + 18] = True
    ctx.poi("ba_sing_se_university", ux_, y0 + 7, uz_, "Professor Zei's university")
    # Jasmine Dragon tea shop (Upper Ring, east of the palace terrace)
    jx, jz = cx + 62, cz - 70
    cvj = kit.house_canvas(ctx.reg, 13, 10, UPPER, stories=2)
    ctx.place(cvj, jx, jz, y0 + 14, "west", foundation="minecraft:polished_andesite")
    occ[jx - x0 - 12:jx - x0 + 12, jz - z0 - 12:jz - z0 + 12] = True
    ctx.poi("jasmine_dragon", jx, y0 + 15, jz, "Iroh's tea shop (Upper Ring)")
    # Iroh & Zuko's apartment / Pao's tea shop in the Lower Ring
    ctx.poi("lower_ring_tea_shop", cx + 170, y0 + 1, cz + 60, "Pao's tea shop; Zuko & Iroh's apartment")
    count = 0
    for k, (pal, sizes, stories, step) in district.items():
        for gi in range(6, n - 6, step):
            for gj in range(6, n - 6, step):
                if ring_id[gi, gj] != k:
                    continue
                if rng.random() < 0.06:
                    continue
                si = int(rng.integers(0, len(sizes)))
                w, d = sizes[si]
                bx, bz = gi + int(rng.integers(-1, 2)), gj + int(rng.integers(-1, 2))
                ox0, oz0 = bx - w // 2 - 2, bz - d // 2 - 2
                if ox0 < 0 or oz0 < 0 or ox0 + w + 4 >= n or oz0 + d + 4 >= n:
                    continue
                if occ[ox0:ox0 + w + 4, oz0:oz0 + d + 4].any() or (ring_id[ox0:ox0 + w + 4, oz0:oz0 + d + 4] != k).any():
                    continue
                occ[ox0:ox0 + w + 4, oz0:oz0 + d + 4] = True
                face = ["north", "south", "east", "west"][int(rng.integers(0, 4))]
                cv = kit.house_canvas(ctx.reg, w, d, pal, stories=stories[si])
                ctx.place(cv, bx + x0, bz + z0, y0 + rings[k][3], face, connect=False)
                count += 1
                if k == 2 and rng.random() < 0.35:  # Upper Ring garden trees
                    kit.tree(B, bx + x0 + w // 2 + 3, y0 + rings[k][3] + 1, bz + z0, "cherry", 5, rng=rng)
    ctx.notes.append(f"{count} city buildings across the Lower/Middle/Upper Rings")
    # ------------------------------------------------------------------
    # 6. The Earth King's palace on its plateau
    pz_ = cz - 88
    py = y0 + 26
    B.box(cx - 44, py - 12, pz_ - 36, cx + 44, py, pz_ + 36, "minecraft:polished_andesite", mode=SOFT)
    cvp = Canvas(ctx.reg, (80, 60, 64))
    kit.house(cvp, 14, 1, 14, 52, 30, UPPER, stories=3, story_h=6, overhang=3)
    kit.hip_roof(cvp, 22, 20, 57, 37, 27, UPPER.roof_stairs, UPPER.roof, overhang=3, ridge=UPPER.ridge, max_levels=3)
    kit.hip_roof(cvp, 30, 24, 49, 33, 33, UPPER.roof_stairs, UPPER.roof, overhang=3, ridge=UPPER.ridge)
    for sx_ in (4, 70):  # side pavilions
        kit.house(cvp, sx_, 1, 22, 8, 16, UPPER, stories=2, story_h=5)
    for k in range(10):  # grand staircase down to the Upper Ring (front = +z)
        cvp.box(30, 0 - 0, 45 + k, 49, 0, 45 + k, "minecraft:polished_andesite")
    cvp.box(12, 0, 46, 67, 0, 62, "minecraft:polished_andesite")
    for (u, v) in ((20, 50), (59, 50), (20, 58), (59, 58)):
        kit.lantern_post(cvp, u, 1, v, "minecraft:stone_brick_wall", 4)
    pl = ctx.place(cvp, cx, pz_, py, "south", anchor=(40, 0, 32))
    ctx.poi("earth_kings_palace", *pl.to_world(40, 2, 44), "Throne room of Earth King Kuei (and Bosco)")
    ctx.poi("palace_courtyard", *pl.to_world(40, 1, 54))
    # ------------------------------------------------------------------
    # 7. Monorail: elevated viaducts from the outer gates to the inner wall gates
    rail_y = y0 + 24
    for name, (gx, gz) in gates.items():
        ux, uz = (gx - cx), (gz - cz)
        L = math.hypot(ux, uz)
        ux, uz = ux / L, uz / L
        start, end = R_IN + 8, L - 16
        for t in np.arange(start, end, 1.0):
            x, z = int(round(cx + ux * t)), int(round(cz + uz * t))
            B.box(x - 2, rail_y, z - 2, x + 2, rail_y, z + 2, "minecraft:polished_andesite")
            B.set(x, rail_y + 1, z, "minecraft:smooth_stone_slab[type=bottom,waterlogged=false]")
            if int(t) % 14 == 0:
                gy = ctx.ground(x, z)
                B.box(x - 1, gy - 2, z - 1, x + 1, rail_y - 1, z + 1, WALL)
        sx_, sz_ = int(cx + ux * (end - 6)), int(cz + uz * (end - 6))
        cvs = kit.house_canvas(ctx.reg, 13, 9, EARTH, stories=1)
        ctx.place(cvs, sx_, sz_, rail_y, facing_from_vector(-ux, -uz), connect=False)
        ctx.poi(f"monorail_station_{name}", sx_, rail_y + 1, sz_, "Monorail across the Agrarian Zone")
    # ------------------------------------------------------------------
    # 8. Lake Laogai and the Dai Li base beneath it
    lx, lz = _find_lake(ctx, cx, cz, R_IN + 60, max(RX, RZ) - 40)
    if lx is None:
        a = math.radians(40)
        lx, lz = int(cx + 380 * math.cos(a)), int(cz + 330 * math.sin(a))
        ly = ctx.ground_median(lx, lz, 20)
        B.ellipsoid(lx, ly, lz, 48, 8, 32, WATER_S, lower=True, upper=False)
        B.ellipsoid(lx, ly + 1, lz, 48, 8, 32, AIR_S, lower=False)
        surface = ly
        ctx.notes.append("Lake Laogai created (no natural lake inside the walls)")
    else:
        surface = int(ctx.field(lx, lz, 1, 1, "water")[0, 0])
        ctx.notes.append("Lake Laogai uses the natural lake inside the Agrarian Zone")
    bottom = min(ctx.ground(lx, lz), surface - 4)
    by = bottom - 30
    B.box(lx - 30, by - 2, lz - 22, lx + 30, by + 14, lz + 22, "minecraft:stone_bricks")
    B.box(lx - 22, by, lz - 14, lx + 22, by + 9, lz + 14, AIR_S)                   # Dai Li HQ hall
    B.box(lx - 22, by - 1, lz - 14, lx + 22, by - 1, lz + 14, "minecraft:polished_deepslate")
    for k in range(-20, 21, 4):
        B.box(lx + k, by, lz - 14, lx + k, by + 9, lz - 14, "minecraft:polished_andesite")
    B.box(lx - 28, by, lz - 3, lx - 23, by + 4, lz + 3, AIR_S)                     # corridor west
    for k in range(6):                                                              # prison cells
        B.box(lx + 23, by, lz - 20 + k * 7, lx + 29, by + 4, lz - 15 + k * 7, AIR_S)
        B.box(lx + 23, by, lz - 20 + k * 7, lx + 23, by + 4, lz - 15 + k * 7, "minecraft:iron_bars")
    ctx.poi("dai_li_headquarters", lx, by, lz, "Long Feng's Dai Li base under Lake Laogai (2x17)")
    ctx.poi("laogai_prison_cells", lx + 26, by, lz)
    # brainwashing chamber: round dark room with the spinning lamp
    bx, bz = lx - 12, lz + 6
    B.cyl(bx, bz, by, by + 7, 6, AIR_S)
    B.cyl(bx, bz, by - 1, by - 1, 6.5, "minecraft:black_concrete")
    B.cyl(bx, bz, by, by + 7, 7, "minecraft:black_concrete", hollow=True, thickness=1, mode=SOFT)
    B.box(bx, by + 5, bz, bx, by + 7, bz, "minecraft:chain[axis=y,waterlogged=false]")
    B.set(bx, by + 4, bz, "minecraft:lantern[hanging=true,waterlogged=false]")
    B.set(bx, by, bz + 3, "minecraft:dark_oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]")
    ctx.poi("brainwashing_chamber", bx, by, bz, "Where Jet was brainwashed")
    # hidden entrance: shoreline platform with a stair shaft down to the base
    shore = _shore_point(ctx, lx, lz, surface)
    sx2, sz2 = shore
    B.box(sx2 - 2, surface, sz2 - 2, sx2 + 2, surface, sz2 + 2, "minecraft:stone_brick_slab[type=top,waterlogged=false]")
    top_y = surface - 1
    y = top_y
    k = 0
    while y > by + 1:
        a = k * 0.5
        x = int(round(sx2 + 2 * math.cos(a)))
        z = int(round(sz2 + 2 * math.sin(a)))
        B.set(x, y, z, "minecraft:stone_bricks")
        B.box(x, y + 1, z, x, y + 3, z, AIR_S)
        y -= 1
        k += 1
    # tunnel from the shaft to the headquarters
    B.line((sx2, by + 1, sz2), (lx - 28, by + 1, lz), AIR_S, width=3)
    B.line((sx2, by, sz2), (lx - 28, by, lz), "minecraft:stone_bricks", width=3)
    ctx.poi("lake_laogai_entrance", sx2, surface + 1, sz2, "Hidden hatch on the lakeshore")
    ctx.poi("lake_laogai", lx, surface, lz)
    # ------------------------------------------------------------------
    ctx.poi("lower_ring", cx, y0 + 1, cz + 190, "Lower Ring (refugees, Zuko & Iroh)")
    ctx.poi("middle_ring", cx - 60, y0 + 7, cz - 40)
    ctx.poi("upper_ring", cx + 40, y0 + 15, cz - 70)
    ctx.claim(cx, cz, max(RX, RZ) + 20)
    ctx.scale = 1.0


def _find_lake(ctx, cx, cz, rmin, rmax):
    R = int(rmax)
    w = ctx.field(cx - R, cz - R, 2 * R + 1, 2 * R + 1, "water") != NONE
    lab, n = ndimage.label(w)
    best = None
    for i in range(1, n + 1):
        m = lab == i
        cnt = int(m.sum())
        if cnt < 1500:
            continue
        xs, zs = np.nonzero(m)
        mx, mz = xs.mean() - R, zs.mean() - R
        d = math.hypot(mx, mz)
        # compact lakes (not rivers): area vs bounding box
        span = (xs.max() - xs.min() + 1) * (zs.max() - zs.min() + 1)
        if rmin < d < rmax and cnt / span > 0.35:
            if best is None or cnt > best[0]:
                best = (cnt, int(cx + mx), int(cz + mz))
    if best is None:
        return None, None
    return best[1], best[2]


def _shore_point(ctx, lx, lz, surface):
    for r in range(4, 200, 2):
        for k in range(24):
            a = 2 * math.pi * k / 24
            x, z = int(lx + r * math.cos(a)), int(lz + r * math.sin(a))
            if not ctx.is_water(x, z):
                return x, z
    return lx, lz
