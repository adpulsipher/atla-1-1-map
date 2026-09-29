"""Preview renderers: top-down terrain map and isometric structure views."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from .blocks import C_AIR, Registry, classify_name
from .terrain import (NONE, S_CLAY, S_DIRT, S_GRASS, S_GRAVEL, S_ICE, S_MUD, S_NONE, S_OTHER,
                      S_PODZOL, S_RED_SAND, S_SAND, S_SANDSTONE, S_SNOW, S_STONE, S_TERRACOTTA)

_COLORS = {
    "stone": (125, 125, 125), "cobblestone": (115, 115, 115), "stone_bricks": (122, 121, 122),
    "mossy_stone_bricks": (100, 118, 90), "cracked_stone_bricks": (118, 117, 118),
    "mossy_cobblestone": (100, 115, 90), "andesite": (136, 136, 137), "polished_andesite": (132, 135, 134),
    "diorite": (188, 188, 189), "polished_diorite": (192, 193, 194), "granite": (149, 103, 85),
    "calcite": (223, 224, 220), "smooth_quartz": (235, 229, 222), "quartz_block": (235, 229, 222),
    "quartz_pillar": (235, 230, 224), "quartz_bricks": (234, 229, 221), "white_concrete": (207, 213, 214),
    "snow_block": (249, 254, 254), "snow": (249, 254, 254), "packed_ice": (141, 180, 250),
    "blue_ice": (116, 167, 253), "ice": (145, 183, 253), "water": (50, 90, 200),
    "sand": (219, 207, 163), "sandstone": (216, 203, 155), "smooth_sandstone": (223, 214, 170),
    "cut_sandstone": (218, 206, 160), "chiseled_sandstone": (216, 203, 155), "red_sand": (190, 102, 33),
    "red_sandstone": (186, 99, 29), "smooth_red_sandstone": (181, 97, 31), "terracotta": (152, 94, 67),
    "white_terracotta": (209, 178, 161), "orange_terracotta": (161, 83, 37), "red_terracotta": (143, 61, 46),
    "brown_terracotta": (77, 51, 35), "yellow_terracotta": (186, 133, 35), "light_gray_terracotta": (135, 107, 98),
    "gray_terracotta": (57, 42, 35), "black_terracotta": (37, 22, 16), "green_terracotta": (76, 83, 42),
    "lime_terracotta": (103, 117, 52), "cyan_terracotta": (86, 91, 91), "light_blue_terracotta": (113, 108, 137),
    "blue_terracotta": (74, 59, 91), "grass_block": (95, 150, 60), "dirt": (134, 96, 67),
    "coarse_dirt": (119, 85, 59), "podzol": (91, 63, 24), "mud": (60, 57, 61), "packed_mud": (142, 106, 79),
    "mud_bricks": (137, 103, 79), "dirt_path": (148, 122, 65), "farmland": (110, 75, 45), "gravel": (131, 127, 126),
    "clay": (160, 166, 179), "oak_planks": (162, 130, 78), "spruce_planks": (114, 84, 48),
    "birch_planks": (192, 175, 121), "jungle_planks": (160, 115, 80), "acacia_planks": (168, 90, 50),
    "dark_oak_planks": (66, 43, 20), "mangrove_planks": (117, 54, 48), "cherry_planks": (226, 178, 172),
    "bamboo_planks": (193, 173, 80), "crimson_planks": (101, 48, 70), "warped_planks": (43, 104, 99),
    "oak_log": (109, 85, 50), "spruce_log": (58, 37, 16), "birch_log": (216, 215, 210), "jungle_log": (85, 67, 25),
    "dark_oak_log": (60, 46, 26), "mangrove_log": (84, 66, 36), "acacia_log": (103, 96, 86),
    "stripped_oak_log": (177, 144, 86), "stripped_spruce_log": (115, 89, 52), "stripped_dark_oak_log": (96, 76, 49),
    "stripped_jungle_log": (171, 132, 84), "mangrove_roots": (74, 59, 38), "muddy_mangrove_roots": (70, 58, 45),
    "oak_leaves": (60, 110, 40), "jungle_leaves": (50, 120, 30), "mangrove_leaves": (60, 105, 35),
    "dark_oak_leaves": (45, 90, 30), "spruce_leaves": (50, 80, 50), "birch_leaves": (90, 125, 60),
    "cherry_leaves": (229, 172, 194), "azalea_leaves": (90, 115, 45), "flowering_azalea_leaves": (110, 115, 70),
    "moss_block": (89, 109, 45), "moss_carpet": (89, 109, 45), "vine": (50, 100, 30), "lily_pad": (40, 110, 40),
    "glass": (200, 220, 230), "glass_pane": (200, 220, 230), "iron_bars": (110, 110, 110),
    "gold_block": (246, 208, 61), "iron_block": (220, 220, 220), "copper_block": (192, 107, 79),
    "cut_copper": (191, 106, 80), "exposed_cut_copper": (155, 122, 101), "weathered_cut_copper": (109, 145, 107),
    "oxidized_cut_copper": (80, 154, 132), "oxidized_copper": (82, 162, 132), "lightning_rod": (192, 107, 79),
    "red_nether_bricks": (69, 7, 9), "nether_bricks": (44, 21, 26), "red_concrete": (142, 32, 32),
    "red_wool": (160, 39, 34), "black_concrete": (8, 10, 15), "gray_concrete": (54, 57, 61),
    "blackstone": (42, 36, 41), "polished_blackstone": (53, 48, 56), "polished_blackstone_bricks": (48, 42, 49),
    "deepslate": (80, 80, 82), "deepslate_tiles": (54, 54, 55), "deepslate_bricks": (70, 70, 70),
    "polished_deepslate": (72, 72, 73), "cobbled_deepslate": (77, 77, 80), "basalt": (80, 81, 86),
    "polished_basalt": (99, 98, 100), "smooth_basalt": (72, 72, 78), "magma_block": (142, 63, 31),
    "lava": (207, 92, 20), "obsidian": (15, 10, 24), "crying_obsidian": (32, 10, 60),
    "prismarine": (99, 156, 151), "prismarine_bricks": (99, 171, 158), "dark_prismarine": (51, 91, 75),
    "sea_lantern": (172, 199, 190), "glowstone": (171, 131, 84), "shroomlight": (240, 146, 70),
    "lantern": (106, 91, 83), "soul_lantern": (70, 99, 110), "torch": (255, 200, 90), "campfire": (160, 90, 40),
    "bookshelf": (117, 94, 59), "chiseled_bookshelf": (120, 95, 60), "white_wool": (234, 236, 237),
    "light_blue_wool": (58, 175, 217), "blue_wool": (53, 57, 157), "cyan_wool": (21, 137, 145),
    "brown_wool": (114, 71, 40), "yellow_wool": (248, 197, 39), "orange_wool": (240, 118, 19),
    "green_wool": (84, 109, 27), "lime_wool": (112, 185, 25), "black_wool": (20, 21, 25), "gray_wool": (62, 68, 71),
    "light_gray_wool": (142, 142, 134), "pink_wool": (237, 141, 172), "purple_wool": (121, 42, 172),
    "blue_concrete": (44, 46, 143), "light_blue_concrete": (35, 137, 198), "cyan_concrete": (21, 119, 136),
    "white_glazed_terracotta": (188, 212, 202), "yellow_concrete": (240, 175, 21), "orange_concrete": (224, 97, 0),
    "green_concrete": (73, 91, 36), "lime_concrete": (94, 168, 24), "brown_concrete": (96, 59, 31),
    "hay_block": (166, 136, 38), "wheat": (170, 160, 60), "bone_block": (229, 225, 207), "bricks": (150, 97, 83),
    "dripstone_block": (134, 107, 92), "tuff": (108, 109, 102), "sponge": (195, 192, 74),
    "bamboo_block": (127, 144, 58), "bamboo_mosaic": (190, 170, 78), "dead_bush": (107, 78, 40),
    "cactus": (85, 127, 43), "sugar_cane": (148, 192, 101), "short_grass": (90, 140, 50), "grass": (90, 140, 50),
    "tall_grass": (90, 140, 50), "fern": (80, 120, 50), "poppy": (200, 30, 30), "dandelion": (240, 220, 40),
    "pink_petals": (240, 170, 200), "coal_block": (16, 15, 15), "bedrock": (85, 85, 85),
    "chiseled_stone_bricks": (119, 118, 119), "chiseled_quartz_block": (231, 226, 218),
    "end_stone_bricks": (218, 224, 162), "purpur_block": (170, 126, 170), "smooth_stone": (158, 158, 158),
    "emerald_block": (42, 203, 88), "lapis_block": (31, 67, 140), "raw_gold_block": (221, 169, 46),
    "honeycomb_block": (229, 148, 29), "ochre_froglight": (251, 245, 207), "pearlescent_froglight": (245, 240, 239),
    "verdant_froglight": (229, 244, 228), "brown_mushroom_block": (149, 111, 81), "mushroom_stem": (203, 196, 185),
    "spruce_fence": (114, 84, 48), "oak_fence": (162, 130, 78), "dark_oak_fence": (66, 43, 20),
    "bubble_column": (50, 90, 200), "bell": (250, 210, 60), "cobweb": (220, 220, 220), "scaffolding": (170, 130, 70),
    "light_gray_concrete": (125, 125, 115), "stripped_mangrove_log": (119, 54, 47), "stripped_acacia_log": (174, 92, 59),
    "mangrove_propagule": (96, 174, 83), "jack_o_lantern": (220, 140, 30), "target": (226, 170, 157),
    "red_mushroom_block": (200, 46, 45), "netherrack": (97, 38, 38), "crimson_nylium": (130, 31, 31),
    "warped_wart_block": (22, 119, 121), "nether_wart_block": (114, 2, 2), "gilded_blackstone": (56, 43, 38),
    "chiseled_polished_blackstone": (53, 48, 56), "cracked_polished_blackstone_bricks": (44, 37, 43),
    "spruce_trapdoor": (103, 79, 47), "oak_trapdoor": (124, 99, 56), "dark_oak_trapdoor": (75, 49, 23),
    "rooted_dirt": (144, 103, 76), "black_concrete_powder": (25, 27, 32), "carrots": (90, 150, 50), "potatoes": (80, 140, 45), "suspicious_sand": (219, 207, 163), "stripped_birch_log": (196, 176, 118),
}
_KEYWORDS = [
    ("red_nether_brick", (69, 7, 9)), ("nether_brick", (44, 21, 26)), ("blackstone", (48, 42, 49)),
    ("deepslate", (70, 70, 70)), ("prismarine", (80, 150, 135)), ("oxidized_cut_copper", (80, 154, 132)),
    ("oxidized", (80, 154, 132)), ("weathered", (109, 145, 107)), ("copper", (191, 106, 80)),
    ("quartz", (235, 229, 222)), ("red_sandstone", (184, 98, 30)), ("sandstone", (218, 206, 160)),
    ("mud_brick", (137, 103, 79)), ("stone_brick", (122, 121, 122)), ("cobblestone", (115, 115, 115)),
    ("andesite", (134, 135, 135)), ("diorite", (190, 190, 191)), ("granite", (149, 103, 85)),
    ("spruce", (114, 84, 48)), ("dark_oak", (66, 43, 20)), ("birch", (192, 175, 121)),
    ("jungle", (160, 115, 80)), ("acacia", (168, 90, 50)), ("mangrove", (117, 54, 48)), ("cherry", (226, 178, 172)),
    ("bamboo", (193, 173, 80)), ("crimson", (101, 48, 70)), ("warped", (43, 104, 99)), ("oak", (162, 130, 78)),
    ("brick", (150, 97, 83)), ("stone", (125, 125, 125)), ("snow", (249, 254, 254)), ("ice", (140, 180, 250)),
    ("wool", (200, 200, 200)), ("glass", (200, 220, 230)), ("leaves", (60, 110, 40)), ("gold", (246, 208, 61)),
    ("iron", (210, 210, 210)), ("lantern", (106, 91, 83)), ("terracotta", (152, 94, 67)),
]


@lru_cache(maxsize=None)
def block_color(name: str) -> tuple[int, int, int]:
    b = name.split(":")[-1]
    if b in _COLORS:
        return _COLORS[b]
    for suffix in ("_stairs", "_slab", "_wall", "_fence_gate", "_fence", "_pane", "_trapdoor", "_door",
                   "_button", "_pressure_plate", "_carpet"):
        if b.endswith(suffix):
            base = b[: -len(suffix)]
            for cand in (base, base + "s", base + "_block", base + "_planks", base.replace("brick", "bricks")):
                if cand in _COLORS:
                    return _COLORS[cand]
    if b.endswith("_wood"):
        return block_color(name.replace("_wood", "_log"))
    for key, col in _KEYWORDS:
        if key in b:
            return col
    return (200, 0, 200)


# --------------------------------------------------------------------------
SURF_COLORS = {
    S_NONE: (60, 60, 60), S_GRASS: (96, 145, 62), S_DIRT: (134, 96, 67), S_SAND: (219, 207, 163),
    S_RED_SAND: (190, 102, 33), S_GRAVEL: (131, 127, 126), S_STONE: (125, 125, 125),
    S_SNOW: (245, 250, 252), S_ICE: (150, 185, 250), S_TERRACOTTA: (160, 95, 60),
    S_SANDSTONE: (216, 203, 155), S_MUD: (70, 66, 60), S_PODZOL: (91, 63, 24), S_CLAY: (160, 166, 179),
    S_OTHER: (110, 140, 70),
}


def terrain_image(tm, step: int = 8) -> Image.Image:
    g = tm.ground[::step, ::step].astype(np.float32)
    w = tm.water[::step, ::step]
    s = tm.surf[::step, ::step]
    lut = np.array([SURF_COLORS.get(i, (255, 0, 255)) for i in range(256)], np.float32)
    col = lut[s]
    gx, gz = np.gradient(np.where(g == NONE, tm.sea_level, g))
    shade = np.clip(1.0 + (gx - gz) * 0.08 * step / 4, 0.55, 1.35)[..., None]
    col = col * shade
    water = w != NONE
    depth = np.clip((w - g) / 30.0, 0, 1)[..., None]
    wcol = np.array([60, 110, 210]) * (1 - depth) + np.array([15, 45, 150]) * depth
    col = np.where(water[..., None], wcol, col)
    img = np.clip(col, 0, 255).astype(np.uint8).transpose(1, 0, 2)  # rows = z
    return Image.fromarray(img, "RGB")


def overlay_sites(img: Image.Image, tm, step: int, sites: dict, footprints: dict | None = None) -> Image.Image:
    d = ImageDraw.Draw(img)
    for sid, s in sites.items():
        px, pz = (s.x - tm.x0) / step, (s.z - tm.z0) / step
        r = (footprints or {}).get(sid, 40) / step
        d.ellipse([px - r, pz - r, px + r, pz + r], outline=(255, 40, 40), width=1)
        d.ellipse([px - 2, pz - 2, px + 2, pz + 2], fill=(255, 255, 0))
        d.text((px + 4, pz - 6), sid, fill=(255, 255, 255))
    return img


# --------------------------------------------------------------------------
def iso_render(reg: Registry, voxels, max_px: int = 2400, cull: bool = True) -> Image.Image | None:
    """Isometric view from the south-east of a list of (xs, ys, zs, ids) arrays."""
    xs = np.concatenate([v[0] for v in voxels]) if voxels else np.zeros(0, int)
    if xs.size == 0:
        return None
    ys = np.concatenate([v[1] for v in voxels])
    zs = np.concatenate([v[2] for v in voxels])
    ids = np.concatenate([v[3] for v in voxels]).astype(np.int64)
    cls = np.array([classify_name(reg.parsed(i)[0]) for i in range(len(reg))], np.uint8)
    keep = cls[ids] != C_AIR
    xs, ys, zs, ids = xs[keep], ys[keep], zs[keep], ids[keep]
    if xs.size == 0:
        return None
    x0, y0, z0 = xs.min(), ys.min(), zs.min()
    xs, ys, zs = xs - x0, ys - y0, zs - z0
    if cull:
        X, Y, Z = xs.max() + 2, ys.max() + 2, zs.max() + 2
        if X * Y * Z < 600_000_000:
            occ = np.zeros((X, Y, Z), bool)
            occ[xs, ys, zs] = True
            vis = ~occ[xs + 1, ys, zs] | ~occ[xs, ys + 1, zs] | ~occ[xs, ys, zs + 1]
            xs, ys, zs, ids = xs[vis], ys[vis], zs[vis], ids[vis]
            del occ
    extent = (xs.max() + zs.max()) * 2 + 8
    s = max(1, min(4, int(max_px / max(extent, 1))))
    u = (xs - zs) * 2 * s
    v = (xs + zs) * s - ys * 2 * s
    u = u - u.min()
    v = v - v.min()
    Wimg, Himg = int(u.max()) + 4 * s + 1, int(v.max()) + 4 * s + 1
    depth = xs + ys + zs
    order = np.argsort(depth, kind="stable")
    u, v, ids = u[order], v[order], ids[order]
    pal = np.array([block_color(reg.parsed(i)[0]) for i in range(len(reg))], np.float32)
    base = pal[ids]
    img = np.zeros((Himg, Wimg, 3), np.float32)
    img[:] = (24, 26, 32)
    top, left, right = base * 1.0, base * 0.78, base * 0.6
    for du in range(4 * s):
        for dv in range(4 * s):
            if dv < 2 * s:
                col = top
            elif du < 2 * s:
                col = left
            else:
                col = right
            img[v + dv, u + du] = col
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def buffer_voxels(buf, bbox=None, include_modes=(1, 2, 3)):
    out = []
    for xs, ys, zs, ids, md in buf.iter_voxels():
        m = np.isin(md, include_modes)
        if bbox is not None:
            x0, z0, x1, z1 = bbox
            m &= (xs >= x0) & (xs <= x1) & (zs >= z0) & (zs <= z1)
        if m.any():
            out.append((xs[m], ys[m], zs[m], ids[m]))
    return out


def world_topdown(world, x0: int, z0: int, w: int, l: int, step: int = 1) -> Image.Image:
    """Top-down colour map read back from the actual blocks stored in the world."""
    from .blocks import C_AIR
    reg = world.reg
    W, L = (w + step - 1) // step, (l + step - 1) // step
    img = np.zeros((W, L, 3), np.float32)
    hgt = np.zeros((W, L), np.float32)
    for cx in range(x0 >> 4, (x0 + w - 1 >> 4) + 1):
        for cz in range(z0 >> 4, (z0 + l - 1 >> 4) + 1):
            ch = world.load_chunk(cx, cz)
            if ch is None:
                continue
            found = np.zeros((16, 16), bool)
            top_id = np.zeros((16, 16), np.int64)
            top_y = np.zeros((16, 16), np.int64)
            for sy in sorted(ch.sections, reverse=True):
                a = ch.section_array(sy)
                if a is None:
                    continue
                cls = np.array([classify_name(reg.parsed(i)[0]) for i in range(len(reg))], np.uint8)
                solid = cls[a] != C_AIR
                has = solid.any(axis=0)
                yy = 15 - np.argmax(solid[::-1], axis=0)
                new = has & ~found
                zz, xx = np.nonzero(new)
                top_id[zz, xx] = a[yy[zz, xx], zz, xx]
                top_y[zz, xx] = sy * 16 + yy[zz, xx]
                found |= new
                if found.all():
                    break
            pal = np.array([block_color(reg.parsed(i)[0]) for i in range(len(reg))], np.float32)
            col = pal[top_id]  # [z, x, 3]
            for lz in range(16):
                for lx in range(16):
                    gx, gz = cx * 16 + lx - x0, cz * 16 + lz - z0
                    if 0 <= gx < w and 0 <= gz < l and gx % step == 0 and gz % step == 0:
                        img[gx // step, gz // step] = col[lz, lx]
                        hgt[gx // step, gz // step] = top_y[lz, lx]
    gx, gz = np.gradient(hgt)
    shade = np.clip(1.0 + (gx - gz) * 0.1, 0.55, 1.4)[..., None]
    out = np.clip(img * shade, 0, 255).astype(np.uint8).transpose(1, 0, 2)
    return Image.fromarray(out, "RGB")
