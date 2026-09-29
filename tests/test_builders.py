"""Smoke-test every landmark builder on a synthetic terrain model."""
import numpy as np
import pytest

from atla_builder.blocks import Registry
from atla_builder.buffer import EditBuffer
from atla_builder.geo import GeoRef, register
from atla_builder.locate import Site, load_landmarks
from atla_builder.schem import read_schem, write_schem
from atla_builder.structures.common import BuildContext
from atla_builder.structures.registry import BUILDERS
from atla_builder.terrain import NONE, S_GRASS, S_SAND, TerrainModel


@pytest.fixture(scope="module")
def terrain():
    n = 1800
    x0 = z0 = -900
    X, Z = np.meshgrid(np.arange(n) + x0, np.arange(n) + z0, indexing="ij")
    r = np.hypot(X, Z)
    ground = (62 + 120 * np.exp(-(r / 260) ** 2) + 12 * np.sin(X / 90) * np.cos(Z / 70)).astype(np.int16)
    ground = np.where(X > 600, 30, ground).astype(np.int16)  # sea to the east
    water = np.where(ground < 62, 62, NONE).astype(np.int16)
    surf = np.full((n, n), S_GRASS, np.uint8)
    surf[Z > 500] = S_SAND
    return TerrainModel(x0, z0, ground, ground.copy(), water, surf)


@pytest.mark.parametrize("lm", load_landmarks(), ids=lambda l: l["id"])
def test_builder_runs(terrain, lm):
    reg = Registry(3837)
    x, z = (420, 0) if lm["strategy"] in ("coast", "coast_flat", "sea") else (0, 0)
    path = [(300, -300), (330, 0), (300, 300)] if lm["strategy"] == "path" else None
    site = Site(id=lm["id"], x=x, y=int(terrain.ground_at(x, z)), z=z, facing="east", angle=0.0,
                fit_radius=300, strategy=lm["strategy"], anchor=(x, z), path=path)
    ctx = BuildContext(reg, terrain, site, lm, seed=1)
    BUILDERS[lm["builder"]](ctx)
    assert ctx.struct.count() + ctx.terrain.count() > 0
    assert ctx.pois, "every landmark exposes quest points of interest"
    for p in ctx.pois.values():
        assert -64 <= p["y"] <= 320


def test_schem_roundtrip(tmp_path):
    reg = Registry(3837)
    b = EditBuffer(reg)
    b.box(0, 64, 0, 9, 70, 4, "minecraft:stone_bricks")
    b.set(3, 71, 2, "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    info = write_schem(b, tmp_path / "t.schem", reg, 3837, "t")
    assert info["size"] == [10, 8, 5]
    ids, off = read_schem(tmp_path / "t.schem", reg)
    assert ids.shape == (8, 5, 10)
    assert reg.state(int(ids[0, 0, 0])) == "minecraft:stone_bricks"
    assert "oak_stairs" in reg.state(int(ids[7, 2, 3]))


def test_registration_recovers_transform():
    from atla_builder.reference import land_mask
    ref = land_mask()
    truth = GeoRef(16.0, -4685.0, 16.0, -4045.0)
    cell = 32
    xs = -5120 + (np.arange(320) + 0.5) * cell
    zs = -4480 + (np.arange(280) + 0.5) * cell
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    from atla_builder.geo import sample_ref_land
    world = sample_ref_land(truth, X, Z, ref)
    guess = GeoRef(17.0, -4900.0, 15.2, -3900.0)
    got = register(world, (-5120, -4480), cell, guess, ref)
    assert got.score > 0.95
    assert abs(got.ax - 16) < 0.4 and abs(got.bx + 4685) < 80
