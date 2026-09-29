"""Command line interface: ``python -m atla_builder <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="atla_builder", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="populate a copy of the world")
    b.add_argument("--world", required=True, help="world folder or .zip (e.g. ATLAB9k.zip)")
    b.add_argument("--out", required=True, help="output directory")
    b.add_argument("--only", nargs="*", help="landmark ids to build (default: all)")
    b.add_argument("--no-scatter", action="store_true", help="skip settlements and roads")
    b.add_argument("--no-schematics", action="store_true", help="skip .schem export")
    b.add_argument("--zip", action="store_true", help="also zip the populated world")
    b.add_argument("--workers", type=int, default=None)
    b.add_argument("--lfs-repo", default=None,
                   help="owner/repo to fetch ATLAB9k.zip from when --world is a Git LFS pointer")
    l = sub.add_parser("locate", help="scan terrain and print landmark sites (no writes)")
    l.add_argument("--world", required=True)
    l.add_argument("--out", required=True)
    p = sub.add_parser("preview", help="render one landmark on the scanned terrain")
    p.add_argument("--terrain", required=True, help="terrain.npz from a previous scan")
    p.add_argument("--georef", required=True)
    p.add_argument("--landmark", required=True)
    p.add_argument("--png", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        from .pipeline import run
        run(a.world, a.out, only=a.only, scatter_on=not a.no_scatter, schematics=not a.no_schematics,
            workers=a.workers, zip_out=a.zip, lfs_repo=a.lfs_repo)
    elif a.cmd == "locate":
        from .anvil import World
        from .locate import locate_all, load_landmarks
        from .pipeline import _extract_if_zip, georeference
        from .terrain import scan_world
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        src = _extract_if_zip(Path(a.world), out, print)
        tm = scan_world(World(src))
        tm.save(out / "terrain.npz")
        geo = georeference(tm)
        geo.save(out / "georef.json")
        sites = locate_all(tm, geo, load_landmarks())
        (out / "sites.json").write_text(json.dumps({k: v.to_json() for k, v in sites.items()}, indent=2),
                                        encoding="utf-8")
    elif a.cmd == "preview":
        sys.argv = ["preview", a.terrain, a.georef, a.landmark, a.png]
        from importlib import util
        spec = util.spec_from_file_location("pv", Path(__file__).resolve().parents[1] / "tools" / "preview_landmark.py")
        mod = util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main(a.terrain, a.georef, a.landmark, a.png)


if __name__ == "__main__":
    main()
