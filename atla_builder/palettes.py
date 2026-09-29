"""Nation material palettes, chosen to match the animated series' colour keys.

Air Nomads   off-white stone, turquoise conical roofs, gold finials/symbols
Earth King.  cream/tan plaster & grey-tan stone, deep green (jade) tile roofs
Fire Nation  red walls & pillars, dark-red tile roofs, black stone, gold trim
Water Tribes snow, packed/blue ice, white & blue accents, hide tents (brown)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    wall: str
    wall_alt: str
    trim: str
    post: str  # vertical frame / pillar (log-like, axis=y)
    floor: str
    foundation: str
    roof: str  # full block
    roof_stairs: str
    roof_slab: str
    ridge: str
    window: str
    door_frame: str
    accent: str
    light: str
    fence: str


AIR = Palette(
    name="air", wall="minecraft:calcite", wall_alt="minecraft:smooth_quartz",
    trim="minecraft:smooth_sandstone", post="minecraft:quartz_pillar[axis=y]",
    floor="minecraft:polished_diorite", foundation="minecraft:stone_bricks",
    roof="minecraft:oxidized_cut_copper", roof_stairs="minecraft:oxidized_cut_copper_stairs",
    roof_slab="minecraft:oxidized_cut_copper_slab", ridge="minecraft:gold_block",
    window="minecraft:air", door_frame="minecraft:smooth_sandstone", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:birch_fence",
)

EARTH = Palette(
    name="earth", wall="minecraft:smooth_sandstone", wall_alt="minecraft:white_terracotta",
    trim="minecraft:stripped_spruce_log[axis=y]", post="minecraft:stripped_spruce_log[axis=y]",
    floor="minecraft:spruce_planks", foundation="minecraft:stone_bricks",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:prismarine_bricks",
    window="minecraft:spruce_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:spruce_planks", accent="minecraft:gold_block",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:spruce_fence",
)

EARTH_POOR = Palette(
    name="earth_poor", wall="minecraft:packed_mud", wall_alt="minecraft:mud_bricks",
    trim="minecraft:stripped_oak_log[axis=y]", post="minecraft:oak_log[axis=y]",
    floor="minecraft:coarse_dirt", foundation="minecraft:cobblestone",
    roof="minecraft:dark_prismarine", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:dark_prismarine",
    window="minecraft:oak_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:oak_planks", accent="minecraft:hay_block[axis=y]",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:oak_fence",
)

EARTH_RURAL = Palette(  # thatched farm cottages between cities
    name="earth_rural", wall="minecraft:packed_mud", wall_alt="minecraft:oak_planks",
    trim="minecraft:oak_log[axis=y]", post="minecraft:oak_log[axis=y]",
    floor="minecraft:oak_planks", foundation="minecraft:cobblestone",
    roof="minecraft:hay_block[axis=y]", roof_stairs="minecraft:dark_prismarine_stairs",
    roof_slab="minecraft:dark_prismarine_slab", ridge="minecraft:hay_block[axis=x]",
    window="minecraft:oak_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:oak_planks", accent="minecraft:hay_block[axis=y]",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:oak_fence",
)

FIRE = Palette(
    name="fire", wall="minecraft:red_terracotta", wall_alt="minecraft:red_concrete",
    trim="minecraft:polished_blackstone", post="minecraft:stripped_crimson_stem[axis=y]",
    floor="minecraft:polished_blackstone_bricks", foundation="minecraft:polished_blackstone_bricks",
    roof="minecraft:red_nether_bricks", roof_stairs="minecraft:red_nether_brick_stairs",
    roof_slab="minecraft:red_nether_brick_slab", ridge="minecraft:gold_block",
    window="minecraft:black_stained_glass_pane", door_frame="minecraft:polished_blackstone",
    accent="minecraft:gold_block", light="minecraft:lantern[hanging=false,waterlogged=false]",
    fence="minecraft:nether_brick_fence",
)

FIRE_COMMON = Palette(
    name="fire_common", wall="minecraft:white_terracotta", wall_alt="minecraft:red_terracotta",
    trim="minecraft:dark_oak_log[axis=y]", post="minecraft:dark_oak_log[axis=y]",
    floor="minecraft:dark_oak_planks", foundation="minecraft:polished_blackstone_bricks",
    roof="minecraft:red_nether_bricks", roof_stairs="minecraft:red_nether_brick_stairs",
    roof_slab="minecraft:red_nether_brick_slab", ridge="minecraft:nether_bricks",
    window="minecraft:dark_oak_trapdoor[facing=north,half=top,open=true,powered=false,waterlogged=false]",
    door_frame="minecraft:dark_oak_planks", accent="minecraft:red_terracotta",
    light="minecraft:lantern[hanging=false,waterlogged=false]", fence="minecraft:dark_oak_fence",
)

WATER = Palette(
    name="water", wall="minecraft:snow_block", wall_alt="minecraft:packed_ice",
    trim="minecraft:blue_ice", post="minecraft:packed_ice", floor="minecraft:packed_ice",
    foundation="minecraft:packed_ice", roof="minecraft:snow_block",
    roof_stairs="minecraft:quartz_stairs", roof_slab="minecraft:snow_block",
    ridge="minecraft:blue_ice", window="minecraft:light_blue_stained_glass_pane",
    door_frame="minecraft:blue_ice", accent="minecraft:blue_ice",
    light="minecraft:sea_lantern", fence="minecraft:spruce_fence",
)

BY_NATION = {"air": AIR, "earth": EARTH, "fire": FIRE, "water": WATER}
