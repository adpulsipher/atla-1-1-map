"""Sponge Schematic v3 (.schem) export/import for WorldEdit / FAWE.

Exports contain the *structure* layer of a landmark only (the terrain
integration lives in the world itself).  Cells the builder never touched are
``minecraft:structure_void`` so the schematic can be pasted onto other terrain
with ``//paste -m !minecraft:structure_void`` without flattening it.
"""
from __future__ import annotations

import gzip
import io
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import tag as T

from .blocks import NOOP, Registry, format_state, parse_state
from .buffer import EditBuffer

VOID = "minecraft:structure_void"
MAX_CELLS = 64_000_000


def _varints(vals: np.ndarray) -> np.ndarray:
    vals = vals.astype(np.int64)
    if vals.max(initial=0) < 128:
        return vals.astype(np.uint8)
    if vals.max() >= 1 << 21:
        raise ValueError("palette too large")
    n = np.ones(vals.shape, np.int64) + (vals >= 128) + (vals >= 1 << 14)
    out = np.zeros(int(n.sum()), np.uint8)
    pos = np.concatenate([[0], np.cumsum(n)[:-1]])
    for k in range(3):
        m = n > k
        byte = (vals[m] >> (7 * k)) & 0x7F
        more = n[m] > k + 1
        out[pos[m] + k] = (byte | (more * 0x80)).astype(np.uint8)
    return out


def _dense(buf: EditBuffer, box) -> np.ndarray:
    x0, y0, z0, x1, y1, z1 = box
    arr = np.zeros((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), np.uint16)  # [y, z, x]
    for xs, ys, zs, ids, _md in buf.iter_voxels():
        m = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1) & (zs >= z0) & (zs <= z1)
        if m.any():
            arr[ys[m] - y0, zs[m] - z0, xs[m] - x0] = ids[m]
    return arr


def tight_bbox(buf: EditBuffer):
    mins = np.array([1 << 30] * 3)
    maxs = -mins
    for xs, ys, zs, _ids, _md in buf.iter_voxels():
        mins = np.minimum(mins, [xs.min(), ys.min(), zs.min()])
        maxs = np.maximum(maxs, [xs.max(), ys.max(), zs.max()])
    if maxs[0] < mins[0]:
        return None
    return int(mins[0]), int(mins[1]), int(mins[2]), int(maxs[0]), int(maxs[1]), int(maxs[2])


def write_schem(buf: EditBuffer, path: Path, reg: Registry, data_version: int, name: str,
                box=None, anchor=None) -> dict:
    box = box or tight_bbox(buf)
    if box is None:
        return {}
    x0, y0, z0, x1, y1, z1 = box
    W, H, L = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
    arr = _dense(buf, box)
    uniq, inv = np.unique(arr.reshape(-1), return_inverse=True)
    palette = T.Compound()
    for i, g in enumerate(uniq):
        palette[VOID if int(g) == NOOP else reg.state(int(g))] = T.Int(i)
    data = _varints(inv)
    ax, ay, az = anchor or (x0, y0, z0)
    root = nbtlib.File({"Schematic": T.Compound({
        "Version": T.Int(3), "DataVersion": T.Int(data_version),
        "Width": T.Short(np.int16(np.uint16(W))), "Height": T.Short(np.int16(np.uint16(H))),
        "Length": T.Short(np.int16(np.uint16(L))),
        "Offset": T.IntArray([x0 - ax, y0 - ay, z0 - az]),
        "Metadata": T.Compound({"Name": T.String(name), "Author": T.String("atla_builder"),
                                "WorldOrigin": T.IntArray([x0, y0, z0]),
                                "WEOffsetX": T.Int(x0 - ax), "WEOffsetY": T.Int(y0 - ay),
                                "WEOffsetZ": T.Int(z0 - az)}),
        "Blocks": T.Compound({"Palette": palette, "Data": T.ByteArray(data.view(np.int8)),
                              "BlockEntities": T.List[T.Compound]()}),
    })}, root_name="")
    bio = io.BytesIO()
    root.write(bio)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(bio.getvalue(), 6))
    return {"file": path.name, "size": [W, H, L], "world_origin": [x0, y0, z0]}


def export_landmark(buf: EditBuffer, out_dir: Path, reg: Registry, data_version: int, lid: str) -> list[dict]:
    """Export a landmark, split into 256-block tiles when it is very large."""
    box = tight_bbox(buf)
    if box is None:
        return []
    x0, y0, z0, x1, y1, z1 = box
    H = y1 - y0 + 1
    if (x1 - x0 + 1) * H * (z1 - z0 + 1) <= MAX_CELLS:
        return [write_schem(buf, out_dir / f"{lid}.schem", reg, data_version, lid, box)]
    out = []
    tile = 256
    for tx in range(x0, x1 + 1, tile):
        for tz in range(z0, z1 + 1, tile):
            sub = (tx, y0, tz, min(tx + tile - 1, x1), y1, min(tz + tile - 1, z1))
            info = write_schem(buf, out_dir / f"{lid}__{tx}_{tz}.schem", reg, data_version,
                               f"{lid} tile {tx},{tz}", sub)
            if info:
                out.append(info)
    return out


def read_schem(path: Path, reg: Registry):
    """Load a .schem (v2 or v3) -> (ids[y,z,x] uint16 with 0 for void/air-skip, offset)."""
    root = nbtlib.load(path)
    sch = root.get("Schematic", root)
    W, H, L = (int(np.uint16(np.int16(int(sch[k])))) for k in ("Width", "Height", "Length"))
    blocks = sch.get("Blocks", sch)
    pal = blocks["Palette"]
    data = np.asarray(blocks.get("Data", blocks.get("BlockData")), dtype=np.int8).view(np.uint8)
    vals = []
    v = shift = 0
    for b in data.tolist():
        v |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
        else:
            vals.append(v)
            v = shift = 0
    lut = np.zeros(max(int(i) for i in pal.values()) + 1, np.uint16)
    for state, i in pal.items():
        name, props = parse_state(str(state))
        lut[int(i)] = 0 if name in (VOID, "minecraft:air") else reg.id(format_state(name, props))
    ids = lut[np.array(vals, np.int64)].reshape(H, L, W)
    off = [int(v) for v in sch.get("Offset", [0, 0, 0])]
    return ids, off
