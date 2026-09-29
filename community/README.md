# Community builds

Put downloaded builds here under the file names used in
[`config/schematic_overrides.json`](../config/schematic_overrides.json) (for example
`fire_nation_palace.schem`), then set `"approved": true` for that landmark and rebuild.

Supported: `.schem` (Sponge v1–3), `.litematic`, `.nbt`, or a world save `.zip` / folder
with `min`/`max` corners. Convert a legacy `.schematic` (pre-1.13) with WorldEdit on
1.13+: `//schem load <name>` then `//schem save <name> sponge.3`.

Check each build's licence before sharing the finished world publicly.

## Getting the files here

The schematic sites use bot protection, so downloads have to be done in your own browser:

1. Download the build from its project page (links in `config/schematic_overrides.json`).
2. On GitHub, open this `community/` folder, click **Add file → Upload files**, drop the file in,
   and rename it to the `file` name its override entry expects (for example `fire_nation_palace.schem`).
   The GitHub website accepts files up to 25 MB; bigger world downloads need Git LFS.
3. In `config/schematic_overrides.json`, set `"approved": true` for that landmark (edit the file on
   GitHub with the pencil icon), then rebuild.

## Where to look

| Site | Link | Notes |
| --- | --- | --- |
| Planet Minecraft: ATLA builds with a downloadable schematic, most downloaded first | https://www.planetminecraft.com/projects/tag/avatar/?share=schematic&order=order_downloads | Best starting point; the "Downloadable Schematic" filter hides world-only downloads |
| Planet Minecraft: all ATLA projects | https://www.planetminecraft.com/projects/tag/avatarthelastairbender/?order=order_downloads | Includes world downloads |
| Rokucraft (ATLA team, near 1:1 scale) | https://www.planetminecraft.com/member/rokucraft/ | Air temples, Fire Nation palace, water tribes, Kyoshi Island |
| abfielder | https://abfielder.com/ | Schematic library with 3D previews in the browser |
| minecraft-schematics.com | https://www.minecraft-schematics.com/ | Search by name |
| ProjectKorra "Avatar Schematics" | https://projectkorra.com/forum/resources/categories/avatar-schematics.8/ | Bending-server community resources |

Search terms: the place name plus `avatar` / `atla` / `last airbender` plus `schematic` or `litematic`.
Useful names: Ba Sing Se, Earth King palace, Omashu, Agna Qel'a / Northern Water Tribe, Southern /
Northern / Eastern / Western Air Temple, Fire Nation palace / Fire Lord palace, Wan Shi Tong library,
Boiling Rock, Kyoshi Island / Kyoshi statue, Crescent Island / Fire Temple, Sun Warriors, Ember Island.
Builder names to try: Rokucraft, Joffrey77, Flerakl. AvatarMC builds are not downloadable.

## File formats (best first)

1. `.schem` (WorldEdit / Sponge, 1.13+)
2. `.litematic` (Litematica)
3. `.nbt` (structure block)
4. A world download (`.zip` with `level.dat` and `region/` inside; extract a `.rar` and zip the folder).
   Also note the build's two corner coordinates (press F3 in-game) for `min` / `max`. Worlds older
   than 1.18 must be opened and saved once in 1.18 or newer.
5. Old `.schematic` (before 1.13): convert first with WorldEdit (`//schem load`, `//schem save <name> sponge.3`).

Not supported: Bedrock files (`.mcstructure`, `.mcworld`). Builds from 1.13–1.20.x fit this world
(1.20.5) best; 1.21+ builds can use blocks that 1.20.5 doesn't have.
