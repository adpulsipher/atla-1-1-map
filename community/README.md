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
