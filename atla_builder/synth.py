"""Synthetic stand-in terrain generated from the reference class raster.

This exists so the whole pipeline (scan -> locate -> build -> write -> log)
can be exercised without the real 9000x7000 world.  It writes genuine 1.18+
Anvil region files: bedrock/stone/deepslate, class-dependent surfaces, sea
level water, and simple trees in forests (to exercise vegetation clearing).
"""
from __future__ import annotations

import gzip
import io
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import tag as T
from scipy import ndimage

from .anvil import RegionFile, bits_for_blocks, pack
from .blocks import Registry
from .geo import GeoRef
from .noise import fbm, hash01
from .reference import CLASSES, load_classes

SEA = 62
MIN_Y, MAX_Y = -64, 320
DATA_VERSION = 3955  # 1.21.1

# class -> (base height, noise amplitude)
PARAMS = {
    CLASSES["plains"]: (68, 6), CLASSES["forest"]: (72, 10), CLASSES["dense_forest"]: (74, 12),
    CLASSES["swamp"]: (63.2, 1.5), CLASSES["hills"]: (88, 16), CLASSES["red_rock"]: (96, 22),
    CLASSES["desert"]: (70, 7), CLASSES["mountain"]: (138, 42), CLASSES["snow"]: (84, 26),
    CLASSES["ocean"]: (34, 6), CLASSES["shallow"]: (52, 4),
}
BIOMES = {
    CLASSES["plains"]: "plains", CLASSES["forest"]: "forest", CLASSES["dense_forest"]: "dark_forest",
    CLASSES["swamp"]: "mangrove_swamp", CLASSES["hills"]: "windswept_hills",
    CLASSES["red_rock"]: "badlands", CLASSES["desert"]: "desert", CLASSES["mountain"]: "stony_peaks",
    CLASSES["snow"]: "snowy_plains", CLASSES["ocean"]: "deep_ocean", CLASSES["shallow"]: "ocean",
}


def _ref_fields():
    cls = load_classes()
    base = np.zeros(cls.shape, np.float32)
    amp = np.zeros(cls.shape, np.float32)
    for c, (b, a) in PARAMS.items():
        base[cls == c] = b
        amp[cls == c] = a
    land = ~np.isin(cls, (CLASSES["ocean"], CLASSES["shallow"]))
    return cls, ndimage.gaussian_filter(base, 1.0), ndimage.gaussian_filter(amp, 1.0), \
        ndimage.gaussian_filter(land.astype(np.float32), 0.9)


def _sample(field, geo: GeoRef, xs, zs, order=1):
    px, py = geo.to_ref(xs, zs)
    return ndimage.map_coordinates(field, [py - 0.5, px - 0.5], order=order, mode="nearest")


def region_fields(geo: GeoRef, x0: int, z0: int, size: int, seed: int = 1):
    """Height (int) and class (uint8) for a size x size window, indexed [x, z]."""
    margin = 192
    cell = 4
    n = (size + 2 * margin) // cell
    cls_r, base_r, amp_r, landf_r = _ref_fields()
    # coarse grid (cell blocks) with margin for the coast-distance transform
    cxs = x0 - margin + (np.arange(n) + 0.5) * cell
    czs = z0 - margin + (np.arange(n) + 0.5) * cell
    CX, CZ = np.meshgrid(cxs, czs, indexing="ij")
    wobble = fbm((n, n), 40, seed + 7, 3, origin=((x0 - margin) // cell, (z0 - margin) // cell))
    land_c = _sample(landf_r, geo, CX, CZ) + 0.18 * wobble > 0.5
    dist_c = ndimage.distance_transform_edt(land_c) * cell
    dwat_c = ndimage.distance_transform_edt(~land_c) * cell
    # full resolution window
    xs = x0 + np.arange(size) + 0.5
    zs = z0 + np.arange(size) + 0.5
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    fx = (X - (x0 - margin)) / cell - 0.5
    fz = (Z - (z0 - margin)) / cell - 0.5
    dist = ndimage.map_coordinates(dist_c, [fx, fz], order=1)
    dwat = ndimage.map_coordinates(dwat_c, [fx, fz], order=1)
    land = ndimage.map_coordinates(land_c.astype(np.float32), [fx, fz], order=1) > 0.5
    base = _sample(base_r, geo, X, Z)
    amp = _sample(amp_r, geo, X, Z)
    cls = _sample(cls_r.astype(np.float32), geo, X, Z, order=0).astype(np.uint8)
    n1 = fbm((size, size), 160, seed, 5, origin=(x0, z0))
    n2 = fbm((size, size), 48, seed + 3, 3, origin=(x0, z0))
    ridge = 1.0 - np.abs(fbm((size, size), 220, seed + 11, 4, origin=(x0, z0)))
    h_land = base + amp * (0.65 * n1 + 0.35 * n2)
    mtn = (cls == CLASSES["mountain"]) | (cls == CLASSES["snow"])
    h_land = np.where(mtn, h_land + amp * 0.8 * (ridge ** 3), h_land)
    red = cls == CLASSES["red_rock"]
    h_land = np.where(red, np.floor(h_land / 7) * 7 + 2 * n2, h_land)  # mesa terraces
    ramp = np.clip(dist / 90.0, 0, 1)
    ramp = ramp * ramp * (3 - 2 * ramp)
    h_land = SEA + 1 + np.maximum(h_land - SEA - 1, 0) * ramp + 2.0 * np.clip(dist / 8, 0, 1)
    h_sea = SEA - 2 - np.minimum(dwat / 6.0, 1) * 6 - np.clip((dwat - 40) / 5.0, 0, 26)
    h_sea = np.minimum(h_sea, base + 20)
    h = np.where(land, h_land, h_sea)
    cls = np.where(land & np.isin(cls, (CLASSES["ocean"], CLASSES["shallow"])), CLASSES["plains"], cls)
    cls = np.where(~land & ~np.isin(cls, (CLASSES["ocean"], CLASSES["shallow"])), CLASSES["shallow"], cls)
    return np.clip(np.rint(h), MIN_Y + 2, MAX_Y - 40).astype(np.int32), cls.astype(np.uint8), dist


def _chunk_columns(reg: Registry, h: np.ndarray, cls: np.ndarray, dist: np.ndarray, cx: int, cz: int):
    """Return (384,16,16) [y,z,x] ids for a chunk.  h/cls are [x,z] 16x16."""
    Y = np.arange(MIN_Y, MAX_Y)[:, None, None]
    H = h.T[None]  # [1, z, x]
    C = cls.T[None]
    D = dist.T[None]
    ids = np.full((MAX_Y - MIN_Y, 16, 16), reg.id("minecraft:air"), np.uint16)
    stone, deep = reg.id("minecraft:stone"), reg.id("minecraft:deepslate")
    ids[(Y < H - 3)] = stone
    ids[(Y < 0) & (Y < H - 3)] = deep
    ids[0] = reg.id("minecraft:bedrock")
    sub = np.full((16, 16), reg.id("minecraft:dirt"), np.uint16)
    top = np.full((16, 16), reg.id("minecraft:grass_block[snowy=false]"), np.uint16)
    c2 = cls.T
    hz = h.T
    beach = (hz <= SEA + 2) & (D[0] < 40)
    for c, t, s in (
        (CLASSES["desert"], "minecraft:sand", "minecraft:sandstone"),
        (CLASSES["red_rock"], "minecraft:red_sand", "minecraft:orange_terracotta"),
        (CLASSES["mountain"], "minecraft:stone", "minecraft:stone"),
        (CLASSES["snow"], "minecraft:snow_block", "minecraft:packed_ice"),
        (CLASSES["swamp"], "minecraft:mud", "minecraft:mud"),
        (CLASSES["ocean"], "minecraft:gravel", "minecraft:gravel"),
        (CLASSES["shallow"], "minecraft:sand", "minecraft:sand"),
    ):
        m = c2 == c
        top[m] = reg.id(t)
        sub[m] = reg.id(s)
    top[beach & ~np.isin(c2, (CLASSES["snow"], CLASSES["swamp"]))] = reg.id("minecraft:sand")
    snowcap = (hz > 175) & (c2 == CLASSES["mountain"])
    top[snowcap] = reg.id("minecraft:snow_block")
    subm = (Y >= H - 3) & (Y < H)
    ids[subm] = np.broadcast_to(sub[None], ids.shape)[subm]
    topm = Y == H
    ids[topm] = np.broadcast_to(top[None], ids.shape)[topm]
    water = (Y > H) & (Y <= SEA)
    ids[water] = reg.id("minecraft:water[level=0]")
    # swamp puddles
    # trees (fully inside the chunk so no cross-chunk writes)
    gx = cx * 16 + np.arange(16)
    gz = cz * 16 + np.arange(16)
    GX, GZ = np.meshgrid(gx, gz, indexing="xy")  # [z, x]
    r = hash01(GX, GZ, 99)
    dens = np.zeros((16, 16))
    dens[c2 == CLASSES["forest"]] = 0.012
    dens[c2 == CLASSES["dense_forest"]] = 0.02
    dens[c2 == CLASSES["plains"]] = 0.0015
    dens[c2 == CLASSES["swamp"]] = 0.01
    ok = (r < dens) & (hz > SEA)
    log = reg.id("minecraft:oak_log[axis=y]")
    leaves = reg.id("minecraft:oak_leaves[distance=1,persistent=true,waterlogged=false]")
    for lz, lx in zip(*np.nonzero(ok)):
        if not (2 <= lx <= 13 and 2 <= lz <= 13):
            continue
        base = int(hz[lz, lx]) + 1 - MIN_Y
        th = 5 + int(r[lz, lx] * 1000) % 3
        if base + th + 3 >= ids.shape[0]:
            continue
        for dy in range(th - 2, th + 2):
            rr = 2 if dy < th + 1 else 1
            sl = ids[base + dy, lz - rr:lz + rr + 1, lx - rr:lx + rr + 1]
            sl[sl == reg.id("minecraft:air")] = leaves
        ids[base:base + th, lz, lx] = log
        ids[base - 1, lz, lx] = reg.id("minecraft:dirt")
    return ids


def _encode_chunk(reg: Registry, ids: np.ndarray, cx: int, cz: int, biome: str) -> nbtlib.File:
    sections = T.List[T.Compound]()
    for sy in range(MIN_Y // 16, MAX_Y // 16):
        sub = ids[(sy * 16 - MIN_Y):(sy * 16 - MIN_Y) + 16]
        uniq, inv = np.unique(sub.reshape(-1), return_inverse=True)
        pal = T.List[T.Compound]()
        for g in uniq:
            name, props = reg.parsed(int(g))
            e = T.Compound({"Name": T.String(name)})
            if props:
                e["Properties"] = T.Compound({k: T.String(v) for k, v in props.items()})
            pal.append(e)
        bs = T.Compound({"palette": pal})
        if len(uniq) > 1:
            bs["data"] = T.LongArray(pack(inv.astype(np.int64), bits_for_blocks(len(uniq))))
        sections.append(T.Compound({
            "Y": T.Byte(sy), "block_states": bs,
            "biomes": T.Compound({"palette": T.List[T.String]([T.String("minecraft:" + biome)])}),
        }))
    root = nbtlib.File({
        "DataVersion": T.Int(DATA_VERSION), "xPos": T.Int(cx), "zPos": T.Int(cz),
        "yPos": T.Int(MIN_Y // 16), "Status": T.String("minecraft:full"),
        "LastUpdate": T.Long(0), "InhabitedTime": T.Long(0), "isLightOn": T.Byte(0),
        "sections": sections, "block_entities": T.List[T.Compound](),
        "Heightmaps": T.Compound(), "fluid_ticks": T.List[T.Compound](),
        "block_ticks": T.List[T.Compound](), "PostProcessing": T.List[T.List[T.Short]](),
        "structures": T.Compound({"starts": T.Compound(), "References": T.Compound()}),
    })
    return root


def generate_region(args) -> tuple[int, int, int]:
    rx, rz, geo_d, bounds, out_dir, seed = args
    geo = GeoRef.from_json(geo_d)
    reg = Registry(DATA_VERSION)
    min_x, min_z, max_x, max_z = bounds
    x0, z0 = rx * 512, rz * 512
    h, cls, dist = region_fields(geo, x0, z0, 512, seed)
    rf = RegionFile(Path(out_dir) / "region" / f"r.{rx}.{rz}.mca", rx, rz)
    n = 0
    for lz in range(32):
        for lx in range(32):
            cx, cz = rx * 32 + lx, rz * 32 + lz
            if not (min_x <= cx * 16 < max_x and min_z <= cz * 16 < max_z):
                continue
            sl = (slice(lx * 16, lx * 16 + 16), slice(lz * 16, lz * 16 + 16))
            ids = _chunk_columns(reg, h[sl], cls[sl], dist[sl], cx, cz)
            biome = BIOMES.get(int(np.bincount(cls[sl].ravel()).argmax()), "plains")
            rf.put_nbt(lx, lz, _encode_chunk(reg, ids, cx, cz, biome))
            n += 1
    if n:
        rf.save()
    return rx, rz, n


def write_level_dat(out_dir: Path, name: str, spawn=(0, 80, 0)) -> None:
    data = T.Compound({
        "DataVersion": T.Int(DATA_VERSION), "LevelName": T.String(name),
        "version": T.Compound({"Id": T.Int(DATA_VERSION), "Name": T.String("1.21.1"),
                               "Series": T.String("main"), "Snapshot": T.Byte(0)}),
        "SpawnX": T.Int(spawn[0]), "SpawnY": T.Int(spawn[1]), "SpawnZ": T.Int(spawn[2]),
        "GameType": T.Int(1), "allowCommands": T.Byte(1), "initialized": T.Byte(1),
        "generatorName": T.String("flat"), "Time": T.Long(0), "DayTime": T.Long(6000),
    })
    f = nbtlib.File({"Data": data}, root_name="")
    bio = io.BytesIO()
    f.write(bio)
    (out_dir / "level.dat").write_bytes(gzip.compress(bio.getvalue()))


def generate_world(out_dir: str | Path, bounds=(-4500, -3500, 4500, 3500), seed: int = 1,
                   only_bbox: tuple[int, int, int, int] | None = None, workers: int | None = None,
                   log=print) -> GeoRef:
    """Write a stand-in world covering ``bounds`` (min_x, min_z, max_x, max_z).

    ``only_bbox`` restricts generation to regions intersecting that box, which
    keeps tests fast.
    """
    out_dir = Path(out_dir)
    (out_dir / "region").mkdir(parents=True, exist_ok=True)
    geo = GeoRef.from_bounds(bounds)
    min_x, min_z, max_x, max_z = bounds
    box = only_bbox or bounds
    jobs = []
    for rx in range(math.floor(box[0] / 512), math.floor((box[2] - 1) / 512) + 1):
        for rz in range(math.floor(box[1] / 512), math.floor((box[3] - 1) / 512) + 1):
            jobs.append((rx, rz, geo.to_json(), bounds, str(out_dir), seed))
    write_level_dat(out_dir, "ATLA stand-in terrain")
    workers = workers or max(1, (os.cpu_count() or 2))
    done = 0
    if workers == 1 or len(jobs) == 1:
        results = map(generate_region, jobs)
    else:
        from .terrain import _mp_context
        ex = ProcessPoolExecutor(workers, mp_context=_mp_context())
        results = ex.map(generate_region, jobs)
    for rx, rz, n in results:
        done += 1
        if done % 10 == 0 or done == len(jobs):
            log(f"  synth: {done}/{len(jobs)} regions")
    return geo
