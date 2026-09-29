"""Dev helper: build one landmark on the scanned terrain and render it.

python tools/preview_landmark.py TERRAIN.npz GEOREF.json LANDMARK_ID OUT.png
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atla_builder.blocks import Registry  # noqa: E402
from atla_builder.geo import GeoRef  # noqa: E402
from atla_builder.locate import Locator, load_landmarks  # noqa: E402
from atla_builder.preview import render_landmark, render_topdown  # noqa: E402
from atla_builder.structures.common import BuildContext  # noqa: E402
from atla_builder.structures.registry import BUILDERS  # noqa: E402
from atla_builder.terrain import TerrainModel  # noqa: E402


def main(tpath, gpath, lid, out, max_side=900):
    tm = TerrainModel.load(tpath)
    geo = GeoRef.from_json(json.load(open(gpath)))
    lm = {l["id"]: l for l in load_landmarks()}[lid]
    site = Locator(tm, geo).locate(lm)
    reg = Registry(3837)
    ctx = BuildContext(reg, tm, site, lm, seed=abs(hash(lid)) % 2**31)
    t = time.time()
    BUILDERS[lm["builder"]](ctx)
    print(f"built {lid} in {time.time() - t:.1f}s: struct {ctx.struct.count()} terrain {ctx.terrain.count()} voxels")
    print("site", site.to_json())
    print("pois", json.dumps(ctx.pois)[:1500])
    box = render_landmark(ctx, out, max_side=int(max_side))
    render_topdown(ctx, out.replace(".png", "_top.png"), scale=2 if int(max_side) <= 500 else 1)
    print("rendered box", box)


if __name__ == "__main__":
    main(*sys.argv[1:])
