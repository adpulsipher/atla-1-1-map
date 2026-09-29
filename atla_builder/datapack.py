"""The Atlas: an item that opens a teleport menu (vanilla datapack).

The item is a glowing written book, "Atlas of the Four Nations".  Its pages
list every landmark (grouped by nation), each landmark's points of interest,
and the settlements.  Clicking an entry runs ``/trigger atla_tp set <n>``,
which works for every player without cheats; the datapack then teleports the
player with a macro function.

Every player receives an Atlas on first join; ``/trigger atla_atlas``
gives another copy.

Compatibility (Java 1.20.5 and newer):
* folders exist in both the pre-1.21 plural (``functions``, ``loot_tables``)
  and the 1.21+ singular (``function``, ``loot_table``) spellings,
* text components carry both the pre-1.21.5 keys (``clickEvent``/``value``)
  and the 1.21.5+ keys (``click_event``/``command``); each version reads the
  keys it knows and ignores the others,
* teleports use function macros (1.20.2+).
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from .blocks import C_AIR, C_LAVA, C_PLANT, C_SNOW_LAYER, C_WATER, classify_name

PACK = "atla_atlas"
NS = "atla"
BOOK_TITLE = "Atlas of the Four Nations"
LINE_CHARS = 19
LINES_PER_PAGE = 13

NATION_ORDER = [("water", "Water Tribes", "dark_aqua"), ("air", "Air Nomads", "gold"),
                ("earth", "Earth Kingdom", "dark_green"), ("fire", "Fire Nation", "dark_red")]
NATION_COLOR = {k: c for k, _, c in NATION_ORDER}

# where to arrive for each landmark (first POI that exists, else the centre)
ARRIVAL = {
    "southern_water_tribe": ["village_center"], "northern_water_tribe": ["chief_palace"],
    "foggy_swamp": ["banyan_tree_heart"], "southern_air_temple": ["temple_plaza"],
    "northern_air_temple": ["temple_plaza"], "eastern_air_temple": ["temple_plaza"],
    "western_air_temple": ["rim_entrance"], "kyoshi_island": ["harbour_pier", "kyoshi_warriors_dojo"],
    "omashu": ["city_gate"], "senlin_village": ["village_square"], "great_divide": ["canyon_ranger_station"],
    "gaoling": ["market_square"], "serpents_pass": ["pass_entrance_sign"], "ba_sing_se": ["outer_wall_south_gate"],
    "full_moon_bay": ["ferry_terminal"], "wan_shi_tong_library": ["library_tower_top"],
    "misty_palms_oasis": ["misty_palms_inn"], "si_wong_rock": ["rock_shelter"], "wulong_forest": ["forest_center"],
    "crescent_island": ["fire_temple_entrance"], "sun_warriors": ["dancing_dragon_plaza"],
    "boiling_rock": ["gondola_rim_station"], "ember_island": ["ember_island_beach"],
    "fire_nation_capital": ["royal_plaza"],
}
SHORT = {
    "southern_water_tribe": "Southern Water Tribe", "northern_water_tribe": "Northern Water Tribe",
    "foggy_swamp": "Foggy Swamp", "southern_air_temple": "Southern Air Temple",
    "northern_air_temple": "Northern Air Temple", "eastern_air_temple": "Eastern Air Temple",
    "western_air_temple": "Western Air Temple", "kyoshi_island": "Kyoshi Island", "omashu": "Omashu",
    "senlin_village": "Senlin Village", "great_divide": "The Great Divide", "gaoling": "Gaoling",
    "serpents_pass": "Serpent's Pass", "ba_sing_se": "Ba Sing Se", "full_moon_bay": "Full Moon Bay",
    "wan_shi_tong_library": "Wan Shi Tong's Library", "misty_palms_oasis": "Misty Palms Oasis",
    "si_wong_rock": "Si Wong Rock", "wulong_forest": "Wulong Forest", "crescent_island": "Crescent Island",
    "sun_warriors": "Sun Warrior Ruins", "boiling_rock": "The Boiling Rock", "ember_island": "Ember Island",
    "fire_nation_capital": "Fire Nation Capital",
}
# spawn markers for the mod, not places to stand
NOT_DESTINATIONS = {"tui_and_la_koi", "serpent_lair"}
KIND_LABEL = {"farm_hamlet": "Farm hamlet", "market_village": "Market village", "watchtower_post": "Watchtower",
              "fire_village": "Village", "fire_outpost": "Army outpost", "igloo_camp": "Igloo camp",
              "air_shrine": "Air shrine"}


LABEL_FIX = {
    "Earth Kings Palace": "Earth King's Palace", "Fire Lord Palace": "Fire Lord's Palace",
    "King Bumi Palace": "King Bumi's Palace", "Dragon Masters Cave": "Dragon Masters' Cave",
    "Gran Gran Igloo": "Gran Gran's Igloo", "Chief Palace": "Chief Arnook's Palace",
    "Aang Iceberg": "Aang's Iceberg", "Kyoshi Warriors Dojo": "Kyoshi Warriors' Dojo",
    "Guru Pathik Ledge": "Guru Pathik's Ledge", "Warden Tower": "Warden's Tower",
    "Harbour Water Gate": "Harbour Water Gate", "Laogai Prison Cells": "Lake Laogai Cells",
}


def _label(poi: str) -> str:
    small = {"of", "the", "and", "to", "on", "in"}
    words = poi.replace("_", " ").split()
    s = " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(words))
    s = s.replace("Mail Chute 1 Top", "Mail Chute 1").replace("Mail Chute 2 Top", "Mail Chute 2") \
         .replace("Mail Chute 3 Top", "Mail Chute 3")
    return LABEL_FIX.get(s, s)


def _direction(dx: float, dz: float) -> str:
    ang = (math.degrees(math.atan2(-dz, dx)) + 360) % 360  # 0 = east, counter-clockwise, z south
    names = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    return names[int((ang + 22.5) // 45) % 8]


# --------------------------------------------------------------------------
# safe arrival points
# --------------------------------------------------------------------------
class SafeSpots:
    """Move each requested point to the nearest standable spot in the world."""

    def __init__(self, world):
        self.world = world
        self._chunks: dict = {}

    def _col(self, x: int, z: int, y0: int, y1: int) -> list[int]:
        key = (x >> 4, z >> 4)
        ch = self._chunks.get(key)
        if ch is None:
            ch = self.world.load_chunk(*key)
            self._chunks[key] = ch
        out = []
        for y in range(y0, y1 + 1):
            if ch is None:
                out.append(C_AIR)
                continue
            a = ch.section_array(y >> 4)
            if a is None:
                out.append(C_AIR)
            else:
                out.append(classify_name(self.world.reg.parsed(int(a[y & 15, z & 15, x & 15]))[0]))
        return out

    def _standable(self, x: int, y: int, z: int) -> bool:
        free = (C_AIR, C_PLANT, C_SNOW_LAYER)
        below, feet, head = self._col(x, z, y - 1, y + 1)
        return below not in free and below not in (C_WATER, C_LAVA) and feet in free and head in free

    def find(self, x: int, y: int, z: int) -> tuple[int, int, int]:
        """Nearest spot a player can stand: a few blocks down, then sideways on
        the same level (out of a statue, wall or well), then further down
        (room and cave floors), then upward, finally the column top."""
        y = max(-62, min(317, y))
        for d in range(0, 4):
            if self._standable(x, y - d, z):
                return x, y - d, z
            if d <= 2 and self._standable(x, y + d, z):
                return x, y + d, z
        for r in range(1, 25):
            ring = [(x + dx, z + dz) for dx in range(-r, r + 1) for dz in (-r, r)] + \
                   [(x + dx, z + dz) for dx in (-r, r) for dz in range(-r + 1, r)]
            for (px, pz) in ring:
                for dy in (0, -1, 1, -2, 2, -3, 3):
                    if self._standable(px, y + dy, pz):
                        return px, y + dy, pz
        for d in range(4, 17):
            if self._standable(x, y - d, z):
                return x, y - d, z
        for d in range(3, 60):
            if y + d <= 317 and self._standable(x, y + d, z):
                return x, y + d, z
        for yy in range(317, -62, -1):
            if self._standable(x, yy, z):
                return x, yy, z
        return x, y, z


# --------------------------------------------------------------------------
# destinations
# --------------------------------------------------------------------------
def destinations(log: dict, spots: SafeSpots | None = None) -> list[dict]:
    """Ordered teleport targets: landmarks, their POIs, then settlements."""
    out: list[dict] = []

    def add(kind, name, nation, x, y, z, group, parent=None):
        if spots is not None:
            x, y, z = spots.find(int(x), int(y), int(z))
        out.append({"n": len(out) + 1, "kind": kind, "name": name, "nation": nation, "x": int(x), "y": int(y),
                    "z": int(z), "group": group, "parent": parent})

    lms = {e["id"]: e for e in log["landmarks"]}
    story = [e["id"] for e in log["landmarks"]]  # the log is in story order
    order = sorted(lms.values(), key=lambda e: ([k for k, *_ in NATION_ORDER].index(e["nation"]),
                                                story.index(e["id"])))
    for e in order:
        pois = e.get("points_of_interest", {})
        arrive = next((pois[p] for p in ARRIVAL.get(e["id"], []) if p in pois), None) or e["center"]
        name = SHORT.get(e["id"], e["name"])
        add("landmark", name, e["nation"], arrive["x"], arrive["y"], arrive["z"], e["nation"])
        for pid, p in pois.items():
            if pid in NOT_DESTINATIONS or pid in ARRIVAL.get(e["id"], [])[:1]:
                continue
            add("poi", _label(pid), e["nation"], p["x"], p["y"], p["z"], e["nation"], parent=name)
    for s in sorted(log.get("settlements", []), key=lambda s: ([k for k, *_ in NATION_ORDER].index(s["nation"]), s["id"])):
        c = s["center"]
        near = min(lms.values(), key=lambda e: (e["center"]["x"] - c["x"]) ** 2 + (e["center"]["z"] - c["z"]) ** 2)
        d = math.hypot(near["center"]["x"] - c["x"], near["center"]["z"] - c["z"])
        where = f"{_direction(c['x'] - near['center']['x'], c['z'] - near['center']['z'])} of {SHORT.get(near['id'], near['name'])}"
        name = f"{KIND_LABEL.get(s['kind'], s['kind'])}, {where}" if d < 1500 else KIND_LABEL.get(s["kind"], s["kind"])
        add("settlement", name, s["nation"], c["x"], c["y"], c["z"], "villages_" + s["nation"])
    return out


# --------------------------------------------------------------------------
# text components (dual-keyed for 1.20.5 - 1.21.4 and 1.21.5+)
# --------------------------------------------------------------------------
def _click_cmd(cmd: str) -> dict:
    return {"clickEvent": {"action": "run_command", "value": cmd},
            "click_event": {"action": "run_command", "command": cmd}}


def _click_page(page: int) -> dict:
    return {"clickEvent": {"action": "change_page", "value": str(page)},
            "click_event": {"action": "change_page", "page": page}}


def _hover(text: str) -> dict:
    return {"hoverEvent": {"action": "show_text", "contents": text},
            "hover_event": {"action": "show_text", "value": text}}


def _lines(text: str) -> int:
    return max(1, math.ceil(len(text) / LINE_CHARS))


def book_pages(dests: list[dict]) -> list[list[dict]]:
    """Paginate the menu; returns a list of pages (each a list of components)."""
    sections: list[tuple[str, str, list[dict]]] = []
    for key, title, color in NATION_ORDER:
        items = [d for d in dests if d["group"] == key]
        if items:
            sections.append((title, color, items))
    for key, title, color in NATION_ORDER:
        items = [d for d in dests if d["group"] == "villages_" + key]
        if items:
            sections.append((f"{title} villages", color, items))
    pages: list[list[dict]] = []
    starts: list[int] = []
    for title, color, items in sections:
        page: list[dict] = [{"text": title + "\n", "bold": True, "color": color, "underlined": True}]
        used = _lines(title) + 1
        starts.append(len(pages) + 2)  # page 1 is the index
        for d in items:
            if d["kind"] == "landmark":
                text = "▶ " + d["name"]
                comp = {"text": text + "\n", "bold": True, "color": color}
            elif d["kind"] == "poi":
                text = "  • " + d["name"]
                comp = {"text": text + "\n", "color": "black"}
            else:
                text = "• " + d["name"]
                comp = {"text": text + "\n", "color": "black"}
            n = _lines(text)
            if used + n > LINES_PER_PAGE:
                pages.append(page)
                page = [{"text": title + " (cont.)\n", "color": color, "italic": True}]
                used = _lines(title + " (cont.)")
            comp.update(_click_cmd(f"/trigger atla_tp set {d['n']}"))
            comp.update(_hover(f"Teleport to {d['name']}\n{d['x']} {d['y']} {d['z']}"))
            page.append(comp)
            used += n
        pages.append(page)
    # wrap each page so entries don't inherit the first entry's style
    pages = [{"text": "", "extra": p} for p in pages]
    index = [{"text": "Atlas of the\nFour Nations\n", "bold": True, "color": "dark_purple"},
             {"text": "Click a place to travel there.\n\n", "color": "gray", "italic": True}]
    for (title, color, _), start in zip(sections, starts):
        comp = {"text": "» " + title + "\n", "color": color}
        comp.update(_click_page(start))
        comp.update(_hover(f"Go to page {start}"))
        index.append(comp)
    return [{"text": "", "extra": index}] + pages


# --------------------------------------------------------------------------
# datapack files
# --------------------------------------------------------------------------
def _write(root: Path, rel_plural: str, rel_singular: str, name: str, text: str) -> None:
    for rel in (rel_plural, rel_singular):
        p = root / "data" / rel / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def _snbt_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_datapack(log: dict, out_dir: Path, world=None) -> dict:
    """Write the Atlas datapack to ``out_dir/atla_atlas``; returns a summary."""
    root = Path(out_dir) / PACK
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    spots = SafeSpots(world) if world is not None else None
    dests = destinations(log, spots)
    pages = book_pages(dests)
    if len(pages) > 100:
        raise ValueError(f"{len(pages)} book pages exceed the 100-page limit")
    (root / "pack.mcmeta").write_text(json.dumps({"pack": {
        "description": "ATLA world: the Atlas teleport menu (/trigger atla_atlas for a copy)",
        "pack_format": 41, "supported_formats": {"min_inclusive": 41, "max_inclusive": 1000},
        "min_format": 41, "max_format": 1000}}, indent=2), encoding="utf-8")
    loot = {"pools": [{"rolls": 1, "entries": [{
        "type": "minecraft:item", "name": "minecraft:written_book", "functions": [
            {"function": "minecraft:set_book_cover", "title": BOOK_TITLE[:32], "author": "Four Nations",
             "generation": 0},
            {"function": "minecraft:set_written_book_pages", "mode": "replace_all", "pages": pages},
            {"function": "minecraft:set_components",
             "components": {"minecraft:enchantment_glint_override": True}},
        ]}]}]}
    _write(root, f"{NS}/loot_tables", f"{NS}/loot_table", "atlas.json", json.dumps(loot, ensure_ascii=False))
    _write(root, "minecraft/tags/functions", "minecraft/tags/function", "load.json",
           json.dumps({"values": [f"{NS}:load"]}))
    _write(root, "minecraft/tags/functions", "minecraft/tags/function", "tick.json",
           json.dumps({"values": [f"{NS}:tick"]}))
    store = "\n".join(
        f"data modify storage {NS}:dests d{d['n']} set value {{x:{d['x'] + 0.5}d,y:{d['y']},z:{d['z'] + 0.5}d,"
        f"name:{_snbt_str(d['name'])}}}" for d in dests)
    fn = {
        "load.mcfunction": "\n".join([
            "scoreboard objectives add atla_tp trigger",
            "scoreboard objectives add atla_atlas trigger",
            store, ""]),
        "tick.mcfunction": "\n".join([
            "scoreboard players enable @a atla_tp",
            "scoreboard players enable @a atla_atlas",
            "execute as @a[tag=!atla_has_atlas] run function atla:give_atlas",
            "execute as @a[scores={atla_atlas=1..}] run function atla:give_atlas",
            "execute as @a[scores={atla_tp=1..}] at @s run function atla:tp/go", ""]),
        "give_atlas.mcfunction": "\n".join([
            "loot give @s loot atla:atlas",
            "tag @s add atla_has_atlas",
            "scoreboard players set @s atla_atlas 0",
            'tellraw @s {"text":"You carry the Atlas of the Four Nations - open it to travel. '
            '(/trigger atla_atlas for another copy)","color":"gold"}', ""]),
        "tp/go.mcfunction": "\n".join([
            f"execute store result storage {NS}:tmp i int 1 run scoreboard players get @s atla_tp",
            f"function atla:tp/lookup with storage {NS}:tmp",
            "scoreboard players set @s atla_tp 0", ""]),
        "tp/lookup.mcfunction": f"$function atla:tp/do with storage {NS}:dests d$(i)\n",
        "tp/do.mcfunction": "\n".join([
            "$tp @s $(x) $(y) $(z)",
            "effect give @s minecraft:slow_falling 3 0 true",
            '$title @s actionbar {"text":"$(name)","color":"gold"}', ""]),
    }
    for name, text in fn.items():
        _write(root, f"{NS}/functions", f"{NS}/function", name, text)
    (root / "destinations.json").write_text(json.dumps(dests, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"path": str(root), "destinations": len(dests), "pages": len(pages)}
