"""Water Tribe landmarks: Southern Water Tribe village, Agna Qel'a + Spirit Oasis."""
from __future__ import annotations

import math

import numpy as np

from ..buffer import SET, Canvas
from . import kit
from .common import (BuildContext, facing_of, local_field, shape_local, unit,
                     water_direction)

SNOW = "minecraft:snow_block"
PICE = "minecraft:packed_ice"
BICE = "minecraft:blue_ice"
WATER_S = "minecraft:water[level=0]"
AIR = "minecraft:air"


# ==========================================================================
# Southern Water Tribe (Book 1 era: a small snow-walled village)
# ==========================================================================
def southern_water_tribe(ctx: BuildContext) -> None:
    s = ctx.site
    dx, dz = water_direction(ctx, s.x, s.z, 160)
    facing = facing_of(dx, dz)
    fx, fz = unit(facing)
    # village centre sits a little inland from the shore
    cx, cz = int(s.x - fx * 40), int(s.z - fz * 40)
    y = int(np.clip(ctx.ground_median(cx, cz, 25), ctx.sea + 2, ctx.sea + 7))
    R = 46
    size = 2 * R + 60
    ax = az = size // 2
    # --- terrain: a level snow shelf, blending to the natural ice; the sea side
    #     slopes down to a beach where the dock starts
    lx = np.arange(size)[:, None] - ax
    lz = np.arange(size)[None, :] - az
    d = np.hypot(lx, lz)
    nat = local_field(ctx, cx, cz, facing, size, size, (ax, az))
    t = np.clip((d - (R + 6)) / 22.0, 0, 1)
    t = t * t * (3 - 2 * t)
    new_h = np.rint(y * (1 - t) + nat * t).astype(np.int32)
    shore = (lz > R) & (np.abs(lx) < 9)
    new_h = np.where(shore, np.minimum(new_h, ctx.sea + 1), new_h)
    mask = d < R + 28
    shape_local(ctx, cx, cz, facing, new_h, mask, (ax, az), top=SNOW, sub=PICE)
    ctx.integration.append("snow shelf levelled at y=%d, blended over 22 blocks; beach cut to the dock" % y)

    c = Canvas(ctx.reg, (size, 30, size))
    b = 2  # canvas y for world y
    # --- snow wall with gate toward the sea, Sokka's watchtower beside it
    ring = (d >= R - 1.5) & (d <= R + 1.5)
    gate = (lz > 0) & (np.abs(lx) <= 3)
    c.column_mask(0, 0, ring & ~gate, b + 1, b + 5, SNOW)
    c.column_mask(0, 0, (d >= R - 1.5) & (d <= R - 0.5) & ~gate, b + 6, b + 6, SNOW)
    for k in range(0, 360, 9):  # crenels
        a = math.radians(k)
        px, pz = int(round(ax + (R + 1) * math.cos(a))), int(round(az + (R + 1) * math.sin(a)))
        if not (pz - az > 0 and abs(px - ax) <= 4):
            c.box(px, b + 6, pz, px, b + 6, pz, SNOW)
    tx, tz = ax + 8, az + R - 3
    c.cyl(tx, tz, b + 1, b + 15, 3.2, SNOW)
    c.cyl(tx, tz, b + 1, b + 15, 2.0, AIR)
    c.cyl(tx, tz, b + 16, b + 16, 4.4, PICE)
    c.cyl(tx, tz, b + 17, b + 18, 4.4, SNOW, hollow=True, thickness=1.0)
    for i in range(1, 16):  # ladder of spruce trapdoor rungs
        c.set(tx, b + i, tz - 1, "minecraft:ladder[facing=south,waterlogged=false]")
    c.box(tx + 3, b + 17, tz, tx + 3, b + 22, tz, "minecraft:spruce_fence")
    c.box(tx + 4, b + 20, tz, tx + 6, b + 22, tz, "minecraft:blue_wool")
    ctx_pois = {"watchtower": (tx, b + 17, tz), "village_gate": (ax, b + 1, az + R)}
    # --- central plaza, fire pit, drying racks
    c.cyl(ax, az, b, b, 9, PICE)
    c.cyl(ax, az, b, b, 2, "minecraft:magma_block")
    c.cyl(ax, az, b + 1, b + 1, 2.5, "minecraft:cobblestone_wall", hollow=True, thickness=1)
    for k in range(4):
        a = math.radians(45 + k * 90)
        rx, rz = int(ax + 12 * math.cos(a)), int(az + 12 * math.sin(a))
        c.box(rx - 2, b + 1, rz, rx + 2, b + 1, rz, AIR)
        c.set(rx - 2, b + 1, rz, "minecraft:spruce_fence")
        c.set(rx + 2, b + 1, rz, "minecraft:spruce_fence")
        c.box(rx - 2, b + 2, rz, rx + 2, b + 2, rz, "minecraft:spruce_fence")
    # --- homes: snow igloos and hide tents facing the plaza
    rng = ctx.rng
    placed: list[tuple[int, int, int]] = [(ax, az, 11), (tx, tz, 6)]
    gran = (ax - 18, az - 6)
    kit.igloo(c, gran[0], b + 1, gran[1], 6, door="east")
    placed.append((gran[0], gran[1], 9))
    ctx_pois["gran_gran_igloo"] = (gran[0], b + 1, gran[1])
    homes = 0
    tries = 0
    while homes < 17 and tries < 600:
        tries += 1
        ang = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(15, R - 8)
        hx, hz = int(ax + rr * math.cos(ang)), int(az + rr * math.sin(ang))
        rad = int(rng.integers(3, 6))
        if hz - az > R - 14 and abs(hx - ax) < 12:
            continue
        if any((hx - px) ** 2 + (hz - pz) ** 2 < (rad + pr + 3) ** 2 for px, pz, pr in placed):
            continue
        door = facing_of(ax - hx, az - hz)
        if homes % 3 == 2:
            kit.hide_tent(c, hx, b + 1, hz, rad, rad + 4,
                          hide="minecraft:brown_wool" if homes % 2 else "minecraft:white_wool")
        else:
            kit.igloo(c, hx, b + 1, hz, rad, door=door)
        placed.append((hx, hz, rad))
        homes += 1
    # --- dock and canoes on the sea side
    for k in range(R + 3, R + 30):
        c.box(ax - 1, b, az + k, ax + 1, b, az + k, "minecraft:spruce_planks")
        if k % 4 == 0:
            c.box(ax - 2, b - 3, az + k, ax - 2, b, az + k, "minecraft:spruce_fence")
            c.box(ax + 2, b - 3, az + k, ax + 2, b, az + k, "minecraft:spruce_fence")
    for i, off in enumerate((-8, 6, 12)):
        kx, kz = ax + off, az + R + 10 + i * 6
        c.box(kx - 1, b - 1, kz - 4, kx + 1, b - 1, kz + 4, "minecraft:spruce_planks")
        c.box(kx - 1, b, kz - 4, kx + 1, b, kz + 4, "minecraft:spruce_slab[type=bottom,waterlogged=true]")
        c.box(kx, b, kz - 3, kx, b, kz + 3, "minecraft:water[level=0]")
    ctx_pois["dock"] = (ax, b + 1, az + R + 28)
    pl = ctx.place(c, cx, cz, y - b, facing, anchor=(ax, 0, az))
    for name, (px, py, pz) in ctx_pois.items():
        ctx.poi(name, *pl.to_world(px, py, pz))
    ctx.poi("village_center", cx, y + 1, cz, "Plaza fire pit; story start (Book 1, ch.1)")
    # --- Aang's iceberg out to sea
    bx, bz = int(cx + fx * 190), int(cz + fz * 190)
    if ctx.is_water(bx, bz):
        ctx.struct.ellipsoid(bx, ctx.sea, bz, 16, 12, 12, PICE)
        ctx.struct.ellipsoid(bx + 3, ctx.sea + 4, bz - 2, 8, 8, 7, BICE)
        ctx.struct.ellipsoid(bx, ctx.sea + 4, bz, 3, 3, 3, "minecraft:light_blue_stained_glass")
        ctx.poi("aang_iceberg", bx, ctx.sea + 4, bz, "Aang & Appa frozen for 100 years")
    ctx.claim(cx, cz, R + 20)
    ctx.notes.append("Book 1 appearance: snow wall, watchtower, igloos & hide tents; Aang's iceberg offshore.")


# ==========================================================================
# Northern Water Tribe: Agna Qel'a, the canal city, and the Spirit Oasis
# ==========================================================================
def northern_water_tribe(ctx: BuildContext) -> None:
    s = ctx.site
    dx, dz = water_direction(ctx, s.x, s.z, 260)
    facing = facing_of(dx, dz)
    fx, fz = unit(facing)
    R = 185  # city radius (semi-circle opening onto the harbour)
    cx, cz = int(s.x - fx * 70), int(s.z - fz * 70)
    W = L = 2 * R + 40
    ax = az = W // 2
    y0 = ctx.sea + 3
    lx = np.arange(W)[:, None] - ax
    lz = np.arange(L)[None, :] - az
    d = np.hypot(lx, lz)
    front = 118  # waterfront / great wall line (local +z toward harbour)
    city = (d <= R) & (lz <= front)
    # tiers rise toward the palace plateau at the centre
    tier = np.clip(((R - d) // 42).astype(int), 0, 3)
    new_h = y0 + tier * 7
    new_h = np.where(d < 46, y0 + 30, new_h)
    nat = local_field(ctx, cx, cz, facing, W, L, (ax, az))
    blend = (d > R) & (d < R + 18) & (lz <= front)
    t = np.clip((d - R) / 18.0, 0, 1)
    bh = np.rint((y0) * (1 - t) + nat * t).astype(np.int32)
    H = np.where(city, new_h, np.where(blend, bh, nat))
    shape_local(ctx, cx, cz, facing, H.astype(np.int32), city | blend, (ax, az), top=SNOW, sub=PICE)
    ctx.integration.append("ice shelf terraced into 4 tiers + palace plateau; city front raised out of the bay")

    base = ctx.sea - 6  # world y of canvas y=0
    c = Canvas(ctx.reg, (W, 110, L))
    Y = lambda wy: wy - base  # noqa: E731
    # --- canals: one ring and five radial canals, water at sea level
    ring = (np.abs(d - 128) < 3) & city
    radial = np.zeros_like(city)
    for ang in (-60, -30, 0, 30, 60):
        a = math.radians(90 + ang)
        ux, uz = math.cos(a), math.sin(a)
        proj = lx * ux + lz * uz
        perp = np.abs(-lx * uz + lz * ux)
        radial |= (perp < 3) & (proj > 50) & (proj < 200)
    canals = (ring | radial) & (lz <= front + 2) & (d > 50)
    top_h = H - base
    for i, j in zip(*np.nonzero(canals)):
        c.box(i, Y(ctx.sea - 3), j, i, Y(ctx.sea), j, WATER_S)
        c.box(i, Y(ctx.sea) + 1, j, i, int(top_h[i, j]) + 2, j, AIR)
    edge = np.zeros_like(canals)
    edge[1:-1, 1:-1] = canals[1:-1, 1:-1] & ~(canals[2:, 1:-1] & canals[:-2, 1:-1] & canals[1:-1, 2:] & canals[1:-1, :-2])
    for i, j in zip(*np.nonzero(edge)):
        c.set(i, Y(ctx.sea) + 1, j, BICE)
    # --- buildings: rounded-roof ice houses on a jittered grid
    occ = canals.copy() | (d < 58) | (lz > front - 14) | ~city
    rng = ctx.rng
    step = 15
    for gi in range(8, W - 8, step):
        for gj in range(8, L - 8, step):
            bx = gi + int(rng.integers(-3, 4))
            bz = gj + int(rng.integers(-3, 4))
            w = int(rng.integers(7, 12))
            dd = int(rng.integers(7, 12))
            x0, z0 = bx - w // 2, bz - dd // 2
            if x0 < 1 or z0 < 1 or x0 + w >= W - 1 or z0 + dd >= L - 1:
                continue
            if occ[x0 - 1:x0 + w + 1, z0 - 1:z0 + dd + 1].any():
                continue
            gy = int(top_h[bx, bz])
            hh = int(rng.integers(5, 11)) + (4 if d[bx, bz] < 100 else 0)
            _ice_house(c, x0, gy + 1, z0, w, dd, hh, rng)
            occ[x0 - 2:x0 + w + 2, z0 - 2:z0 + dd + 2] = True
    # arched ice bridges over the ring canal
    for ang in range(-80, 81, 20):
        a = math.radians(90 + ang)
        ux, uz = math.cos(a), math.sin(a)
        p0 = (ax + ux * 123, az + uz * 123)
        p1 = (ax + ux * 133, az + uz * 133)
        if p1[1] - az > front:
            continue
        gy = int(top_h[int(p0[0]), int(p0[1])])
        kit.bridge(c, int(p0[0]), int(p0[1]), int(p1[0]), int(p1[1]), gy + 1, 3, PICE,
                   "minecraft:snow_block", arch=2)
    # --- the great ice wall along the harbour front with the water gate
    wall_top = Y(y0 + 44)
    F = az + front  # canvas z of the waterfront line
    for i in range(W):
        lat = i - ax
        if abs(lat) > math.sqrt(max(R * R - front * front, 0)) + 12:
            continue
        for j in range(F - 4, F + 6):
            c.box(i, Y(ctx.sea - 8), j, i, wall_top, j, PICE)
        c.box(i, wall_top + 1, F - 4, i, wall_top + 1, F - 4, SNOW)
        c.box(i, wall_top + 1, F + 5, i, wall_top + 1, F + 5, SNOW if i % 3 else AIR)
        if lat % 22 == 0:  # buttress columns carved in the wall face
            c.box(i - 2, Y(ctx.sea - 4), F + 6, i + 2, wall_top - 2, F + 8, BICE)
            c.box(i - 1, wall_top - 1, F + 6, i + 1, wall_top + 4, F + 7, SNOW)
    # water gate: canal passage through the wall + gate leaves
    c.box(ax - 5, Y(ctx.sea - 3), F - 5, ax + 5, Y(ctx.sea), F + 9, WATER_S)
    c.box(ax - 5, Y(ctx.sea) + 1, F - 5, ax + 5, Y(ctx.sea) + 16, F + 9, AIR)
    c.box(ax - 7, Y(ctx.sea) + 17, F + 6, ax + 7, Y(ctx.sea) + 19, F + 8, BICE)
    c.box(ax - 5, Y(ctx.sea) + 1, F + 1, ax - 3, Y(ctx.sea) + 15, F + 1, BICE)
    c.box(ax + 3, Y(ctx.sea) + 1, F + 1, ax + 5, Y(ctx.sea) + 15, F + 1, BICE)
    # --- Chief Arnook's palace on the plateau
    py = Y(y0 + 30)
    for k in range(4):
        hw, hd = 34 - k * 6, 28 - k * 5
        c.box(ax - hw, py + k * 5, az - hd, ax + hw, py + k * 5 + 4, az + hd, SNOW if k % 2 == 0 else PICE)
    # grand stair toward the harbour, landing onto the top terrace
    c.box(ax - 8, py, az + 13, ax + 8, py + 19, az + 29, PICE)
    for k in range(20):
        c.box(ax - 8, py + k + 1, az + 28 + 20 - k, ax + 8, py + k + 1, az + 28 + 20 - k,
              kit.stair(c, "minecraft:quartz_stairs", "north"))
        c.box(ax - 8, py, az + 28 + 20 - k, ax + 8, py + k, az + 28 + 20 - k, PICE)
    hall_y = py + 20
    c.box(ax - 15, hall_y, az - 12, ax + 15, hall_y + 14, az + 12, SNOW)
    c.box(ax - 14, hall_y + 1, az - 11, ax + 14, hall_y + 13, az + 11, AIR)
    for k in range(-12, 13, 4):  # front colonnade of ice pillars
        c.box(ax + k, hall_y + 1, az + 14, ax + k, hall_y + 13, az + 14, BICE)
    c.box(ax - 15, hall_y + 14, az + 13, ax + 15, hall_y + 14, az + 15, SNOW)
    c.box(ax - 2, hall_y + 1, az + 12, ax + 2, hall_y + 8, az + 12, AIR)
    kit.dome(c, ax, hall_y + 14, az, 13, SNOW)
    c.ellipsoid(ax, hall_y + 14, az, 12, 12, 12, AIR, lower=False)
    for sx in (-19, 19):  # twin spires
        c.cyl(ax + sx, az, hall_y, hall_y + 30, 2.5, PICE)
        c.cone(ax + sx, az, hall_y + 31, 10, 2.5, 0.2, BICE)
    ctx_pois = {"chief_palace": (ax, hall_y + 1, az), "harbour_water_gate": (ax, Y(ctx.sea) + 1, az + front + 8)}
    # --- Spirit Oasis courtyard behind the palace
    ox, oz = ax, az - 70
    oy = int(top_h[ox, oz]) + 1
    c.box(ox - 19, oy - 1, oz - 19, ox + 19, oy + 11, oz + 19, PICE)
    c.box(ox - 18, oy, oz - 18, ox + 18, oy + 11, oz + 18, AIR)
    c.box(ox - 18, oy - 1, oz - 18, ox + 18, oy - 1, oz + 18, "minecraft:grass_block[snowy=false]")
    c.box(ox - 18, oy - 3, oz - 18, ox + 18, oy - 2, oz + 18, "minecraft:dirt")
    c.box(ox - 2, oy, oz + 19, ox + 2, oy + 4, oz + 19, AIR)  # entrance toward the palace
    c.cyl(ox, oz, oy - 3, oy - 1, 8, WATER_S)
    c.cyl(ox, oz, oy - 1, oy - 1, 8.8, "minecraft:mossy_cobblestone", hollow=True, thickness=0.9)
    c.cyl(ox + 2, oz - 1, oy - 1, oy - 1, 2.2, "minecraft:moss_block")
    kit.tree(c, ox + 2, oy, oz - 1, "cherry", 4, rng=rng, mode=SET)
    for k in range(40):
        a = rng.uniform(0, 2 * math.pi)
        r_ = rng.uniform(10, 17)
        c.set(int(ox + r_ * math.cos(a)), oy, int(oz + r_ * math.sin(a)),
              "minecraft:fern" if k % 3 else "minecraft:short_grass")
    for k in range(-16, 17, 8):
        c.box(ox + k, oy, oz - 18, ox + k, oy + 9, oz - 18, "minecraft:bamboo[age=0,leaves=large,stage=0]")
    c.box(ox - 3, oy + 11, oz - 18, ox + 3, oy + 11, oz - 18, WATER_S)  # small falls
    ctx_pois["spirit_oasis"] = (ox, oy, oz)
    ctx_pois["tui_and_la_koi"] = (ox - 3, oy - 2, oz + 2)
    pl = ctx.place(c, cx, cz, base, facing, anchor=(ax, 0, az))
    for name, (px, py_, pz) in ctx_pois.items():
        ctx.poi(name, *pl.to_world(px, py_, pz))
    ctx.claim(cx, cz, R + 20)
    ctx.notes.append("Tiered ice city with ring + radial canals, great harbour wall with water gate, "
                     "Chief's palace plateau, and the enclosed Spirit Oasis (koi spawn POI).")


def _ice_house(c: Canvas, x0, y0, z0, w, d, h, rng) -> None:
    x1, z1 = x0 + w - 1, z0 + d - 1
    c.box(x0, y0, z0, x1, y0 + h, z1, SNOW)
    c.box(x0 + 1, y0, z0 + 1, x1 - 1, y0 + h - 1, z1 - 1, AIR)
    c.box(x0, y0 + h, z0, x1, y0 + h, z1, PICE)
    for x in range(x0 + 2, x1 - 1, 3):  # tall narrow windows
        c.box(x, y0 + 2, z0, x, y0 + h - 2, z0, "minecraft:light_blue_stained_glass")
        c.box(x, y0 + 2, z1, x, y0 + h - 2, z1, "minecraft:light_blue_stained_glass")
    c.box((x0 + x1) // 2, y0, z1, (x0 + x1) // 2, y0 + 2, z1, AIR)
    r = min(w, d) / 2
    c.ellipsoid((x0 + x1) // 2, y0 + h, (z0 + z1) // 2, r - 0.5, r * 0.8, r - 0.5, SNOW, lower=False)
    c.set((x0 + x1) // 2, y0 + h + int(r * 0.8) + 1, (z0 + z1) // 2, BICE)
    c.set((x0 + x1) // 2, y0 + 1, (z0 + z1) // 2, "minecraft:sea_lantern")
