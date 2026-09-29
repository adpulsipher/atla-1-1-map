"""Terrain scan: per-column ground / water / canopy heights and surface material."""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from .anvil import Chunk, RegionFile, World
from .blocks import C_AIR, C_SOLID, C_WATER, Registry

NONE = -32768

# surface material categories
(S_NONE, S_GRASS, S_DIRT, S_SAND, S_RED_SAND, S_GRAVEL, S_STONE, S_SNOW, S_ICE,
 S_TERRACOTTA, S_SANDSTONE, S_MUD, S_PODZOL, S_CLAY, S_OTHER) = range(15)

SURFACE_BLOCKS = {  # category -> (top, subsurface)
    S_GRASS: ("minecraft:grass_block[snowy=false]", "minecraft:dirt"),
    S_DIRT: ("minecraft:coarse_dirt", "minecraft:dirt"),
    S_SAND: ("minecraft:sand", "minecraft:sandstone"),
    S_RED_SAND: ("minecraft:red_sand", "minecraft:orange_terracotta"),
    S_GRAVEL: ("minecraft:gravel", "minecraft:stone"),
    S_STONE: ("minecraft:stone", "minecraft:stone"),
    S_SNOW: ("minecraft:snow_block", "minecraft:packed_ice"),
    S_ICE: ("minecraft:packed_ice", "minecraft:packed_ice"),
    S_TERRACOTTA: ("minecraft:terracotta", "minecraft:terracotta"),
    S_SANDSTONE: ("minecraft:sandstone", "minecraft:sandstone"),
    S_MUD: ("minecraft:mud", "minecraft:packed_mud"),
    S_PODZOL: ("minecraft:podzol", "minecraft:dirt"),
    S_CLAY: ("minecraft:clay", "minecraft:clay"),
    S_OTHER: ("minecraft:grass_block[snowy=false]", "minecraft:dirt"),
    S_NONE: ("minecraft:stone", "minecraft:stone"),
}


def surface_category(name: str) -> int:
    b = name.split(":")[-1]
    if b in ("grass_block", "moss_block", "mycelium"):
        return S_GRASS
    if b in ("dirt", "coarse_dirt", "rooted_dirt", "farmland", "dirt_path"):
        return S_DIRT
    if b in ("sand", "suspicious_sand"):
        return S_SAND
    if b == "red_sand":
        return S_RED_SAND
    if b in ("gravel", "suspicious_gravel"):
        return S_GRAVEL
    if b in ("snow_block", "powder_snow"):
        return S_SNOW
    if b in ("ice", "packed_ice", "blue_ice"):
        return S_ICE
    if b.endswith("terracotta"):
        return S_TERRACOTTA
    if "sandstone" in b:
        return S_SANDSTONE
    if b in ("mud", "packed_mud", "muddy_mangrove_roots"):
        return S_MUD
    if b == "podzol":
        return S_PODZOL
    if b == "clay":
        return S_CLAY
    if b in ("stone", "andesite", "diorite", "granite", "deepslate", "tuff", "calcite",
             "cobblestone", "mossy_cobblestone", "basalt", "blackstone", "dripstone_block",
             "smooth_basalt", "obsidian", "bedrock", "magma_block", "netherrack"):
        return S_STONE
    return S_OTHER


@dataclass
class TerrainModel:
    x0: int
    z0: int
    ground: np.ndarray  # int16 [x, z], y of top solid block (NONE = void)
    top: np.ndarray  # int16, y of top non-air block (trees, plants included)
    water: np.ndarray  # int16, y of water surface above ground (NONE = dry)
    surf: np.ndarray  # uint8 surface category
    sea_level: int = 62

    @property
    def shape(self) -> tuple[int, int]:
        return self.ground.shape  # type: ignore[return-value]

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        W, L = self.ground.shape
        return self.x0, self.z0, self.x0 + W, self.z0 + L

    def inside(self, x, z) -> np.ndarray:
        W, L = self.ground.shape
        x = np.asarray(x) - self.x0
        z = np.asarray(z) - self.z0
        return (x >= 0) & (x < W) & (z >= 0) & (z < L)

    def _idx(self, x, z):
        W, L = self.ground.shape
        return (np.clip(np.asarray(x, dtype=np.int64) - self.x0, 0, W - 1),
                np.clip(np.asarray(z, dtype=np.int64) - self.z0, 0, L - 1))

    def ground_at(self, x, z):
        i, j = self._idx(x, z)
        return self.ground[i, j]

    def water_at(self, x, z):
        i, j = self._idx(x, z)
        return self.water[i, j]

    def window(self, x0: int, z0: int, w: int, l: int, name: str = "ground") -> np.ndarray:
        """Copy of a field over [x0, x0+w) x [z0, z0+l), clamped at the edges."""
        arr = getattr(self, name)
        xs = np.clip(np.arange(x0, x0 + w) - self.x0, 0, arr.shape[0] - 1)
        zs = np.clip(np.arange(z0, z0 + l) - self.z0, 0, arr.shape[1] - 1)
        return arr[np.ix_(xs, zs)]

    def land(self) -> np.ndarray:
        return (self.water == NONE) & (self.ground != NONE)

    def downsample_land(self, cell: int) -> np.ndarray:
        land = self.land()
        W, L = land.shape
        w, l = W // cell, L // cell
        return land[: w * cell, : l * cell].reshape(w, cell, l, cell).mean(axis=(1, 3)) > 0.5

    def save(self, path: str | Path) -> None:
        np.savez_compressed(path, x0=self.x0, z0=self.z0, ground=self.ground, top=self.top,
                            water=self.water, surf=self.surf, sea_level=self.sea_level)

    @classmethod
    def load(cls, path: str | Path) -> "TerrainModel":
        d = np.load(path)
        return cls(int(d["x0"]), int(d["z0"]), d["ground"], d["top"], d["water"], d["surf"],
                   int(d["sea_level"]))

    def estimate_sea_level(self) -> int:
        w = self.water[self.water != NONE]
        if w.size == 0:
            return 62
        vals, counts = np.unique(w, return_counts=True)
        return int(vals[counts.argmax()])


# --------------------------------------------------------------------------
def scan_chunk(ch: Chunk, cls_lut_fn) -> tuple[np.ndarray, ...]:
    """Return ground, top, water, surface-id-of-ground arrays [x, z]."""
    ground = np.full((16, 16), NONE, np.int32)
    top = np.full((16, 16), NONE, np.int32)
    water = np.full((16, 16), NONE, np.int32)
    gid = np.zeros((16, 16), np.int32)
    found = np.zeros((16, 16), bool)  # indexed [z, x] internally
    tfound = np.zeros((16, 16), bool)
    wfound = np.zeros((16, 16), bool)
    g_zx = np.full((16, 16), NONE, np.int32)
    t_zx = np.full((16, 16), NONE, np.int32)
    w_zx = np.full((16, 16), NONE, np.int32)
    zz, xx = np.meshgrid(np.arange(16), np.arange(16), indexing="ij")
    for sy in sorted(ch.sections, reverse=True):
        sec = ch.sections[sy]
        if "block_states" not in sec:
            continue
        pal = sec["block_states"]["palette"]
        if len(pal) == 1 and str(pal[0]["Name"]).split(":")[-1] in ("air", "cave_air", "void_air"):
            continue
        arr = ch.section_array(sy)
        lut = cls_lut_fn()
        c = lut[arr]  # [y, z, x]
        nonair = c != C_AIR
        solid = c == C_SOLID
        wat = c == C_WATER
        rev = slice(None, None, -1)
        has_t = nonair.any(axis=0)
        yt = 15 - np.argmax(nonair[rev], axis=0)
        new_t = has_t & ~tfound
        t_zx[new_t] = sy * 16 + yt[new_t]
        tfound |= new_t
        has_s = solid.any(axis=0)
        ys = 15 - np.argmax(solid[rev], axis=0)
        has_w = wat.any(axis=0)
        yw = 15 - np.argmax(wat[rev], axis=0)
        # water counts only if above the ground found in this section
        wat_ok = has_w & ~wfound & ~found & (~has_s | (yw > ys))
        w_zx[wat_ok] = sy * 16 + yw[wat_ok]
        wfound |= wat_ok
        new_s = has_s & ~found
        g_zx[new_s] = sy * 16 + ys[new_s]
        if new_s.any():
            vals = arr[ys, zz, xx]
            gid_zx = gid.T  # view [z, x]
            gid_zx[new_s] = vals[new_s]
        found |= new_s
        if found.all():
            break
    ground[:] = g_zx.T
    top[:] = t_zx.T
    water[:] = w_zx.T
    return ground, top, water, gid


def _scan_region(args):
    world_path, rx, rz = args
    reg = Registry()
    rf = RegionFile(Path(world_path) / "region" / f"r.{rx}.{rz}.mca", rx, rz)
    g = np.full((512, 512), NONE, np.int16)
    t = np.full((512, 512), NONE, np.int16)
    w = np.full((512, 512), NONE, np.int16)
    s = np.zeros((512, 512), np.uint8)
    state = {"n": -1, "lut": None, "surf": None}

    def cls_lut():
        if state["n"] != len(reg):
            state["lut"] = reg.classes()
            state["n"] = len(reg)
        return state["lut"]

    surf_cache: dict[int, int] = {}
    for (lx, lz) in list(rf.raw):
        root = rf.read_nbt(lx, lz)
        ch = Chunk(root, reg)
        gr, tp, wt, gid = scan_chunk(ch, cls_lut)
        sl = (slice(lx * 16, lx * 16 + 16), slice(lz * 16, lz * 16 + 16))
        g[sl], t[sl], w[sl] = gr, tp, wt
        cat = np.zeros((16, 16), np.uint8)
        for u in np.unique(gid):
            u = int(u)
            if u not in surf_cache:
                surf_cache[u] = surface_category(reg.parsed(u)[0]) if u else S_NONE
            cat[gid == u] = surf_cache[u]
        s[sl] = cat
    return rx, rz, g, t, w, s


def scan_world(world: World, workers: int | None = None, log=print) -> TerrainModel:
    coords = world.region_coords()
    if not coords:
        raise RuntimeError("world has no region files")
    min_x, min_z, max_x, max_z = world.bounds_blocks()
    W, L = max_x - min_x, max_z - min_z
    ground = np.full((W, L), NONE, np.int16)
    top = np.full((W, L), NONE, np.int16)
    water = np.full((W, L), NONE, np.int16)
    surf = np.zeros((W, L), np.uint8)
    jobs = [(str(world.path), rx, rz) for rx, rz in coords]
    workers = workers or min(os.cpu_count() or 2, 8)
    ex = None
    if workers > 1 and len(jobs) > 1:
        ex = ProcessPoolExecutor(workers, mp_context=_mp_context())
        it = ex.map(_scan_region, jobs, chunksize=2)
    else:
        it = map(_scan_region, jobs)
    for n, (rx, rz, g, t, w, s) in enumerate(it, 1):
        ax, az = rx * 512 - min_x, rz * 512 - min_z
        # intersect the region with the model window
        sx0, sz0 = max(0, -ax), max(0, -az)
        sx1, sz1 = min(512, W - ax), min(512, L - az)
        if sx1 <= sx0 or sz1 <= sz0:
            continue
        dst = (slice(ax + sx0, ax + sx1), slice(az + sz0, az + sz1))
        src = (slice(sx0, sx1), slice(sz0, sz1))
        ground[dst], top[dst], water[dst], surf[dst] = g[src], t[src], w[src], s[src]
        if n % 20 == 0 or n == len(jobs):
            log(f"  scan: {n}/{len(jobs)} regions")
    if ex is not None:
        ex.shutdown()
    tm = TerrainModel(min_x, min_z, ground, top, water, surf)
    tm.sea_level = tm.estimate_sea_level()
    return tm


def _mp_context():
    """Platform default start method; ATLA_MP_START=spawn reproduces Windows."""
    import multiprocessing as mp
    method = os.environ.get("ATLA_MP_START")
    return mp.get_context(method) if method else None


# --------------------------------------------------------------------------
# analysis helpers
# --------------------------------------------------------------------------
def smoothed_ground(tm: TerrainModel, x0: int, z0: int, w: int, l: int, sigma: float = 2.0):
    g = tm.window(x0, z0, w, l).astype(np.float32)
    g[g == NONE] = tm.sea_level - 20
    return ndimage.gaussian_filter(g, sigma)


def slope(g: np.ndarray) -> np.ndarray:
    gx, gz = np.gradient(g)
    return np.hypot(gx, gz)
