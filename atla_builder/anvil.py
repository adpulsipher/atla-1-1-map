"""Minimal, dependency-light Anvil (Java Edition 1.18+) reader/writer.

Only what the builder needs is implemented:

* region files (``r.X.Z.mca``) with gzip / zlib / uncompressed / LZ4 chunk
  payloads and oversized external ``.mcc`` chunks,
* 1.18+ chunk sections (``block_states`` palette + packed ``data``),
* re-encoding of edited sections, after which ``Heightmaps`` are dropped and
  ``isLightOn`` is cleared so the game recomputes heightmaps and lighting when
  the chunk is next loaded.

Pre-1.18 worlds (``Level`` wrapper, ``Palette``/``BlockStates``) are rejected
explicitly rather than risk corrupting them.
"""
from __future__ import annotations

import gzip
import io
import math
import os
import shutil
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import tag as T

from .blocks import AIR, DV_1_18, Registry, format_state

SECTOR = 4096


class UnsupportedWorld(RuntimeError):
    pass


# --------------------------------------------------------------------------
# bit packing (1.16+ layout: entries never straddle two longs)
# --------------------------------------------------------------------------
def bits_for_blocks(palette_len: int) -> int:
    return max(4, math.ceil(math.log2(palette_len))) if palette_len > 1 else 0


def bits_for_biomes(palette_len: int) -> int:
    return math.ceil(math.log2(palette_len)) if palette_len > 1 else 0


def pack(values: np.ndarray, bits: int) -> np.ndarray:
    epl = 64 // bits
    n = -(-values.size // epl)
    padded = np.zeros(n * epl, dtype=np.uint64)
    padded[: values.size] = values.astype(np.uint64)
    padded = padded.reshape(n, epl)
    shifts = np.arange(epl, dtype=np.uint64) * np.uint64(bits)
    longs = np.bitwise_or.reduce(padded << shifts[None, :], axis=1)
    return longs.view(np.int64)


def unpack(longs, bits: int, count: int) -> np.ndarray:
    arr = np.asarray(longs, dtype=np.int64).view(np.uint64)
    epl = 64 // bits
    shifts = np.arange(epl, dtype=np.uint64) * np.uint64(bits)
    mask = np.uint64((1 << bits) - 1)
    vals = (arr[:, None] >> shifts[None, :]) & mask
    return vals.reshape(-1)[:count].astype(np.int64)


def _bits_from_length(n_longs: int, count: int, minimum: int) -> int:
    for bits in range(max(1, minimum), 33):
        if -(-count // (64 // bits)) == n_longs:
            return bits
    raise ValueError(f"cannot infer bit width for {n_longs} longs")


# --------------------------------------------------------------------------
# compression
# --------------------------------------------------------------------------
def _lz4_block_decompress(buf: bytes) -> bytes:
    """Decode lz4-java's LZ4BlockOutputStream framing (MC 1.20.5+ option)."""
    import lz4.block  # optional dependency

    out = bytearray()
    pos = 0
    while pos < len(buf):
        if buf[pos:pos + 8] != b"LZ4Block":
            raise ValueError("bad LZ4Block magic")
        token = buf[pos + 8]
        clen, dlen, _chk = struct.unpack("<iii", buf[pos + 9:pos + 21])
        pos += 21
        if dlen == 0:
            break
        method = token & 0xF0
        data = buf[pos:pos + clen]
        pos += clen
        if method == 0x10:
            out += data
        else:
            out += lz4.block.decompress(data, uncompressed_size=dlen)
    return bytes(out)


def decompress(ctype: int, payload: bytes) -> bytes:
    if ctype == 1:
        return gzip.decompress(payload)
    if ctype == 2:
        return zlib.decompress(payload)
    if ctype == 3:
        return payload
    if ctype == 4:
        return _lz4_block_decompress(payload)
    raise UnsupportedWorld(f"unknown chunk compression type {ctype}")


def parse_nbt(raw: bytes) -> nbtlib.File:
    return nbtlib.File.parse(io.BytesIO(raw))


def dump_nbt(root: nbtlib.File) -> bytes:
    bio = io.BytesIO()
    root.write(bio)
    return bio.getvalue()


# --------------------------------------------------------------------------
# region files
# --------------------------------------------------------------------------
class RegionFile:
    """All chunk payloads of one region, kept compressed until requested."""

    def __init__(self, path: Path, rx: int, rz: int):
        self.path = Path(path)
        self.rx, self.rz = rx, rz
        self.raw: dict[tuple[int, int], tuple[int, bytes]] = {}
        self.timestamps: dict[tuple[int, int], int] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        data = self.path.read_bytes()
        if len(data) < 2 * SECTOR:
            return
        loc = np.frombuffer(data[:SECTOR], dtype=">u4")
        ts = np.frombuffer(data[SECTOR:2 * SECTOR], dtype=">u4")
        for i in range(1024):
            v = int(loc[i])
            if v == 0:
                continue
            off = (v >> 8) * SECTOR
            if off + 5 > len(data):
                continue
            length = struct.unpack(">I", data[off:off + 4])[0]
            if length == 0:
                continue
            ctype = data[off + 4]
            payload = data[off + 5:off + 4 + length]
            lx, lz = i & 31, i >> 5
            if ctype & 128:
                ext = self.path.parent / f"c.{self.rx * 32 + lx}.{self.rz * 32 + lz}.mcc"
                payload = ext.read_bytes()
                ctype &= 127
            self.raw[(lx, lz)] = (ctype, payload)
            self.timestamps[(lx, lz)] = int(ts[i])

    def has(self, lx: int, lz: int) -> bool:
        return (lx, lz) in self.raw

    def read_nbt(self, lx: int, lz: int) -> nbtlib.File | None:
        entry = self.raw.get((lx, lz))
        if entry is None:
            return None
        return parse_nbt(decompress(*entry))

    def put_nbt(self, lx: int, lz: int, root: nbtlib.File, timestamp: int = 0) -> None:
        self.raw[(lx, lz)] = (2, zlib.compress(dump_nbt(root), 6))
        if timestamp:
            self.timestamps[(lx, lz)] = timestamp

    def save(self, path: Path | None = None) -> None:
        path = Path(path or self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = np.zeros(1024, dtype=">u4")
        tsh = np.zeros(1024, dtype=">u4")
        body = bytearray()
        sector = 2
        for (lx, lz), (ctype, payload) in sorted(self.raw.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            i = lx + lz * 32
            blob = struct.pack(">IB", len(payload) + 1, ctype) + payload
            ext = path.parent / f"c.{self.rx * 32 + lx}.{self.rz * 32 + lz}.mcc"
            if len(blob) > 255 * SECTOR:
                ext.write_bytes(payload)
                blob = struct.pack(">IB", 1, ctype | 128)
            elif ext.exists():
                ext.unlink()
            n = -(-len(blob) // SECTOR)
            header[i] = (sector << 8) | n
            tsh[i] = self.timestamps.get((lx, lz), 0)
            body += blob + b"\0" * (n * SECTOR - len(blob))
            sector += n
        tmp = path.with_suffix(".mca.tmp")
        with open(tmp, "wb") as f:
            f.write(header.tobytes())
            f.write(tsh.tobytes())
            f.write(body)
        os.replace(tmp, path)


# --------------------------------------------------------------------------
# chunks
# --------------------------------------------------------------------------
@dataclass
class Chunk:
    root: nbtlib.File
    reg: Registry
    arrays: dict[int, np.ndarray] = field(default_factory=dict)  # sy -> (16,16,16) y,z,x ids
    dirty: set[int] = field(default_factory=set)

    def __post_init__(self):
        r = self.root
        if "Level" in r and "sections" not in r:
            raise UnsupportedWorld("pre-1.18 chunk format (Level wrapper) is not supported; "
                                   "open and save the world once in 1.20+ first")
        self.data_version = int(r.get("DataVersion", 0))
        # 1.18+ share the section layout we read/write.  Chunks keep their own
        # DataVersion so the game's DataFixer still upgrades untouched content
        # (e.g. WorldPainter writes 1.18 chunks inside a 1.20.5 level).
        if self.data_version and self.data_version < DV_1_18:
            raise UnsupportedWorld(f"chunk DataVersion {self.data_version} predates the 1.18 "
                                   f"chunk format; open and save the world in 1.20+ first")
        self.min_section = int(r.get("yPos", -4))
        self.max_section = self.min_section + 23  # overworld: 24 sections (y -64..319)
        self.cx = int(r["xPos"])
        self.cz = int(r["zPos"])
        self.sections: dict[int, T.Compound] = {int(s["Y"]): s for s in r.get("sections", [])}

    # ---- decoding --------------------------------------------------------
    def palette_ids(self, sec: T.Compound) -> np.ndarray:
        pal = sec["block_states"]["palette"]
        ids = np.empty(len(pal), dtype=np.uint16)
        for i, e in enumerate(pal):
            props = {str(k): str(v) for k, v in e.get("Properties", {}).items()}
            ids[i] = self.reg.id(format_state(str(e["Name"]), props))
        return ids

    def section_array(self, sy: int, create: bool = False) -> np.ndarray | None:
        a = self.arrays.get(sy)
        if a is not None:
            return a
        sec = self.sections.get(sy)
        if sec is None or "block_states" not in sec:
            if not create:
                return None
            a = np.full((16, 16, 16), AIR, dtype=np.uint16)
        else:
            bs = sec["block_states"]
            pids = self.palette_ids(sec)
            if len(pids) == 1 or "data" not in bs:
                a = np.full((16, 16, 16), pids[0], dtype=np.uint16)
            else:
                data = bs["data"]
                bits = bits_for_blocks(len(pids))
                if -(-4096 // (64 // bits)) != len(data):
                    bits = _bits_from_length(len(data), 4096, bits)
                idx = unpack(data, bits, 4096)
                idx = np.clip(idx, 0, len(pids) - 1)
                a = pids[idx].reshape(16, 16, 16)
        self.arrays[sy] = a
        return a

    def section_range(self) -> tuple[int, int]:
        """Writable section range: the dimension's build height, not just the
        sections present (WorldPainter omits empty sections above terrain)."""
        ys = sorted(self.sections)
        lo = min(ys[0], self.min_section) if ys else self.min_section
        hi = max(ys[-1], self.max_section) if ys else self.max_section
        return lo, hi

    # ---- encoding --------------------------------------------------------
    def mark_dirty(self, sy: int) -> None:
        self.dirty.add(sy)

    def encode(self) -> nbtlib.File:
        if not self.dirty:
            return self.root
        r = self.root
        for sy in sorted(self.dirty):
            a = self.arrays[sy]
            uniq, inv = np.unique(a.reshape(-1), return_inverse=True)
            palette = T.List[T.Compound]()
            for gid in uniq:
                name, props = self.reg.parsed(int(gid))
                entry = T.Compound({"Name": T.String(name)})
                if props:
                    entry["Properties"] = T.Compound({k: T.String(v) for k, v in props.items()})
                palette.append(entry)
            bs = T.Compound({"palette": palette})
            if len(uniq) > 1:
                bs["data"] = T.LongArray(pack(inv.astype(np.int64), bits_for_blocks(len(uniq))))
            sec = self.sections.get(sy)
            if sec is None:
                sec = T.Compound({"Y": T.Byte(sy)})
                sec["biomes"] = self._neighbour_biomes(sy)
                self.sections[sy] = sec
                r.setdefault("sections", T.List[T.Compound]())
                r["sections"].append(sec)
            sec["block_states"] = bs
            for k in ("BlockLight", "SkyLight"):
                if k in sec:
                    del sec[k]
        r["sections"] = T.List[T.Compound](sorted(r["sections"], key=lambda s: int(s["Y"])))
        # Invalidate derived data; the game recomputes both on load.
        if "Heightmaps" in r:
            r["Heightmaps"] = T.Compound()
        r["isLightOn"] = T.Byte(0)
        for sec in r["sections"]:
            for k in ("BlockLight", "SkyLight"):
                if k in sec:
                    del sec[k]
        self._prune_block_entities()
        self.dirty.clear()
        return r

    def _neighbour_biomes(self, sy: int) -> T.Compound:
        best = None
        for y in sorted(self.sections):
            if "biomes" in self.sections[y]:
                if best is None or abs(y - sy) < abs(best - sy):
                    best = y
        if best is not None:
            b = self.sections[best]["biomes"]
            pal = b["palette"]
            if len(pal) == 1:
                return T.Compound({"palette": T.List[T.String]([T.String(pal[0])])})
            # use the most common biome of the nearest section
            bits = bits_for_biomes(len(pal))
            vals = unpack(b["data"], bits, 64) if "data" in b else np.zeros(64, int)
            common = int(np.bincount(np.clip(vals, 0, len(pal) - 1)).argmax())
            return T.Compound({"palette": T.List[T.String]([T.String(pal[common])])})
        return T.Compound({"palette": T.List[T.String]([T.String("minecraft:plains")])})

    def _prune_block_entities(self) -> None:
        bes = self.root.get("block_entities")
        if not bes:
            return
        keep = T.List[T.Compound]()
        for be in bes:
            x, y, z = int(be["x"]), int(be["y"]), int(be["z"])
            sy = y >> 4
            a = self.arrays.get(sy)
            if a is not None and sy in self.sections:
                name = self.reg.parsed(int(a[y & 15, z & 15, x & 15]))[0]
                be_id = str(be.get("id", ""))
                # keep only if the block at that position still plausibly owns it
                if be_id.split(":")[-1] not in name and not _be_matches(be_id, name):
                    continue
            keep.append(be)
        self.root["block_entities"] = keep

    def add_block_entity(self, be: T.Compound) -> None:
        self.root.setdefault("block_entities", T.List[T.Compound]())
        bes = self.root["block_entities"]
        pos = (int(be["x"]), int(be["y"]), int(be["z"]))
        self.root["block_entities"] = T.List[T.Compound](
            [b for b in bes if (int(b["x"]), int(b["y"]), int(b["z"])) != pos] + [be])


def _be_matches(be_id: str, block_name: str) -> bool:
    be = be_id.split(":")[-1]
    blk = block_name.split(":")[-1]
    if be == "sign":
        return blk.endswith("_sign")
    if be == "hanging_sign":
        return blk.endswith("_hanging_sign")
    if be == "banner":
        return blk.endswith("_banner")
    if be == "bed":
        return blk.endswith("_bed")
    if be == "skull":
        return blk.endswith("_skull") or blk.endswith("_head")
    if be == "shulker_box":
        return blk.endswith("shulker_box")
    return be in blk


# --------------------------------------------------------------------------
# world
# --------------------------------------------------------------------------
class World:
    """A Java Edition world directory (overworld only)."""

    def __init__(self, path: str | Path, registry: Registry | None = None):
        self.path = Path(path)
        self.region_dir = self.path / "region"
        if not self.region_dir.is_dir():
            raise FileNotFoundError(f"{self.region_dir} not found; is this a world folder?")
        self.data_version = self._read_data_version()
        self.reg = registry or Registry(self.data_version or 3953)
        if registry is not None and self.data_version:
            registry.data_version = self.data_version
        self._regions: dict[tuple[int, int], RegionFile] = {}

    def _read_data_version(self) -> int:
        ld = self.path / "level.dat"
        if ld.exists():
            try:
                root = nbtlib.load(ld)
                data = root.get("Data", root)
                return int(data.get("DataVersion", 0))
            except Exception:
                pass
        # fall back to the first chunk we can find
        for p in sorted(self.region_dir.glob("r.*.*.mca")):
            rx, rz = map(int, p.stem.split(".")[1:3])
            rf = RegionFile(p, rx, rz)
            for key in rf.raw:
                return int(rf.read_nbt(*key).get("DataVersion", 0))
        return 0

    def region_coords(self) -> list[tuple[int, int]]:
        out = []
        for p in self.region_dir.glob("r.*.*.mca"):
            parts = p.stem.split(".")
            if len(parts) == 3 and p.stat().st_size >= 2 * SECTOR:
                out.append((int(parts[1]), int(parts[2])))
        return sorted(out)

    def region(self, rx: int, rz: int) -> RegionFile:
        rf = self._regions.get((rx, rz))
        if rf is None:
            rf = RegionFile(self.region_dir / f"r.{rx}.{rz}.mca", rx, rz)
            self._regions[(rx, rz)] = rf
        return rf

    def drop_region(self, rx: int, rz: int) -> None:
        self._regions.pop((rx, rz), None)

    def load_chunk(self, cx: int, cz: int) -> Chunk | None:
        rf = self.region(cx >> 5, cz >> 5)
        root = rf.read_nbt(cx & 31, cz & 31)
        if root is None:
            return None
        return Chunk(root, self.reg)

    def bounds_blocks(self) -> tuple[int, int, int, int]:
        """(min_x, min_z, max_x_exclusive, max_z_exclusive) of generated chunks."""
        xs, zs = [], []
        for rx, rz in self.region_coords():
            rf = self.region(rx, rz)
            for lx, lz in rf.raw:
                xs.append(rx * 32 + lx)
                zs.append(rz * 32 + lz)
            self.drop_region(rx, rz)
        if not xs:
            raise UnsupportedWorld("world has no chunks")
        return min(xs) * 16, min(zs) * 16, (max(xs) + 1) * 16, (max(zs) + 1) * 16


def copy_world(src: Path, dst: Path) -> None:
    src, dst = Path(src), Path(dst)
    if dst.exists():
        raise FileExistsError(f"{dst} already exists")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("session.lock"))
