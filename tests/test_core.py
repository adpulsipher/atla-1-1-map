import numpy as np
import pytest

from atla_builder.anvil import Chunk, RegionFile, World, bits_for_blocks, pack, unpack
from atla_builder.blocks import Registry, parse_state, rotate_state, versioned_name
from atla_builder.buffer import SOFT, Canvas, EditBuffer, apply_buffers
from atla_builder.structures.common import Placement, TURNS, rot2d
from atla_builder.synth import generate_world


@pytest.mark.parametrize("bits", [4, 5, 7, 9, 12])
def test_pack_roundtrip(bits):
    rng = np.random.default_rng(bits)
    vals = rng.integers(0, 1 << bits, 4096)
    assert np.array_equal(unpack(pack(vals, bits), bits, 4096), vals)


def test_bits_for_blocks():
    assert bits_for_blocks(1) == 0
    assert bits_for_blocks(2) == 4
    assert bits_for_blocks(17) == 5
    assert bits_for_blocks(300) == 9


def test_rotation_of_states():
    s = "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
    assert parse_state(rotate_state(s, 1))[1]["facing"] == "east"
    assert parse_state(rotate_state(s, 2))[1]["facing"] == "south"
    assert parse_state(rotate_state("minecraft:oak_log[axis=x]", 1))[1]["axis"] == "z"
    fence = "minecraft:oak_fence[east=false,north=true,south=false,west=false,waterlogged=false]"
    assert parse_state(rotate_state(fence, 1))[1]["east"] == "true"


def test_versioned_names():
    assert versioned_name("minecraft:grass", 3837) == "minecraft:short_grass"
    assert versioned_name("minecraft:short_grass", 3000) == "minecraft:grass"


def test_canvas_rotation_matches_placement():
    reg = Registry()
    for facing, q in TURNS.items():
        c = Canvas(reg, (9, 3, 5))
        c.set(2, 1, 4, "minecraft:stone")
        rc = c.rotated(q)
        xs, ys, zs = np.nonzero(rc.ids)
        assert (int(xs[0]), int(ys[0]), int(zs[0])) == Placement(q, (9, 3, 5), (0, 0, 0)).to_world(2, 1, 4)
        a = np.zeros((9, 5), bool)
        a[2, 4] = True
        ra = rot2d(a, q)
        assert ra[xs[0], zs[0]]


def test_editbuffer_box_and_columns():
    reg = Registry()
    b = EditBuffer(reg)
    b.box(-3, 60, -3, 20, 70, 17, "minecraft:stone")
    assert b.count() == 24 * 11 * 21
    lo = np.full((5, 5), 10)
    hi = np.full((5, 5), 13)
    b2 = EditBuffer(reg)
    b2.fill_columns(30, 30, lo, hi, "minecraft:dirt")
    assert b2.count() == 5 * 5 * 3


def test_connect_fences():
    reg = Registry()
    c = Canvas(reg, (5, 2, 5))
    c.box(0, 0, 2, 4, 0, 2, "minecraft:oak_fence")
    c.connect()
    name, props = reg.parsed(int(c.ids[2, 0, 2]))
    assert props["east"] == "true" and props["west"] == "true" and props["north"] == "false"


@pytest.fixture(scope="module")
def tiny_world(tmp_path_factory):
    d = tmp_path_factory.mktemp("w")
    generate_world(d, bounds=(-4500, -3500, 4500, 3500), only_bbox=(0, 0, 32, 32), workers=1, log=lambda *a: None)
    return d


def test_world_roundtrip_and_apply(tiny_world):
    w = World(tiny_world)
    assert w.data_version > 0
    ch = w.load_chunk(0, 0)
    assert isinstance(ch, Chunk)
    buf = EditBuffer(w.reg)
    buf.box(2, 100, 2, 6, 104, 6, "minecraft:gold_block")
    soft = EditBuffer(w.reg)  # SOFT writes only replace air/fluids/plants in the world
    soft.box(2, 100, 2, 6, 100, 6, "minecraft:diamond_block", mode=SOFT)
    soft.box(2, 110, 2, 2, 110, 2, "minecraft:diamond_block", mode=SOFT)
    stats = apply_buffers(w, [buf, soft], log=lambda *a: None)
    assert stats["blocks"] == 125 + 1
    w2 = World(tiny_world)
    ch2 = w2.load_chunk(0, 0)
    assert str(ch2.root["Status"]).endswith("full")
    arr = ch2.section_array(100 >> 4)
    assert w2.reg.state(int(arr[100 & 15, 3, 3])) == "minecraft:gold_block"
    assert w2.reg.state(int(ch2.section_array(110 >> 4)[110 & 15, 2, 2])) == "minecraft:diamond_block"
    # every chunk in the rewritten region still parses
    rf = RegionFile(tiny_world / "region" / "r.0.0.mca", 0, 0)
    for key in rf.raw:
        Chunk(rf.read_nbt(*key), Registry())


def test_writes_above_missing_sections(tiny_world):
    """WorldPainter omits empty upper sections; edits there must still land."""
    w = World(tiny_world)
    rf = w.region(0, 0)
    root = rf.read_nbt(1, 1)
    from nbtlib import tag as T
    root["sections"] = T.List[T.Compound]([s for s in root["sections"] if int(s["Y"]) <= 4])
    rf.put_nbt(1, 1, root)
    rf.save()
    w = World(tiny_world)
    buf = EditBuffer(w.reg)
    buf.box(20, 250, 20, 21, 251, 21, "minecraft:gold_block")
    stats = apply_buffers(w, [buf], log=lambda *a: None)
    assert stats["blocks"] == 8
    ch = World(tiny_world).load_chunk(1, 1)
    assert 250 >> 4 in ch.sections
    a = ch.section_array(250 >> 4)
    assert "gold_block" in w.reg.state(int(a[250 & 15, 20 & 15, 20 & 15]))
