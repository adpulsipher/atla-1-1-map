# ATLA 1:1 Map: Landmark Population

`atla_builder` adds *Avatar: The Last Airbender* structures to the 9k × 7k custom terrain world `ATLAB9k.zip`. It places 25 story landmarks, 123 settlements themed by nation and a road network. It also writes a JSON log of every placement for the quest-scripting module.

![overview](docs/previews/overview_map.png)

## Quick start

**Just want the finished world?** `ATLAB9k_populated.zip` in the repo root is the populated world
(Git LFS, 762 MB), with every landmark, settlement, road and the Atlas teleport book. On GitHub, open
the file and click **Download raw file**. Unzip it into your `.minecraft/saves/` folder. The
repository's "Download ZIP" button only gives you a small pointer file for it.

To rebuild it yourself (for example after adding community builds):

```bash
pip install -r requirements.txt
python -m atla_builder build --world ATLAB9k.zip --out out --zip
```

`ATLAB9k.zip` is stored with Git LFS. GitHub's **Download ZIP** button (and `git clone` without
Git LFS installed) gives you a 134-byte pointer file instead of the 772 MB world. The build
detects the pointer and downloads the real file into `out/_work/`, checking its SHA-256. For a
private repository, set a token with read access first (`$env:GITHUB_TOKEN="..."` in
PowerShell). You can also pass the real file or an unzipped world folder with `--world`.

The build takes about 4 minutes on 4 cores (a 2-minute terrain scan, then about 100 s of building and writing). The `out/` folder then contains:

| Path | What it is |
| --- | --- |
| `out/ATLAB9k_populated/` (+ `.zip`) | A copy of the world with everything placed. The input world is never modified. |
| `out/placements.json` | The log for the quest-scripting module: landmark centres, bounding boxes, points of interest (POIs), settlements and roads. |
| `out/schematics/*.schem` | Sponge v3 schematics (WorldEdit/FAWE) of each landmark's structure layer. |
| `out/overview.png` | The map with every located site marked. |
| `out/datapack/atla_atlas/` | The Atlas teleport-menu datapack (already installed in the populated world). |

A copy of the log, the schematics and the overview from the run against `ATLAB9k.zip` is committed in [`output/`](output/).

Other commands:

```bash
python -m atla_builder locate  --world ATLAB9k.zip --out scan/        # scan + georeference + sites.json only
python -m atla_builder build   --world ATLAB9k.zip --out out --only omashu ba_sing_se --no-scatter
python -m atla_builder preview --terrain scan/terrain.npz --georef scan/georef.json --landmark omashu --png omashu.png
python -m pytest -q                                                  # 56 tests
```

## How it works

1. **Scan.** Every chunk is decoded and each column records ground height, water surface, canopy top and surface material. The results are cached in `terrain.npz`.
2. **Georeference.** `reference/terrain_classes.png` is a terrain-class raster derived from the painted source map. The pipeline registers it against the world's land mask. For `ATLAB9k` the fit is exact at 16 blocks per reference pixel, with an intersection-over-union (IoU) of 0.974.
3. **Locate.** Each landmark in [`config/landmarks.json`](config/landmarks.json) has an anchor on the reference map, checked against the canon *Aang's Journey* map. A terrain strategy then refines it:
   - `peak`: air temples, Omashu, the Fire Nation Capital.
   - `coast` and `coast_flat`: the Water Tribes, Full Moon Bay.
   - `island`: Kyoshi, Ember and Crescent islands.
   - `inland_max`: Ba Sing Se.
   - `desert`: the library and the rock.
   - `ravine`: the Western Air Temple.
   - `sea`: the Boiling Rock.
   - `path`: the Serpent's Pass.
4. **Scale check.** Each builder sizes itself to the usable radius the locator measured, then blends into the terrain. The integration step used for each landmark is recorded in the log.
5. **Build and write.** Builders draw into sparse edit buffers, one for terrain and one for structure. Edited sections are re-encoded in the chunk's own format and DataVersion.
   - Heightmaps are dropped and `isLightOn` is cleared, so Minecraft recomputes both on load.
   - WorldPainter proto-chunks (`liquid_carvers`) that get edited are promoted to `full`. Otherwise vanilla feature generation would grow trees and lakes over the new buildings.
6. **Scatter.** Settlements are placed by Poisson spacing, avoiding landmarks and each nation's unsuitable terrain. A minimum-spanning road network links them and the landmarks so NPCs have paths to follow.

## Landmarks (from the committed run)

| Tier | Landmark | Centre (x, y, z) | Terrain integration |
| --- | --- | --- | --- |
| 1 | Southern Water Tribe *(quest start)* | -394, 65, 2738 | Snow shelf levelled on the flat north coast, beach cut for the dock, Aang's iceberg offshore |
| 1 | Northern Water Tribe & Spirit Oasis | -250, 96, -3096 | Ice shelf terraced into 4 tiers around the bay, ring and radial canals, great harbour wall with water gate |
| 1 | Foggy Swamp (banyan-grove tree) | 632, 63, 739 | Grown in the painted swamp wetland; 18 surface roots spread across it |
| 2 | Southern Air Temple | -138, 249, 1810 | Summit cut to a plaza, towers step down the flanks, pilgrim stair |
| 2 | Northern Air Temple (Mechanist) | 582, 259, -2234 | Spire trimmed under the build limit; copper pipes, gears, workshop, war balloon, gas cavern |
| 2 | Eastern Air Temple | 3750, 245, 762 | Five rock spires with towers, rope bridges, Guru Pathik's ledge |
| 2 | Western Air Temple | -3344, 89, -1883 | Gorge carved along the ridge; towers hang **inverted** under both rims; fountain courtyard |
| 3 | Kyoshi Island | 762, 68, 2342 | Coastal flat; Avatar Kyoshi statue, Kyoshi Warriors' dojo, pier |
| 3 | Omashu | 658, 152, 254 | Peak reshaped into a 4-tier mesa inside a chasm; bridge and gate, palace, 3 spiralling **mail chutes** |
| 3 | Senlin Village & Spirit Forest | 190, 85, 14 | Village plus a burnt forest with Hei Bai's statue and the acorn |
| 3 | The Great Divide | 158, 67, -978 | 640-block terraced canyon with terracotta strata, ranger station, switchback trail |
| 3 | Gaoling | 1954, 86, 1098 | Town, walled Beifong estate, **underground Earth Rumble VI arena** with cave entrance |
| 3 | Serpent's Pass | 2478, 67, -671 | Meandering rock spine with flooded moats and sunken gaps, "Abandon hope" sign |
| 3 | Ba Sing Se | 2438, 84, -1818 | See below |
| 3 | Full Moon Bay | 2624, 66, -334 | Sheltered cove, ferry terminal, passport office, 3 piers, 2 ferries |
| 3 | Wan Shi Tong's Library | 1786, 79, 158 | Buried hall; only the spire shows above the dunes; planetarium |
| 3 | Misty Palms Oasis | 1146, 67, 222 | Pool, palms, adobe buildings, sand-sailer |
| 3 | Si Wong rock | 1622, 72, -254 | Rock formation with a shelter overhang |
| 3 | Wulong Forest | -54, 81, -202 | About 60 karst pillars (some broken); final-battle pillar POI |
| 4 | Crescent Island Fire Temple | -1670, 145, -34 | Temple with its tall spire, Roku's sanctuary behind the five-dragon door, lava vent |
| 4 | Sun Warriors' ancient city | -4222, 78, 250 | Stepped pyramid with the Sun Stone, Dancing Dragon plaza, ruins, Eternal Flame, Masters' cave |
| 4 | The Boiling Rock | -3018, 75, -1070 | Crater island raised from the seabed; magma lake floor with bubble columns (it really boils); prison, cooler, gondola |
| 4 | Ember Island | -2258, 75, 38 | Shaped sand beach, Ember Island Players theatre, royal beach house, resort town |
| 4 | Fire Nation Capital | -4010, 163, -294 | Volcano hollowed into the Royal Caldera; palace, Royal Plaza, Agni Kai arena, terraced city, Harbor City and rim road |

**Ba Sing Se** is the largest structure on the map (1,120 × 1,000 blocks):
- **Outer Wall:** a 60-block wall with walkway, crenellations, towers, four gatehouses and culverts where rivers pass through.
- **Agrarian Zone:** 34×24 crop plots, irrigation ditches and about 70 farmhouses.
- **Monorail:** elevated viaducts with stations running from each outer gate.
- **Inner Wall and districts:** the dense Lower Ring, the Middle Ring (including the University) and the Upper Ring (including the Jasmine Dragon), each on a higher terrace.
- **Palace:** the Earth King's Palace on the top plateau.
- **Lake Laogai:** uses the natural lake in the Agrarian Zone. The Dai Li base is underneath, with a headquarters hall, prison cells and the brainwashing chamber, reached from a hidden shoreline shaft.

Previews in [`docs/previews/`](docs/previews/): isometric renders of each builder, plus top-down renders of Ba Sing Se read back from the written world.

## `placements.json` schema

```jsonc
{
  "world": {"data_version": 3837, "sea_level": 62, "georef": {...}},
  "quest_start": {"x": -394, "y": 65, "z": 2738},
  "landmarks": [{
    "id": "omashu", "name": "...", "nation": "earth", "story_tier": 3, "episodes": ["1x05 ..."],
    "center": {"x": 658, "y": 152, "z": 254},          // walkable surface at the centre
    "bbox": {"min": {...}, "max": {...}},
    "site": {...},                                      // locator result (strategy, facing, fit radius)
    "schematic": {"type": "procedural", "generator": "atla_builder.structures.earth.omashu", "seed": 0,
                  "files": [{"file": "omashu.schem", "size": [w, h, l], "world_origin": [x, y, z]}]},
    "terrain_integration": ["peak reshaped into a 4-tier mesa ..."],
    "points_of_interest": {"king_bumi_palace": {"x":..,"y":..,"z":.., "desc": "..."}, "mail_chute_1_top": {...}}
  }],
  "settlements": [{"id": "earth_farm_hamlet_004", "kind": "farm_hamlet", "nation": "earth", "center": {...}}],
  "roads": [{"from": "earth_farm_hamlet_004", "to": "omashu", "length": 412}]
}
```

The log contains 110 landmark POIs, including spawn points for creatures and characters the mod adds: Tui & La's koi, the serpent's lair, the Unagi waters and Hei Bai.

## The Atlas (teleport menu)

Every player gets a glowing written book, the **Atlas of the Four Nations**, the first time they join.
Opening it shows a menu:

- **Index page:** jump to Water Tribes, Air Nomads, Earth Kingdom, Fire Nation, or the villages of each nation.
- **Nation pages:** every landmark (bold), with its points of interest underneath, such as the Spirit
  Oasis, Lake Laogai's Dai Li base, the Earth Rumble arena and the Omashu mail chutes.
- **Village pages:** each settlement, named by where it is (for example "Farm hamlet, NW of Omashu").

Clicking an entry teleports you there. The click runs `/trigger atla_tp set <n>`, which works for
every player without cheats. Lost the book? Run `/trigger atla_atlas`.

- **How it's built:** the datapack is generated from `placements.json` by `atla_builder/datapack.py`.
- **Arrival points:** every destination is checked against the written world and moved to the nearest
  spot a player can stand (out of statues, wells and walls; onto cave and room floors).
- **Versions:** the files use both the pre-1.21 and 1.21+ folder names, and both the old and new
  text-component keys, so one pack targets Java 1.20.5 and newer. It has not been tested in-game.
- **Reinstalling:** `python -m atla_builder datapack --log out/placements.json --world <populated world>`
  rewrites it into an existing world.

## Community builds (for the complex landmarks)

The complex landmarks can use existing community builds instead of the procedural ones. The pipeline
imports them automatically once the files are in [`community/`](community/) and approved in
[`config/schematic_overrides.json`](config/schematic_overrides.json).

- **Formats:** Sponge `.schem` (v1–3), Litematica `.litematic`, vanilla structure `.nbt`, or a region
  copied out of a downloaded **world save** (give its `min`/`max` corners). Legacy pre-1.13 `.schematic`
  files are detected and need converting first (WorldEdit on 1.13+: `//schem load`, then
  `//schem save <name> sponge.3`).
- **`replace` mode:** the build is the whole landmark. The ground is levelled under its footprint and
  foundations are filled down to the terrain.
- **`core` mode:** the procedural landmark is kept, and the build replaces the area around one point of
  interest. This suits the Fire Nation palace inside the carved caldera city, or the Earth King's
  palace inside the Ba Sing Se rings.
- **Block entities:** signs, banners and heads are converted to the chunk's data version. Container
  contents and entities (item frames, armor stands) are not imported, and the log says how many were
  skipped.
- **Fallback:** if a file is missing or unreadable, the build logs a warning and falls back to the
  procedural landmark.

**Shortlist.** These were found with web search. Planet Minecraft and the file hosts are blocked from the
build environment, so none could be downloaded or previewed here. Check each one against the show
before approving it.

| Landmark | Candidates (see `schematic_overrides.json` for notes) |
| --- | --- |
| Fire Nation Capital (palace, `core`) | [Joffrey77 – Fire Nation Royal Palace](https://www.planetminecraft.com/project/fire-nation-royal-palace-avatar-the-last-airbender/) (~34k downloads), [Rokucraft](https://www.planetminecraft.com/project/the-fire-nation-palace-rokucraft/), [blazeon1234](https://abfielder.com/schematicdetail/blazeon1234/fire-nation-palace/2307) |
| Southern Air Temple | [Rokucraft](https://www.planetminecraft.com/project/southern-air-temple-rokucraft/), [Rokucraft (older)](https://www.planetminecraft.com/project/the-southern-air-temple-jong-mu-air-temple/) |
| Western Air Temple | [Rokucraft](https://www.planetminecraft.com/project/western-air-temple-rokucraft/), [1.16.5 build](https://www.planetminecraft.com/project/avatar-the-last-airbender-western-air-temple-1-16-5/), [another](https://www.planetminecraft.com/project/western-air-temple-avatar/) |
| Eastern Air Temple | [Rokucraft](https://www.planetminecraft.com/project/the-eastern-airtemple-rokucraft/), [Java & Bedrock build](https://www.planetminecraft.com/project/the-eastern-air-temple/) |
| Northern Water Tribe | [Rokucraft (2012)](https://www.planetminecraft.com/project/southern-water-tribe/), [full scale](https://www.planetminecraft.com/project/full-scale-northern-water-tribe/), [finished city](https://www.planetminecraft.com/project/the-northern-water-tribe-finished-download-link/) |
| Omashu | [mocarona](https://www.planetminecraft.com/project/omashu/), [Avatar Omashu](https://www.planetminecraft.com/project/avatar-omashu/) |
| Ba Sing Se (palace, `core`) | [ShadowESH map (40% complete, world download)](https://www.planetminecraft.com/project/avatar-the-last-airbender-ba-sing-se/) |
| Wan Shi Tong's Library | [three builds](https://www.planetminecraft.com/project/wan-shi-tong-s-library-avatar-the-last-airbender/) (see config) |
| Kyoshi Island | [Rokucraft rework](https://www.planetminecraft.com/projects/tag/rokucraft/) |

No downloadable Northern Air Temple or Boiling Rock was found (AvatarMC's builds can't be downloaded),
so those stay procedural. Check each build's licence before sharing a world that contains it.

**Exported schematics.** The `.schem` files in `output/schematics/` hold only each landmark's structure
layer; the terrain integration exists only in the world. Paste them with `//schem load <id>`, then
`//paste -m !minecraft:structure_void`.

## Version notes

- `ATLAB9k` is a 1.20.5 level (DataVersion 3837) whose chunks were written by WorldPainter as 1.18 proto-chunks (DataVersion 2860).
- Edited chunks keep their DataVersion, so Minecraft's DataFixer still upgrades the untouched WorldPainter content when a newer game opens the world. New blocks are written with names that are valid in the level's version, for example `short_grass`.
- Every block used exists in 1.20+.
- After editing, all 358,400 chunks were re-parsed with zero failures.

## Limitations

- No entities are placed: no NPCs, animals, boats as entities, or the serpent. Those belong to the mod; their spawn points are POIs in the log.
- The procedural builds write no block entities except the Serpent's Pass sign. Imported community builds keep their signs, banners and heads.
- Settlements between landmarks use generic nation-themed houses rather than named canon villages.

## Layout

```
atla_builder/        anvil.py (region/chunk IO), buffer.py (edit buffers & primitives), terrain.py (scan),
                     geo.py + locate.py (georef & site search), structures/ (water, air, earth, basingse,
                     fire, kit, village), scatter.py, schem.py, imports.py (community builds),
                     datapack.py (the Atlas), lfs.py, pipeline.py, render.py, preview.py, cli.py
config/              landmarks.json, schematic_overrides.json (community-build shortlist)
community/           put downloaded community builds here
datapack/atla_atlas/ the Atlas datapack generated from the committed run
reference/           terrain_classes.png (derived from the painted map; used for registration)
tools/               make_reference_classes.py, preview_landmark.py
tests/               anvil/buffer/rotation/schem/georef tests + a smoke test for every builder
output/              placements.json, overview.png, georef.json, schematics/ from the ATLAB9k run
.claude/skills/      visual-builder skill (image -> code protocol); skills_dist/ has the packaged .skill
```
