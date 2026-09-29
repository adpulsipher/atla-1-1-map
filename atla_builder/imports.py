"""Import community builds and place them at a landmark.

Supported sources
-----------------
* Sponge schematics ``.schem`` (v1, v2, v3 - WorldEdit / FAWE)
* Litematica ``.litematic`` (all regions merged)
* Vanilla structure files ``.nbt`` (structure block / ``/place template``)
* A region copied out of a downloaded **world save** (folder or .zip, 1.18+
  chunk format) given its inclusive ``min`` / ``max`` corners

Legacy MCEdit ``.schematic`` files (numeric block ids, pre-1.13) are detected
and rejected with conversion instructions.

Block entities (signs, banners, heads, containers...) are imported and
converted to the target chunk's data version where the format changed
(signs 1.20, banners and heads 1.20.5).  Container contents and entities
(armor stands, item frames, paintings) are not imported.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import tag as T

from .blocks import AIR, NOOP, Registry, format_state, parse_state

VOID = ("minecraft:structure_void",)


class ImportError_(RuntimeError):
    pass


@dataclass
class ImportedBuild:
    ids: np.ndarray                      # [x, y, z]; 0 = not part of the build, AIR = explicit air
    block_entities: list = field(default_factory=list)  # (lx, ly, lz, Compound without x/y/z)
    data_version: int = 0
    source_format: str = ""
    entities_skipped: int = 0
    name: str = ""

    @property
    def size(self):
        return self.ids.shape


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _load_nbt(path: Path):
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return nbtlib.File.parse(io.BytesIO(raw))


def _state_id(reg: Registry, name: str, props: dict) -> int:
    if name in VOID:
        return NOOP
    return reg.id(format_state(name, props))


def _compound_state(reg: Registry, e) -> int:
    props = {str(k): str(v) for k, v in e.get("Properties", {}).items()}
    return _state_id(reg, str(e["Name"]), props)


def decode_varints(data: np.ndarray) -> np.ndarray:
    """Vectorised LEB128 varint decoding (Sponge schematic block data)."""
    b = np.asarray(data, dtype=np.int8).view(np.uint8).astype(np.int64)
    if b.size == 0:
        return b
    last = (b & 0x80) == 0
    ends = np.nonzero(last)[0]
    starts = np.concatenate([[0], ends[:-1] + 1])
    group = np.repeat(np.arange(ends.size), ends - starts + 1)
    pos = np.arange(b.size) - starts[group]
    contrib = (b & 0x7F) << (7 * pos)
    return np.add.reduceat(contrib, starts)


def _unpack_tight(longs, bits: int, count: int) -> np.ndarray:
    """Litematica bit array: entries may span two longs."""
    arr = np.asarray(longs, dtype=np.int64).view(np.uint64)
    arr = np.concatenate([arr, np.zeros(1, np.uint64)])
    idx = np.arange(count, dtype=np.uint64) * np.uint64(bits)
    word = (idx >> np.uint64(6)).astype(np.int64)
    off = (idx & np.uint64(63))
    lo = arr[word] >> off
    spill = off + np.uint64(bits) > np.uint64(64)
    shift_hi = np.where(spill, np.uint64(64) - off, np.uint64(0))
    hi = np.where(spill, arr[word + 1] << shift_hi, np.uint64(0))
    mask = np.uint64((1 << bits) - 1)
    return ((lo | hi) & mask).astype(np.int64)


# --------------------------------------------------------------------------
# format readers
# --------------------------------------------------------------------------
def read_sponge(path: Path, reg: Registry) -> ImportedBuild:
    root = _load_nbt(path)
    sch = root.get("Schematic", root)
    if "Materials" in sch or ("Blocks" in sch and not hasattr(sch["Blocks"], "keys")):
        raise ImportError_(
            f"{Path(path).name} is a legacy MCEdit .schematic (numeric block ids, pre-1.13). Convert it "
            "first: load it with WorldEdit on 1.13+ (//schem load <name>) and save it as Sponge "
            "(//schem save <name> sponge.3), or open it in Amulet and export .schem.")
    version = int(sch.get("Version", 2))
    W, H, L = (int(np.uint16(np.int16(int(sch[k])))) for k in ("Width", "Height", "Length"))
    blocks = sch["Blocks"] if version >= 3 else sch
    pal = blocks["Palette"]
    raw = blocks.get("Data") if version >= 3 else sch.get("BlockData")
    lut = np.zeros(max(int(i) for i in pal.values()) + 1, np.uint16)
    for state, i in pal.items():
        name, props = parse_state(str(state))
        lut[int(i)] = _state_id(reg, name, props)
    vals = decode_varints(raw)
    ids = lut[vals[: W * H * L]].reshape(H, L, W).transpose(2, 0, 1)  # -> [x, y, z]
    bes = []
    be_list = blocks.get("BlockEntities", sch.get("BlockEntities", sch.get("TileEntities", [])))
    for be in be_list or []:
        x, y, z = (int(v) for v in be["Pos"])
        data = be.get("Data", be)  # v3 nests the payload
        c = T.Compound({k: v for k, v in data.items() if k not in ("Pos", "Id", "x", "y", "z")})
        c["id"] = T.String(str(be.get("Id", data.get("id", ""))))
        bes.append((x, y, z, c))
    ents = len(sch.get("Entities", [])) + len(blocks.get("Entities", []) if version >= 3 else [])
    return ImportedBuild(ids, bes, int(sch.get("DataVersion", 0)), f"sponge-v{version}", ents, Path(path).stem)


def read_litematic(path: Path, reg: Registry) -> ImportedBuild:
    root = _load_nbt(path)
    regions = root["Regions"]
    boxes = []
    for name, r in regions.items():
        pos = [int(r["Position"][k]) for k in "xyz"]
        size = [int(r["Size"][k]) for k in "xyz"]
        lo = [p + (s + 1 if s < 0 else 0) for p, s in zip(pos, size)]
        boxes.append((name, r, lo, [abs(s) for s in size]))
    mn = [min(b[2][i] for b in boxes) for i in range(3)]
    mx = [max(b[2][i] + b[3][i] for b in boxes) for i in range(3)]
    ids = np.zeros(tuple(mx[i] - mn[i] for i in range(3)), np.uint16)
    bes, ents = [], 0
    for name, r, lo, (sx, sy, sz) in boxes:
        pal = r["BlockStatePalette"]
        lut = np.array([_compound_state(reg, e) for e in pal], np.uint16)
        bits = max(2, int(math.ceil(math.log2(max(len(pal), 2)))))
        vals = _unpack_tight(r["BlockStates"], bits, sx * sy * sz)
        vals = np.clip(vals, 0, len(pal) - 1)
        block = lut[vals].reshape(sy, sz, sx).transpose(2, 0, 1)
        ox, oy, oz = (lo[i] - mn[i] for i in range(3))
        sub = ids[ox:ox + sx, oy:oy + sy, oz:oz + sz]
        m = block != NOOP
        sub[m] = block[m]
        for be in r.get("TileEntities", []):
            x, y, z = int(be["x"]), int(be["y"]), int(be["z"])
            c = T.Compound({k: v for k, v in be.items() if k not in ("x", "y", "z")})
            bes.append((x + ox, y + oy, z + oz, c))
        ents += len(r.get("Entities", []))
    return ImportedBuild(ids, bes, int(root.get("MinecraftDataVersion", 0)), "litematic", ents, Path(path).stem)


def read_structure_nbt(path: Path, reg: Registry) -> ImportedBuild:
    root = _load_nbt(path)
    sx, sy, sz = (int(v) for v in root["size"])
    pal = root["palette"] if "palette" in root else root["palettes"][0]
    lut = np.array([_compound_state(reg, e) for e in pal], np.uint16)
    ids = np.zeros((sx, sy, sz), np.uint16)
    bes = []
    for b in root["blocks"]:
        x, y, z = (int(v) for v in b["pos"])
        ids[x, y, z] = lut[int(b["state"])]
        if "nbt" in b:
            bes.append((x, y, z, T.Compound(dict(b["nbt"]))))
    return ImportedBuild(ids, bes, int(root.get("DataVersion", 0)), "structure-nbt",
                         len(root.get("entities", [])), Path(path).stem)


def read_world_region(src: Path, reg: Registry, lo, hi, work: Path | None = None) -> ImportedBuild:
    """Copy blocks (and block entities) inside [lo, hi] from another world save."""
    from .anvil import World

    src = Path(src)
    if src.suffix.lower() == ".zip":
        dest = (work or src.parent) / f"_import_{src.stem}"
        if not (dest / ".extracted").exists():
            with zipfile.ZipFile(src) as z:
                z.extractall(dest)
            (dest / ".extracted").write_text("ok", encoding="utf-8")
        cands = [p.parent for p in dest.rglob("level.dat") if (p.parent / "region").is_dir()]
        if not cands:
            raise ImportError_(f"no world save inside {src}")
        src = cands[0]
    w = World(src, reg)
    x0, y0, z0 = (min(a, b) for a, b in zip(lo, hi))
    x1, y1, z1 = (max(a, b) for a, b in zip(lo, hi))
    ids = np.zeros((x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1), np.uint16)
    bes = []
    dv = 0
    for cx in range(x0 >> 4, (x1 >> 4) + 1):
        for cz in range(z0 >> 4, (z1 >> 4) + 1):
            ch = w.load_chunk(cx, cz)
            if ch is None:
                continue
            dv = max(dv, ch.data_version)
            for sy in range(y0 >> 4, (y1 >> 4) + 1):
                a = ch.section_array(sy)
                if a is None:
                    continue
                ax0, ax1 = max(x0, cx * 16), min(x1, cx * 16 + 15)
                az0, az1 = max(z0, cz * 16), min(z1, cz * 16 + 15)
                ay0, ay1 = max(y0, sy * 16), min(y1, sy * 16 + 15)
                sub = a[ay0 - sy * 16:ay1 - sy * 16 + 1, az0 - cz * 16:az1 - cz * 16 + 1,
                        ax0 - cx * 16:ax1 - cx * 16 + 1]
                ids[ax0 - x0:ax1 - x0 + 1, ay0 - y0:ay1 - y0 + 1, az0 - z0:az1 - z0 + 1] = sub.transpose(2, 0, 1)
            for be in ch.root.get("block_entities", []):
                x, y, z = int(be["x"]), int(be["y"]), int(be["z"])
                if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
                    c = T.Compound({k: v for k, v in be.items() if k not in ("x", "y", "z")})
                    bes.append((x - x0, y - y0, z - z0, c))
    return ImportedBuild(ids, bes, dv, "world-region", 0, src.name)


def load_build(spec: dict, reg: Registry, root: Path, work: Path | None = None) -> ImportedBuild:
    """Load the build described by an override spec (paths relative to ``root``)."""
    if "world" in spec:
        return read_world_region(root / spec["world"], reg, spec["min"], spec["max"], work)
    path = root / spec["file"]
    if not path.exists():
        raise ImportError_(f"{path} not found - download the build and place it there")
    suf = path.suffix.lower()
    if suf == ".litematic":
        return read_litematic(path, reg)
    if suf == ".nbt":
        return read_structure_nbt(path, reg)
    if suf in (".schem", ".schematic"):
        return read_sponge(path, reg)
    raise ImportError_(f"unsupported build file type: {path.name}")


# --------------------------------------------------------------------------
# block entity conversion for the target chunk's data version
# --------------------------------------------------------------------------
DV_SIGN_TWO_SIDED = 3440     # 1.20 (23w12a): Text1..4 -> front_text/back_text
DV_COMPONENTS = 3837         # 1.20.5: item components, banner patterns, skull profile
DV_TEXT_NBT = 4325           # 1.21.5: text components stored as NBT instead of JSON strings

BANNER_CODES = {
    "base": "b", "square_bottom_left": "bl", "square_bottom_right": "br", "square_top_left": "tl",
    "square_top_right": "tr", "stripe_bottom": "bs", "stripe_top": "ts", "stripe_left": "ls",
    "stripe_right": "rs", "stripe_center": "cs", "stripe_middle": "ms", "stripe_downright": "drs",
    "stripe_downleft": "dls", "small_stripes": "ss", "cross": "cr", "straight_cross": "sc",
    "triangle_bottom": "bt", "triangle_top": "tt", "triangles_bottom": "bts", "triangles_top": "tts",
    "diagonal_left": "ld", "diagonal_up_right": "rd", "diagonal_up_left": "lud", "diagonal_right": "rud",
    "circle": "mc", "rhombus": "mr", "half_vertical": "vh", "half_horizontal": "hh",
    "half_vertical_right": "vhr", "half_horizontal_bottom": "hhb", "border": "bo", "curly_border": "cbo",
    "gradient": "gra", "gradient_up": "gru", "bricks": "bri", "globe": "glb", "creeper": "cre",
    "skull": "sku", "flower": "flo", "mojang": "moj", "piglin": "pig", "flow": "flw", "guster": "gus",
}
DYES = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray",
        "cyan", "purple", "blue", "brown", "green", "red", "black"]
DROP_KEYS = ("Items", "Book", "RecordItem", "item", "components")


def _nbt_to_py(v):
    if isinstance(v, T.Compound):
        return {str(k): _nbt_to_py(x) for k, x in v.items()}
    if isinstance(v, (T.List, list)):
        return [_nbt_to_py(x) for x in v]
    if isinstance(v, T.String):
        return str(v)
    if isinstance(v, (T.Byte,)) and int(v) in (0, 1):
        return bool(int(v))
    if hasattr(v, "real"):
        return v.real
    return str(v)


def _as_json_text(v) -> str:
    """A sign line in any version's format -> JSON text (pre-1.21.5 storage)."""
    if isinstance(v, T.String):
        s = str(v)
        if s[:1] in ('"', "{", "["):
            return s
        return json.dumps({"text": s})
    return json.dumps(_nbt_to_py(v))


def convert_block_entity(be: T.Compound, source_dv: int, target_dv: int) -> T.Compound | None:
    be = T.Compound(dict(be))
    bid = str(be.get("id", "")).split(":")[-1]
    if not bid:
        return None
    be["id"] = T.String("minecraft:" + bid)
    for k in DROP_KEYS:
        if k in be:
            del be[k]
    if bid in ("sign", "hanging_sign"):
        if target_dv < DV_SIGN_TWO_SIDED and "front_text" in be:
            front = be["front_text"]
            msgs = front.get("messages", [])
            for i in range(4):
                be[f"Text{i + 1}"] = T.String(_as_json_text(msgs[i]) if i < len(msgs) else '""')
            be["Color"] = T.String(str(front.get("color", "black")))
            be["GlowingText"] = T.Byte(int(front.get("has_glowing_text", 0)))
            for k in ("front_text", "back_text", "is_waxed"):
                if k in be:
                    del be[k]
        elif target_dv < DV_TEXT_NBT and "front_text" in be:
            for side in ("front_text", "back_text"):
                if side in be and "messages" in be[side]:
                    be[side]["messages"] = T.List[T.String]([T.String(_as_json_text(m)) for m in be[side]["messages"]])
    if bid == "banner" and target_dv < DV_COMPONENTS and "patterns" in be:
        old = T.List[T.Compound]()
        for p in be["patterns"]:
            code = BANNER_CODES.get(str(p.get("pattern", "")).split(":")[-1])
            color = str(p.get("color", "white"))
            if code and color in DYES:
                old.append(T.Compound({"Pattern": T.String(code), "Color": T.Int(DYES.index(color))}))
        be["Patterns"] = old
        del be["patterns"]
    if bid == "skull" and target_dv < DV_COMPONENTS and "profile" in be:
        prof = be["profile"]
        owner = T.Compound()
        if "name" in prof:
            owner["Name"] = T.String(str(prof["name"]))
        if "id" in prof:
            owner["Id"] = T.IntArray(list(prof["id"]))
        props = prof.get("properties", [])
        tex = [p for p in props if str(p.get("name", "")) == "textures"]
        if tex:
            t = T.Compound({"Value": T.String(str(tex[0]["value"]))})
            if "signature" in tex[0]:
                t["Signature"] = T.String(str(tex[0]["signature"]))
            owner["Properties"] = T.Compound({"textures": T.List[T.Compound]([t])})
        be["SkullOwner"] = owner
        del be["profile"]
    return be


# --------------------------------------------------------------------------
# placement
# --------------------------------------------------------------------------
NEWER_BLOCK_HINTS = ("tuff_brick", "polished_tuff", "chiseled_tuff", "tuff_stairs", "tuff_slab", "tuff_wall",
                     "copper_bulb", "copper_grate", "copper_door", "copper_trapdoor", "chiseled_copper",
                     "crafter", "trial_spawner", "vault", "heavy_core", "pale_oak", "pale_moss", "creaking",
                     "resin", "eyeblossom", "leaf_litter", "wildflowers", "firefly_bush", "cactus_flower",
                     "dry_grass", "dried_ghast", "copper_chest", "copper_golem", "copper_lantern",
                     "copper_torch", "copper_bars", "copper_chain", "iron_chain", "shelf")


def newer_blocks(reg: Registry, ids: np.ndarray) -> list[str]:
    names = sorted({reg.parsed(int(i))[0] for i in np.unique(ids) if i > AIR})
    return [n for n in names if any(h in n for h in NEWER_BLOCK_HINTS)]


def base_layer(ids: np.ndarray) -> int:
    """Lowest local y with any solid block."""
    solid = (ids > AIR).any(axis=(0, 2))
    ys = np.nonzero(solid)[0]
    return int(ys[0]) if ys.size else 0


def place_build(ctx, build: ImportedBuild, spec: dict, at: tuple[int, int] | None = None,
                ground_y: int | None = None) -> dict:
    """Paste ``build`` into ``ctx`` with terrain integration; returns a summary."""
    from .buffer import Canvas
    from .structures.common import TURNS

    reg = ctx.reg
    ids = build.ids
    X, Y, Z = ids.shape
    base = int(spec.get("base_y_local", base_layer(ids)))
    # explicit air below the base would dig holes under the build: drop it
    keep = ids.copy()
    keep[:, :base, :][keep[:, :base, :] == AIR] = NOOP
    facing = spec.get("facing") or {0: "south", 1: "west", 2: "north", 3: "east"}[int(spec.get("rotate", 0)) % 4]
    cx, cz = at if at is not None else (ctx.site.x, ctx.site.z)
    cx += int(spec.get("offset", [0, 0, 0])[0])
    cz += int(spec.get("offset", [0, 0, 0])[2])
    q = TURNS[facing]
    fx, fz = (X, Z) if q % 2 == 0 else (Z, X)
    if ground_y is None:
        g = ctx.field(cx - fx // 2, cz - fz // 2, fx, fz)
        ground_y = int(np.median(g)) if spec.get("y", "auto") == "auto" else int(spec["y"])
    y = ground_y + int(spec.get("y_offset", 0))
    if spec.get("pad", True):
        ctx.level_pad(cx, cz, fx / 2 + 2, fx / 2 + 2 + int(spec.get("blend", 18)), y,
                      rz_in=fz / 2 + 2, square=True)
    cv = Canvas(reg, (X, Y, Z))
    cv.ids[:] = keep
    cv.mode[keep != NOOP] = 1
    pl = ctx.place(cv, cx, cz, y + 1, facing, anchor=(X // 2, base, Z // 2),
                   foundation=spec.get("foundation", "minecraft:stone"), connect=False)
    placed_be = 0
    for (lx, ly, lz, nbt) in build.block_entities:
        wx, wy, wz = pl.to_world(lx, ly, lz)
        src_dv = build.data_version

        def factory(target_dv, nbt=nbt, src_dv=src_dv):
            return convert_block_entity(nbt, src_dv, target_dv)

        ctx.struct.add_block_entity(wx, wy, wz, factory)
        placed_be += 1
    ctx.claim(cx, cz, math.hypot(fx, fz) / 2)
    newer = newer_blocks(reg, keep)
    if newer:
        ctx.notes.append("imported build uses blocks newer than 1.20.5 (need a newer game): " + ", ".join(newer[:12]))
    if build.entities_skipped:
        ctx.notes.append(f"{build.entities_skipped} entities (item frames, armor stands...) not imported")
    ctx.integration.append(f"imported {build.source_format} '{build.name}' {X}x{Y}x{Z} placed at "
                           f"({cx},{y + 1},{cz}) facing {facing}; pad + foundation under the footprint")
    return {"size": [int(X), int(Y), int(Z)], "origin": list(pl.origin), "facing": facing,
            "block_entities": placed_be, "entities_skipped": build.entities_skipped,
            "source_data_version": build.data_version}
