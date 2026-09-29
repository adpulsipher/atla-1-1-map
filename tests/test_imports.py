"""Community-build importers: every format round-trips, block entities convert."""
import gzip
import io
import json

import nbtlib
import numpy as np
import pytest
from nbtlib import tag as T

from atla_builder.blocks import AIR, NOOP, Registry
from atla_builder.buffer import EditBuffer
from atla_builder.imports import (convert_block_entity, decode_varints, load_build, place_build,
                                  read_world_region)
from atla_builder.schem import write_schem

STAIR = "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]"


def _save(root: nbtlib.File, path):
    bio = io.BytesIO()
    root.write(bio)
    path.write_bytes(gzip.compress(bio.getvalue()))


def _expected(reg):
    """A 6x4x5 test build: stone floor, a stair, air above, one void corner."""
    ids = np.full((6, 4, 5), reg.id("minecraft:air"), np.uint16)
    ids[:, 0, :] = reg.id("minecraft:stone_bricks")
    ids[2, 1, 3] = reg.id(STAIR)
    ids[5, 3, 4] = NOOP
    return ids


def test_varints():
    vals = np.array([0, 1, 127, 128, 300, 16383, 16384, 70000])
    enc = []
    for v in vals:
        while True:
            b = v & 0x7F
            v >>= 7
            enc.append(b | (0x80 if v else 0))
            if not v:
                break
    assert np.array_equal(decode_varints(np.array(enc, np.uint8).view(np.int8)), vals)


def test_sponge_v3_roundtrip(tmp_path):
    reg = Registry(3837)
    b = EditBuffer(reg)
    b.box(0, 64, 0, 5, 64, 4, "minecraft:stone_bricks")
    b.set(2, 65, 3, STAIR)
    write_schem(b, tmp_path / "t.schem", reg, 3837, "t")
    build = load_build({"file": "t.schem"}, reg, tmp_path)
    assert build.size == (6, 2, 5)
    assert reg.state(int(build.ids[2, 1, 3])) == reg.state(reg.id(STAIR))
    assert build.source_format == "sponge-v3"


def test_sponge_v2_with_block_entity(tmp_path):
    reg = Registry(3837)
    exp = _expected(reg)
    pal = {}
    flat = []
    for y in range(4):
        for z in range(5):
            for x in range(6):
                i = int(exp[x, y, z])
                st = "minecraft:structure_void" if i == NOOP else reg.state(i)
                flat.append(pal.setdefault(st, len(pal)))
    root = nbtlib.File({"Schematic": T.Compound({
        "Version": T.Int(2), "DataVersion": T.Int(3700), "Width": T.Short(6), "Height": T.Short(4),
        "Length": T.Short(5), "Palette": T.Compound({k: T.Int(v) for k, v in pal.items()}),
        "BlockData": T.ByteArray(np.array(flat, np.int8)),
        "BlockEntities": T.List[T.Compound]([T.Compound({"Pos": T.IntArray([2, 1, 3]),
                                                         "Id": T.String("minecraft:chest"),
                                                         "Items": T.List[T.Compound]()})]),
    })}, root_name="")
    _save(root, tmp_path / "v2.schem")
    build = load_build({"file": "v2.schem"}, reg, tmp_path)
    assert np.array_equal(build.ids, exp)
    assert build.block_entities[0][:3] == (2, 1, 3)


def _pack_tight(vals, bits):
    total = len(vals) * bits
    longs = [0] * ((total + 63) // 64)
    for i, v in enumerate(vals):
        pos = i * bits
        w, o = pos >> 6, pos & 63
        longs[w] |= (v << o) & ((1 << 64) - 1)
        if o + bits > 64:
            longs[w + 1] |= v >> (64 - o)
    return np.array(longs, np.uint64).view(np.int64)


def test_litematic_with_negative_size(tmp_path):
    reg = Registry(3837)
    exp = _expected(reg)
    states = sorted({int(i) for i in exp.ravel()})
    names = ["minecraft:air" if s == NOOP else reg.state(s) for s in states]
    pal = T.List[T.Compound]()
    for n in names:
        from atla_builder.blocks import parse_state
        name, props = parse_state(n)
        c = T.Compound({"Name": T.String(name)})
        if props:
            c["Properties"] = T.Compound({k: T.String(v) for k, v in props.items()})
        pal.append(c)
    index = {s: i for i, s in enumerate(states)}
    vals = [index[int(exp[x, y, z])] for y in range(4) for z in range(5) for x in range(6)]
    bits = max(2, int(np.ceil(np.log2(len(pal)))))
    region = T.Compound({
        # negative size: the region extends toward -x from its position
        "Position": T.Compound({"x": T.Int(5), "y": T.Int(0), "z": T.Int(0)}),
        "Size": T.Compound({"x": T.Int(-6), "y": T.Int(4), "z": T.Int(5)}),
        "BlockStatePalette": pal, "BlockStates": T.LongArray(_pack_tight(vals, bits)),
        "TileEntities": T.List[T.Compound](), "Entities": T.List[T.Compound](),
    })
    root = nbtlib.File({"MinecraftDataVersion": T.Int(3953), "Version": T.Int(6),
                        "Regions": T.Compound({"main": region})}, root_name="")
    _save(root, tmp_path / "b.litematic")
    build = load_build({"file": "b.litematic"}, reg, tmp_path)
    exp_air = exp.copy()
    exp_air[exp_air == NOOP] = AIR  # litematic stores that corner as air
    assert np.array_equal(build.ids, exp_air)


def test_structure_nbt(tmp_path):
    reg = Registry(3837)
    root = nbtlib.File({
        "DataVersion": T.Int(3837), "size": T.List[T.Int]([T.Int(3), T.Int(2), T.Int(3)]),
        "palette": T.List[T.Compound]([T.Compound({"Name": T.String("minecraft:stone")}),
                                       T.Compound({"Name": T.String("minecraft:oak_sign"),
                                                   "Properties": T.Compound({"rotation": T.String("0"),
                                                                             "waterlogged": T.String("false")})})]),
        "blocks": T.List[T.Compound]([
            T.Compound({"pos": T.List[T.Int]([T.Int(0), T.Int(0), T.Int(0)]), "state": T.Int(0)}),
            T.Compound({"pos": T.List[T.Int]([T.Int(1), T.Int(1), T.Int(1)]), "state": T.Int(1),
                        "nbt": T.Compound({"id": T.String("minecraft:sign")})}),
        ]),
        "entities": T.List[T.Compound](),
    }, root_name="")
    _save(root, tmp_path / "s.nbt")
    build = load_build({"file": "s.nbt"}, reg, tmp_path)
    assert reg.state(int(build.ids[0, 0, 0])) == "minecraft:stone"
    assert build.ids[2, 1, 2] == NOOP  # unlisted positions are left untouched
    assert len(build.block_entities) == 1


def test_legacy_schematic_is_rejected_with_help(tmp_path):
    reg = Registry(3837)
    root = nbtlib.File({"Schematic": T.Compound({
        "Width": T.Short(1), "Height": T.Short(1), "Length": T.Short(1), "Materials": T.String("Alpha"),
        "Blocks": T.ByteArray([1]), "Data": T.ByteArray([0])})}, root_name="")
    _save(root, tmp_path / "old.schematic")
    with pytest.raises(Exception, match="legacy MCEdit"):
        load_build({"file": "old.schematic"}, reg, tmp_path)


def test_sign_banner_skull_conversion_for_old_chunks():
    sign = T.Compound({"id": T.String("minecraft:sign"), "front_text": T.Compound({
        "messages": T.List[T.String]([T.String('{"text":"Abandon hope"}'), T.String('""'),
                                      T.String('""'), T.String('""')]),
        "color": T.String("red"), "has_glowing_text": T.Byte(1)})})
    old = convert_block_entity(sign, 3953, 2860)
    assert "front_text" not in old and json.loads(str(old["Text1"]))["text"] == "Abandon hope"
    assert str(old["Color"]) == "red" and int(old["GlowingText"]) == 1
    new121 = T.Compound({"id": T.String("minecraft:sign"), "front_text": T.Compound({
        "messages": T.List[T.String]([T.String("plain"), T.String(""), T.String(""), T.String("")])})})
    assert json.loads(str(convert_block_entity(new121, 4325, 2860)["Text1"])) == {"text": "plain"}
    banner = T.Compound({"id": T.String("minecraft:banner"), "patterns": T.List[T.Compound]([
        T.Compound({"pattern": T.String("minecraft:stripe_bottom"), "color": T.String("red")})])})
    ob = convert_block_entity(banner, 3953, 2860)
    assert str(ob["Patterns"][0]["Pattern"]) == "bs" and int(ob["Patterns"][0]["Color"]) == 14
    chest = T.Compound({"id": T.String("minecraft:chest"), "Items": T.List[T.Compound]()})
    assert "Items" not in convert_block_entity(chest, 3953, 2860)


def test_world_region_import_and_placement(tmp_path):
    from atla_builder.anvil import World
    from atla_builder.buffer import apply_buffers
    from atla_builder.locate import Site
    from atla_builder.structures.common import BuildContext
    from atla_builder.synth import generate_world
    from atla_builder.terrain import NONE, S_GRASS, TerrainModel

    src = tmp_path / "src"
    generate_world(src, only_bbox=(0, 0, 32, 32), workers=1, log=lambda *a: None)
    w = World(src)
    b = EditBuffer(w.reg)
    b.box(4, 120, 4, 8, 124, 8, "minecraft:gold_block")
    apply_buffers(w, [b], log=lambda *a: None)
    reg = Registry(3837)
    build = read_world_region(src, reg, (4, 120, 4), (8, 124, 8))
    assert build.size == (5, 5, 5) and (build.ids == reg.id("minecraft:gold_block")).all()
    # place it on flat synthetic terrain in core-less replace mode
    n = 200
    g = np.full((n, n), 70, np.int16)
    tm = TerrainModel(-100, -100, g, g.copy(), np.full((n, n), NONE, np.int16), np.full((n, n), S_GRASS, np.uint8))
    site = Site("x", 0, 70, 0, "south", 0.0, 50, "flat", (0, 0))
    ctx = BuildContext(reg, tm, site, {"id": "x", "footprint_r": 20})
    info = place_build(ctx, build, {"rotate": 1})
    assert info["facing"] == "west" and info["size"] == [5, 5, 5]
    assert ctx.struct.count() >= 125


def test_core_mode_swaps_in_community_palace(tmp_path):
    from atla_builder.locate import Site, load_landmarks
    from atla_builder.pipeline import build_with_override
    from atla_builder.structures.common import BuildContext
    from atla_builder.terrain import NONE, S_GRASS, TerrainModel

    reg = Registry(3837)
    b = EditBuffer(reg)
    b.box(0, 64, 0, 40, 64, 30, "minecraft:gold_block")  # stand-in "palace"
    b.box(0, 65, 0, 40, 70, 30, "minecraft:red_concrete", hollow=True)
    write_schem(b, tmp_path / "palace.schem", reg, 3837, "palace")
    n = 1600
    X, Z = np.meshgrid(np.arange(n) - 800, np.arange(n) - 800, indexing="ij")
    g = (80 + 170 * np.exp(-(np.hypot(X, Z) / 300) ** 2)).astype(np.int16)
    tm = TerrainModel(-800, -800, g, g.copy(), np.full((n, n), NONE, np.int16), np.full((n, n), S_GRASS, np.uint8))
    lm = {l["id"]: l for l in load_landmarks()}["fire_nation_capital"]
    site = Site(lm["id"], 0, int(g[800, 800]), 0, "south", 0.0, 400, "peak", (0, 0))
    ctx = BuildContext(reg, tm, site, lm, seed=1)
    spec = {"mode": "core", "core_poi": "fire_lord_palace", "file": "palace.schem"}
    info = build_with_override(ctx, lm, spec, tmp_path, lambda *a: None, root=tmp_path)
    assert info["size"] == [41, 7, 31]
    poi = ctx.pois["fire_lord_palace"]
    gold = reg.id("minecraft:gold_block")
    found = any((ids == gold).any() for xs, ys, zs, ids, _ in ctx.struct.iter_voxels()
                if ((abs(xs - poi["x"]) < 25) & (abs(zs - poi["z"]) < 20)).any())
    assert found, "community palace present at the palace POI"
    assert "royal_plaza" in ctx.pois, "procedural surroundings kept"
