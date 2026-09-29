"""Block-state registry, classification, version-aware naming and rotation.

Block states are handled as canonical strings, e.g.
``minecraft:oak_stairs[facing=east,half=bottom]``.  Every string gets a small
integer id in a :class:`Registry` so that large volumes can be stored as
``uint16`` numpy arrays.  Id 0 is reserved for "no edit" in edit buffers and
id 1 is always ``minecraft:air``.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

NOOP = 0
AIR = 1

# Data versions of releases whose block ids matter to us.
DV_1_18 = 2860
DV_1_20 = 3463
DV_1_20_3 = 3698  # minecraft:grass -> minecraft:short_grass
DV_1_21 = 3953

# Newest block we rely on is from 1.20 (cherry/bamboo); 1.18 chunk format is
# the hard floor for the Anvil reader/writer.
MIN_SUPPORTED_DATA_VERSION = DV_1_20

_STATE_RE = re.compile(r"^([a-z0-9_.\-]+:)?([a-z0-9_./\-]+)(?:\[(.*)\])?$")


def parse_state(state: str) -> tuple[str, dict[str, str]]:
    """Split ``ns:name[k=v,...]`` into (``ns:name``, {k: v})."""
    m = _STATE_RE.match(state.strip())
    if not m:
        raise ValueError(f"bad block state: {state!r}")
    ns = m.group(1) or "minecraft:"
    props: dict[str, str] = {}
    if m.group(3):
        for part in m.group(3).split(","):
            if not part:
                continue
            k, v = part.split("=", 1)
            props[k.strip()] = v.strip()
    return ns + m.group(2), props


def format_state(name: str, props: dict[str, str] | None = None) -> str:
    if ":" not in name:
        name = "minecraft:" + name
    if not props:
        return name
    inner = ",".join(f"{k}={props[k]}" for k in sorted(props))
    return f"{name}[{inner}]"


def canonical(state: str) -> str:
    name, props = parse_state(state)
    return format_state(name, props)


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------
C_AIR, C_WATER, C_LAVA, C_PLANT, C_LEAVES, C_LOG, C_SNOW_LAYER, C_SOLID = range(8)

_PLANTS = {
    "grass", "short_grass", "tall_grass", "fern", "large_fern", "dead_bush",
    "dandelion", "poppy", "blue_orchid", "allium", "azure_bluet", "red_tulip",
    "orange_tulip", "white_tulip", "pink_tulip", "oxeye_daisy", "cornflower",
    "lily_of_the_valley", "wither_rose", "sunflower", "lilac", "rose_bush",
    "peony", "seagrass", "tall_seagrass", "kelp", "kelp_plant", "sugar_cane",
    "lily_pad", "sweet_berry_bush", "brown_mushroom", "red_mushroom", "vine",
    "glow_lichen", "hanging_roots", "spore_blossom", "moss_carpet",
    "pink_petals", "torchflower", "pitcher_plant", "small_dripleaf",
    "big_dripleaf", "big_dripleaf_stem", "cave_vines", "cave_vines_plant",
    "bamboo", "bamboo_sapling", "cactus", "sea_pickle", "pointed_dripstone",
    "mangrove_propagule", "leaf_litter", "wildflowers", "bush", "firefly_bush",
    "short_dry_grass", "tall_dry_grass", "cactus_flower",
}


@lru_cache(maxsize=None)
def classify_name(name: str) -> int:
    base = name.split(":", 1)[-1]
    if base in ("air", "cave_air", "void_air", "structure_void", "light"):
        return C_AIR
    if base in ("water", "bubble_column"):
        return C_WATER
    if base == "lava":
        return C_LAVA
    if base == "snow":
        return C_SNOW_LAYER
    if base in _PLANTS:
        return C_PLANT
    if base.endswith("_leaves") or base in ("mangrove_roots",):
        return C_LEAVES
    if (base.endswith("_log") or base.endswith("_wood") or base.endswith("_stem")
            or base.endswith("_hyphae")) and not base.startswith("stripped_") \
            and not base.startswith("mushroom"):
        return C_LOG
    if base.endswith("_sapling") or base.endswith("_tulip") or base.endswith("_coral") \
            or base.endswith("_coral_fan") or base.endswith("_mushroom"):
        return C_PLANT
    return C_SOLID


def is_waterlogged(props: dict[str, str]) -> bool:
    return props.get("waterlogged") == "true"


# --------------------------------------------------------------------------
# version-aware names
# --------------------------------------------------------------------------
# (old_name, new_name, first data version that uses new_name)
RENAMES = [
    ("minecraft:grass", "minecraft:short_grass", DV_1_20_3),
    ("minecraft:grass_path", "minecraft:dirt_path", 2566),
]

# Blocks newer than 1.20 that a builder might ask for, with a safe stand-in.
NEWER_BLOCKS = {
    "minecraft:tuff_bricks": ("minecraft:stone_bricks", DV_1_21),
    "minecraft:polished_tuff": ("minecraft:polished_andesite", DV_1_21),
    "minecraft:chiseled_tuff": ("minecraft:chiseled_stone_bricks", DV_1_21),
}


def versioned_name(name: str, data_version: int) -> str:
    for old, new, dv in RENAMES:
        if name == old and data_version >= dv:
            return new
        if name == new and data_version < dv:
            return old
    if name in NEWER_BLOCKS:
        repl, dv = NEWER_BLOCKS[name]
        if data_version < dv:
            return repl
    return name


# --------------------------------------------------------------------------
# rotation
# --------------------------------------------------------------------------
_CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
_SIDE_PROPS = ("north", "east", "south", "west")


def rotate_state(state: str, quarter_turns: int) -> str:
    """Rotate a block state clockwise (seen from above) by 90° steps."""
    q = quarter_turns % 4
    if q == 0:
        return state
    name, props = parse_state(state)
    if not props:
        return state
    out = dict(props)
    for _ in range(q):
        new = dict(out)
        if new.get("facing") in _CW:
            new["facing"] = _CW[new["facing"]]
        if new.get("axis") in ("x", "z"):
            new["axis"] = "z" if new["axis"] == "x" else "x"
        if "rotation" in new and new["rotation"].isdigit():
            new["rotation"] = str((int(new["rotation"]) + 4) % 16)
        if any(p in out for p in _SIDE_PROPS):
            for p in _SIDE_PROPS:
                if p in out:
                    new[_CW[p]] = out[p]
        out = new
    return format_state(name, out)


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
class Registry:
    """Bidirectional map between block-state strings and uint16 ids."""

    def __init__(self, data_version: int = DV_1_21):
        self.data_version = data_version
        self._ids: dict[str, int] = {}
        self._states: list[str] = []
        self._parsed: list[tuple[str, dict[str, str]]] = []
        self._cls: list[int] = []
        self.id("minecraft:structure_void")  # 0: NOOP placeholder
        self.id("minecraft:air")  # 1: AIR
        assert self.id("minecraft:air") == AIR

    def __len__(self) -> int:
        return len(self._states)

    def id(self, state: str) -> int:
        i = self._ids.get(state)
        if i is not None:
            return i
        name, props = parse_state(state)
        name = versioned_name(name, self.data_version)
        key = format_state(name, props)
        i = self._ids.get(key)
        if i is None:
            i = len(self._states)
            if i >= 65535:
                raise OverflowError("too many distinct block states")
            self._ids[key] = i
            self._states.append(key)
            self._parsed.append((name, props))
            self._cls.append(classify_name(name))
        self._ids[state] = i
        return i

    def __call__(self, name: str, **props) -> int:
        return self.id(format_state(name, {k: str(v).lower() if isinstance(v, bool) else str(v)
                                            for k, v in props.items()}))

    def state(self, i: int) -> str:
        return self._states[i]

    def parsed(self, i: int) -> tuple[str, dict[str, str]]:
        return self._parsed[i]

    def classes(self) -> np.ndarray:
        return np.array(self._cls, dtype=np.uint8)

    def lut(self, fn) -> np.ndarray:
        """Boolean lookup table over all current ids."""
        return np.array([bool(fn(self._parsed[i][0], self._parsed[i][1]))
                         for i in range(len(self._states))], dtype=bool)

    def rotation_lut(self, quarter_turns: int) -> np.ndarray:
        n = len(self._states)
        out = np.arange(n, dtype=np.uint16)
        if quarter_turns % 4:
            for i in range(2, n):
                out[i] = self.id(rotate_state(self._states[i], quarter_turns))
        return out

    def mirror_y_lut(self) -> np.ndarray:
        """Flip top/bottom halves (used to hang the Western Air Temple)."""
        n = len(self._states)
        out = np.arange(n, dtype=np.uint16)
        for i in range(2, n):
            name, props = self._parsed[i]
            new = dict(props)
            if props.get("half") in ("top", "bottom") and "stairs" in name:
                new["half"] = "bottom" if props["half"] == "top" else "top"
            if props.get("type") in ("top", "bottom") and name.endswith("_slab"):
                new["type"] = "bottom" if props["type"] == "top" else "top"
            if props.get("facing") in ("up", "down"):
                new["facing"] = "down" if props["facing"] == "up" else "up"
            if name.endswith("lantern"):
                new["hanging"] = "false" if props.get("hanging") == "true" else "true"
            if new != props:
                out[i] = self.id(format_state(name, new))
        return out


def replaceable(name: str, props: dict[str, str]) -> bool:
    return classify_name(name) in (C_AIR, C_WATER, C_PLANT, C_LEAVES, C_SNOW_LAYER)


def is_air(name: str, props: dict[str, str]) -> bool:
    return classify_name(name) == C_AIR
