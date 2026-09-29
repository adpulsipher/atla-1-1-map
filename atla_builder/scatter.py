"""Nation-themed settlements between the landmarks, linked by dirt roads.

Keeps the world from feeling "alive at the landmarks, dead in between":
Earth Kingdom farm hamlets and market villages, Fire Nation villages and
watch posts, Water Tribe igloo camps on the polar coasts, and sparse Air
Nomad shrines on the high islands.  Settlements avoid landmark footprints
and each other (Poisson spacing), and a road graph (minimum spanning tree
per land-mass, plus spurs to landmarks) is painted onto the terrain so NPCs
have paths to follow.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse.csgraph import minimum_spanning_tree

from .geo import GeoRef
from .palettes import AIR, EARTH, EARTH_POOR, EARTH_RURAL, FIRE, FIRE_COMMON
from .structures import kit
from .structures.common import BuildContext, facing_from_vector
from .structures.village import paint_path, place_houses
from .terrain import NONE, S_ICE, S_RED_SAND, S_SAND, S_SNOW, TerrainModel


@dataclass
class Settlement:
    id: str
    kind: str
    nation: str
    x: int
    z: int
    y: int = 0
    buildings: int = 0
    pois: dict = field(default_factory=dict)


def nation_at(geo: GeoRef, tm: TerrainModel, x: int, z: int) -> str:
    """Nation zone from the reference-map position (+ polar surfaces)."""
    px, py = geo.to_ref(x, z)
    surf = int(tm.surf[np.clip(x - tm.x0, 0, tm.shape[0] - 1), np.clip(z - tm.z0, 0, tm.shape[1] - 1)])
    if py < 90 or py > 405 or surf in (S_SNOW, S_ICE) and (py < 110 or py > 395):
        return "water"
    if px < 215 and 190 < py < 320:
        return "fire"
    if px < 170 and 100 <= py <= 190:
        return "air"          # Western Air Temple islands
    if py > 330 and px < 330:
        return "air"          # Patola range (Southern Air Temple archipelago)
    if px > 468 and py > 280:
        return "air"          # Eastern Air Temple islands
    return "earth"


SPACING = {"earth": 240, "fire": 200, "water": 300, "air": 420}


def plan(tm: TerrainModel, geo: GeoRef, claims: list[tuple[int, int, float]], seed: int = 7,
         log=print) -> list[Settlement]:
    rng = np.random.default_rng(seed)
    step = 64
    cands = []
    xs = np.arange(tm.x0 + step // 2, tm.x0 + tm.shape[0], step)
    zs = np.arange(tm.z0 + step // 2, tm.z0 + tm.shape[1], step)
    land = tm.land()
    for x in xs:
        for z in zs:
            jx, jz = int(x + rng.integers(-24, 25)), int(z + rng.integers(-24, 25))
            i, j = jx - tm.x0, jz - tm.z0
            if not (20 <= i < tm.shape[0] - 20 and 20 <= j < tm.shape[1] - 20):
                continue
            if not land[i, j]:
                continue
            win = tm.ground[i - 18:i + 19:3, j - 18:j + 19:3]
            if (win == NONE).any() or (~land[i - 18:i + 19:3, j - 18:j + 19:3]).any():
                continue
            g = int(tm.ground[i, j])
            if not (tm.sea_level + 2 <= g <= 210) or int(win.max()) - int(win.min()) > 15:
                continue
            sw = tm.surf[i - 12:i + 13:4, j - 12:j + 13:4]
            if (np.isin(sw, (S_SAND, S_RED_SAND))).mean() > 0.3:
                continue  # the Si Wong sands and beaches stay empty
            if any(math.hypot(jx - cx, jz - cz) < r + 90 for cx, cz, r in claims):
                continue
            cands.append((jx, jz, g))
    order = rng.permutation(len(cands))
    chosen: list[Settlement] = []
    grid: dict[tuple[int, int], list[Settlement]] = {}
    for k in order:
        x, z, g = cands[k]
        nat = nation_at(geo, tm, x, z)
        sp = SPACING[nat]
        gx, gz = x // 256, z // 256
        ok = True
        for ddx in (-2, -1, 0, 1, 2):
            for ddz in (-2, -1, 0, 1, 2):
                for s in grid.get((gx + ddx, gz + ddz), []):
                    if math.hypot(s.x - x, s.z - z) < max(sp, SPACING[s.nation]):
                        ok = False
                        break
        if not ok:
            continue
        kind = _kind(nat, rng, g, tm.sea_level)
        st = Settlement(f"{nat}_{kind}_{len(chosen):03d}", kind, nat, x, z, g)
        chosen.append(st)
        grid.setdefault((gx, gz), []).append(st)
    counts = {}
    for s in chosen:
        counts[s.nation] = counts.get(s.nation, 0) + 1
    log(f"  scatter plan: {len(chosen)} settlements {counts}")
    return chosen


def _kind(nat: str, rng, g: int, sea: int) -> str:
    r = rng.random()
    if nat == "earth":
        return "market_village" if r < 0.18 else ("farm_hamlet" if r < 0.85 else "watchtower_post")
    if nat == "fire":
        return "fire_village" if r < 0.75 else "fire_outpost"
    if nat == "water":
        return "igloo_camp"
    return "air_shrine"


def build_settlement(reg, tm: TerrainModel, st: Settlement, seed: int) -> BuildContext:
    from .locate import Site

    site = Site(id=st.id, x=st.x, y=st.y, z=st.z, facing="south", angle=0.0, fit_radius=60,
                strategy="scatter", anchor=(st.x, st.z), sea_level=tm.sea_level)
    ctx = BuildContext(reg, tm, site, {"id": st.id, "footprint_r": 50}, seed=seed)
    cx, cz = st.x, st.z
    B = ctx.struct
    rng = ctx.rng
    n = 0
    if st.kind in ("farm_hamlet", "market_village"):
        big = st.kind == "market_village"
        y = ctx.ground_median(cx, cz, 6)
        ctx.level_pad(cx, cz, 5, 10, y, top="minecraft:dirt_path")
        B.cyl(cx, cz, y + 1, y + 1, 1.6, "minecraft:cobblestone_wall", hollow=True, thickness=1)
        B.set(cx, y, cz, "minecraft:water[level=0]")
        B.box(cx - 1, y + 2, cz - 1, cx + 1, y + 3, cz + 1, "minecraft:air")
        B.box(cx, y + 2, cz, cx, y + 3, cz, "minecraft:oak_fence")
        pals = [EARTH, EARTH_POOR] if big else [EARTH_RURAL, EARTH_RURAL, EARTH_POOR]
        hs = place_houses(ctx, cx, cz, 10, 42 if big else 32, int(rng.integers(8, 13)) if big else int(rng.integers(3, 7)),
                          pals, roof="hip" if big else "thatch", avoid=[(cx, cz, 5)], max_slope=8, tries=300)
        for (hx, hz, *_r) in hs:
            paint_path(ctx, cx, cz, hx, hz, 2)
        n = len(hs)
        # crop plots beside the hamlet
        for k in range(2 if big else 3):
            a = rng.uniform(0, 2 * math.pi)
            fx, fz = int(cx + 46 * math.cos(a)), int(cz + 46 * math.sin(a))
            _field(ctx, fx, fz, 9, 7, rng)
        st.pois["well"] = (cx, y + 1, cz)
    elif st.kind == "watchtower_post":
        y = ctx.ground_median(cx, cz, 5)
        ctx.level_pad(cx, cz, 7, 12, y)
        B.box(cx - 3, y + 1, cz - 3, cx + 3, y + 14, cz + 3, "minecraft:stone_bricks")
        B.box(cx - 2, y + 1, cz - 2, cx + 2, y + 13, cz + 2, "minecraft:air")
        B.box(cx, y + 1, cz + 3, cx, y + 2, cz + 3, "minecraft:air")
        kit.hip_roof(B, cx - 3, cz - 3, cx + 3, cz + 3, y + 15, EARTH.roof_stairs, EARTH.roof, overhang=1)
        for i in range(1, 14):
            B.set(cx, y + i, cz - 2, "minecraft:ladder[facing=south,waterlogged=false]")
        n = 1
    elif st.kind == "fire_village":
        y = ctx.ground_median(cx, cz, 6)
        ctx.level_pad(cx, cz, 6, 11, y, top="minecraft:polished_blackstone_bricks")
        B.box(cx, y + 1, cz, cx, y + 4, cz, "minecraft:red_nether_bricks")
        B.set(cx, y + 5, cz, "minecraft:magma_block")
        hs = place_houses(ctx, cx, cz, 10, 34, int(rng.integers(4, 8)), [FIRE_COMMON, FIRE_COMMON, FIRE],
                          avoid=[(cx, cz, 6)], max_slope=8, tries=300)
        for (hx, hz, *_r) in hs:
            paint_path(ctx, cx, cz, hx, hz, 2, mat="minecraft:gravel", mat2="minecraft:coarse_dirt")
        n = len(hs)
        st.pois["shrine"] = (cx, y + 1, cz)
    elif st.kind == "fire_outpost":
        y = ctx.ground_median(cx, cz, 8)
        ctx.level_pad(cx, cz, 12, 18, y, top="minecraft:polished_blackstone_bricks")
        B.walls(cx - 11, y + 1, cz - 11, cx + 11, y + 5, cz + 11, "minecraft:polished_blackstone_bricks")
        B.box(cx - 1, y + 1, cz + 11, cx + 1, y + 3, cz + 11, "minecraft:air")
        B.box(cx - 3, y + 1, cz - 3, cx + 3, y + 18, cz + 3, "minecraft:red_terracotta")
        B.box(cx - 2, y + 1, cz - 2, cx + 2, y + 17, cz + 2, "minecraft:air")
        kit.hip_roof(B, cx - 3, cz - 3, cx + 3, cz + 3, y + 19, FIRE.roof_stairs, FIRE.roof, overhang=1,
                     ridge=FIRE.ridge)
        B.box(cx + 4, y + 10, cz, cx + 4, y + 16, cz, "minecraft:red_wool")
        n = 1
    elif st.kind == "igloo_camp":
        y = ctx.ground_median(cx, cz, 6)
        ctx.level_pad(cx, cz, 16, 24, y, top="minecraft:snow_block", sub="minecraft:packed_ice")
        k = int(rng.integers(3, 7))
        for i in range(k):
            a = 2 * math.pi * i / k + rng.uniform(-0.3, 0.3)
            ix, iz = int(cx + 11 * math.cos(a)), int(cz + 11 * math.sin(a))
            if i % 3 == 2:
                kit.hide_tent(B, ix, y + 1, iz, 3, 6)
            else:
                kit.igloo(B, ix, y + 1, iz, 4, door=facing_from_vector(cx - ix, cz - iz))
        B.cyl(cx, cz, y, y, 1.5, "minecraft:magma_block")
        n = k
    elif st.kind == "air_shrine":
        y = ctx.ground_median(cx, cz, 4)
        ctx.level_pad(cx, cz, 6, 10, y, top=AIR.floor)
        kit.air_tower(B, cx, cz, y + 1, 3, 9, AIR, roof_h=8, windows=False, balcony=False)
        B.cyl(cx, cz, y, y, 5.5, "minecraft:smooth_sandstone", hollow=True, thickness=1)
        n = 1
    st.y = ctx.ground(cx, cz)
    st.buildings = n
    return ctx


def _field(ctx: BuildContext, fx, fz, hw, hd, rng) -> None:
    g = ctx.field(fx - hw, fz - hd, 2 * hw + 1, 2 * hd + 1)
    wat = ctx.field(fx - hw, fz - hd, 2 * hw + 1, 2 * hd + 1, "water")
    if (wat != NONE).any() or g.max() - g.min() > 2:
        return
    y = int(np.median(g))
    ctx.level_pad(fx, fz, max(hw, hd), max(hw, hd) + 3, y, square=True)
    crop = ["minecraft:wheat[age=7]", "minecraft:carrots[age=7]", "minecraft:potatoes[age=7]"][int(rng.integers(0, 3))]
    ctx.terrain.box(fx - hw, y, fz - hd, fx + hw, y, fz + hd, "minecraft:farmland[moisture=7]")
    ctx.terrain.box(fx - hw, y + 1, fz - hd, fx + hw, y + 1, fz + hd, crop)
    ctx.terrain.box(fx, y, fz - hd, fx, y, fz + hd, "minecraft:water[level=0]")
    ctx.terrain.box(fx, y + 1, fz - hd, fx, y + 1, fz + hd, "minecraft:air")


def road_network(tm: TerrainModel, settlements: list[Settlement], landmark_pts: list[tuple[str, int, int]],
                 max_edge: int = 700) -> list[tuple[str, str, int]]:
    """Minimum spanning forest over settlements + landmarks, edges on dry land only."""
    nodes = [(s.id, s.x, s.z) for s in settlements] + landmark_pts
    n = len(nodes)
    if n < 2:
        return []
    P = np.array([(x, z) for _, x, z in nodes], dtype=float)
    D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
    D[D > max_edge] = 0
    land = tm.land()
    # reject edges that cross water for more than a few blocks
    for i in range(n):
        for j in range(i + 1, n):
            if D[i, j] == 0:
                continue
            k = int(D[i, j] // 8) + 2
            xs = np.linspace(P[i, 0], P[j, 0], k).astype(int) - tm.x0
            zs = np.linspace(P[i, 1], P[j, 1], k).astype(int) - tm.z0
            ok = (xs >= 0) & (xs < tm.shape[0]) & (zs >= 0) & (zs < tm.shape[1])
            wet = (~land[np.clip(xs, 0, tm.shape[0] - 1), np.clip(zs, 0, tm.shape[1] - 1)]) | ~ok
            if wet.sum() > 3:
                D[i, j] = D[j, i] = 0
    mst = minimum_spanning_tree(D).tocoo()
    return [(nodes[i][0], nodes[j][0], int(w)) for i, j, w in zip(mst.row, mst.col, mst.data)]


def paint_roads(ctx_factory, tm: TerrainModel, nodes: dict[str, tuple[int, int]], edges) -> BuildContext:
    """Paint all road edges into a single context (terrain buffer only)."""
    ctx = ctx_factory()
    for a, b, _w in edges:
        (x0, z0), (x1, z1) = nodes[a], nodes[b]
        # break into 64-block legs so paths hug the terrain
        L = math.hypot(x1 - x0, z1 - z0)
        legs = max(1, int(L // 64))
        for k in range(legs):
            t0, t1 = k / legs, (k + 1) / legs
            ax_, az_ = int(x0 + (x1 - x0) * t0), int(z0 + (z1 - z0) * t0)
            bx_, bz_ = int(x0 + (x1 - x0) * t1), int(z0 + (z1 - z0) * t1)
            paint_path(ctx, ax_, az_, bx_, bz_, 3)
    return ctx
