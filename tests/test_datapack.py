"""The Atlas teleport datapack."""
import json


from atla_builder.datapack import book_pages, destinations, write_datapack

LOG = {
    "landmarks": [
        {"id": "southern_water_tribe", "name": "Southern Water Tribe", "nation": "water", "story_tier": 1,
         "center": {"x": -394, "y": 65, "z": 2738},
         "points_of_interest": {"village_center": {"x": -394, "y": 65, "z": 2738},
                                "gran_gran_igloo": {"x": -376, "y": 65, "z": 2744}}},
        {"id": "northern_water_tribe", "name": "NWT", "nation": "water", "story_tier": 1,
         "center": {"x": -250, "y": 96, "z": -3096},
         "points_of_interest": {"tui_and_la_koi": {"x": 1, "y": 2, "z": 3}, "spirit_oasis": {"x": -250, "y": 80, "z": -3166}}},
        {"id": "ba_sing_se", "name": "Ba Sing Se", "nation": "earth", "story_tier": 3,
         "center": {"x": 2438, "y": 84, "z": -1818},
         "points_of_interest": {"earth_kings_palace": {"x": 2438, "y": 97, "z": -1894}}},
    ],
    "settlements": [{"id": "earth_farm_hamlet_001", "kind": "farm_hamlet", "nation": "earth",
                     "center": {"x": 2600, "y": 70, "z": -1700}, "buildings": 4, "pois": {}}],
}


def test_destinations_order_and_filter():
    d = destinations(LOG)
    names = [x["name"] for x in d]
    assert names[0] == "Southern Water Tribe"  # story start first
    assert "Gran Gran's Igloo" in names and "Earth King's Palace" in names
    assert not any("Koi" in n for n in names)  # spawn markers are not destinations
    assert d[-1]["kind"] == "settlement" and "of Ba Sing Se" in d[-1]["name"]
    assert [x["n"] for x in d] == list(range(1, len(d) + 1))


def test_book_components_are_dual_keyed():
    pages = book_pages(destinations(LOG))
    entries = [c for p in pages for c in p["extra"] if "clickEvent" in c]
    assert entries
    for c in entries:
        assert "click_event" in c and "hoverEvent" in c and "hover_event" in c
        if c["clickEvent"]["action"] == "run_command":
            assert c["click_event"]["command"] == c["clickEvent"]["value"]
            assert c["clickEvent"]["value"].startswith("/trigger atla_tp set ")


def test_write_datapack_layout(tmp_path):
    info = write_datapack(LOG, tmp_path)
    root = tmp_path / "atla_atlas"
    mc = json.loads((root / "pack.mcmeta").read_text())
    assert mc["pack"]["pack_format"] == 41
    for plural, singular in (("functions", "function"), ("loot_tables", "loot_table")):
        assert (root / "data/atla" / plural).is_dir() and (root / "data/atla" / singular).is_dir()
    for tag in ("tags/functions", "tags/function"):
        assert json.loads((root / "data/minecraft" / tag / "tick.json").read_text())["values"] == ["atla:tick"]
    load = (root / "data/atla/function/load.mcfunction").read_text()
    assert "x:-393.5d" in load  # block centre of x=-394 (negative coordinates)
    do = (root / "data/atla/function/tp/do.mcfunction").read_text().splitlines()
    assert do[0] == "$tp @s $(x) $(y) $(z)"
    loot = json.loads((root / "data/atla/loot_table/atlas.json").read_text())
    fns = [f["function"] for f in loot["pools"][0]["entries"][0]["functions"]]
    assert fns == ["minecraft:set_book_cover", "minecraft:set_written_book_pages", "minecraft:set_components"]
    assert info["pages"] <= 100


def test_safe_spots_on_real_blocks(tmp_path):
    from atla_builder.anvil import World
    from atla_builder.buffer import EditBuffer, apply_buffers
    from atla_builder.datapack import SafeSpots
    from atla_builder.synth import generate_world

    generate_world(tmp_path, only_bbox=(0, 0, 32, 32), workers=1, log=lambda *a: None)
    w = World(tmp_path)
    b = EditBuffer(w.reg)
    b.box(8, 150, 8, 12, 160, 12, "minecraft:stone")  # a pillar: the point is inside it
    b.box(20, 150, 20, 24, 150, 24, "minecraft:stone")  # a floating platform
    apply_buffers(w, [b], log=lambda *a: None)
    s = SafeSpots(World(tmp_path))
    x, y, z = s.find(10, 155, 10)
    assert not (8 <= x <= 12 and 8 <= z <= 12 and 150 <= y <= 160)  # moved out of the pillar
    assert s.find(22, 151, 22) == (22, 151, 22)  # already standable on the platform
