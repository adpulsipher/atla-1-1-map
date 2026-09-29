"""End-to-end population of the ATLA terrain world.

scan terrain -> georeference -> locate landmarks -> build (procedural or an
approved schematic override) -> export .schem -> write into a copy of the
world -> scatter settlements + roads -> JSON placement log + overview map.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import time
import zipfile
from pathlib import Path

import numpy as np

from . import __version__, lfs, scatter
from .anvil import World, copy_world
from .blocks import Registry
from .buffer import EditBuffer, apply_buffers
from .geo import GeoRef, register
from .locate import ROOT, Locator, load_landmarks
from .render import overlay_sites, terrain_image
from .schem import export_landmark, read_schem
from .structures.common import BuildContext
from .structures.registry import BUILDERS
from .terrain import NONE, TerrainModel, scan_world


def _extract_if_zip(src: Path, work: Path, log, lfs_repo: str | None = None) -> Path:
    if not src.exists():
        raise FileNotFoundError(f"{src} not found")
    if src.is_file() and lfs.read_pointer(src):
        # GitHub's "Download ZIP" ships the LFS pointer, not the 772 MB world
        src = lfs.fetch(src, work / src.name, repo=lfs_repo, log=log)
    if src.suffix.lower() != ".zip":
        return src
    if not zipfile.is_zipfile(src):
        raise ValueError(f"{src} is not a zip file (size {src.stat().st_size} bytes). If it came from "
                         "GitHub's 'Download ZIP', fetch the real file with Git LFS or pass the world folder.")
    dest = work / "world_src"
    marker = dest / ".extracted"
    if not marker.exists():
        log(f"extracting {src} ...")
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
        marker.write_text("ok", encoding="utf-8")
    for p in [dest, *sorted(d for d in dest.iterdir() if d.is_dir())]:
        if (p / "level.dat").exists() and (p / "region").is_dir():
            return p
    raise FileNotFoundError("no world (level.dat + region/) inside the zip")


def georeference(tm: TerrainModel, log=print) -> GeoRef:
    valid = tm.ground != NONE
    xs = np.nonzero(valid.any(axis=1))[0]
    zs = np.nonzero(valid.any(axis=0))[0]
    bounds = (tm.x0 + xs[0], tm.z0 + zs[0], tm.x0 + xs[-1] + 1, tm.z0 + zs[-1] + 1)
    g0 = GeoRef.from_bounds(bounds)
    geo = register(tm.downsample_land(16), (tm.x0, tm.z0), 16, g0)
    log(f"  georef: {geo.blocks_per_px:.2f} blocks/px, IoU={geo.score}")
    return geo


def load_overrides() -> dict:
    p = ROOT / "config" / "schematic_overrides.json"
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.get("overrides", {}).items() if v.get("approved")}


def build_override(ctx: BuildContext, spec: dict) -> None:
    """Paste a reviewed community schematic at the located site."""
    ids, off = read_schem(ROOT / spec["file"], ctx.reg)
    H, L, W = ids.shape
    s = ctx.site
    y = spec.get("y") or ctx.ground_median(s.x, s.z, max(W, L) // 2)
    ctx.level_pad(s.x, s.z, max(W, L) / 2, max(W, L) / 2 + 20, y)
    from .buffer import Canvas
    cv = Canvas(ctx.reg, (W, H, L))
    cv.ids[:] = ids.transpose(2, 0, 1)
    cv.mode[cv.ids != 0] = 1
    ctx.place(cv, s.x, s.z, y + spec.get("y_offset", 0), spec.get("facing", "south"),
              anchor=(W // 2, 0, L // 2))


def run(world: str | Path, out: str | Path, only: list[str] | None = None, scatter_on: bool = True,
        schematics: bool = True, workers: int | None = None, zip_out: bool = False, log=print,
        lfs_repo: str | None = None) -> dict:
    t0 = time.time()
    out = Path(out)
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    src = _extract_if_zip(Path(world), work, log, lfs_repo)
    dst = out / f"{src.name}_populated"
    if dst.exists():
        shutil.rmtree(dst)
    log(f"copying {src} -> {dst}")
    copy_world(src, dst)
    W = World(dst)
    reg = Registry(W.data_version or 3953)
    W.reg = reg
    log(f"world DataVersion {W.data_version}")
    # 1. terrain scan (cached)
    tcache = work / "terrain.npz"
    if tcache.exists():
        tm = TerrainModel.load(tcache)
    else:
        log("scanning terrain ...")
        tm = scan_world(World(src), workers=workers, log=log)
        tm.save(tcache)
    log(f"  terrain bounds {tm.bounds}, sea level {tm.sea_level}")
    # 2. georeference
    geo = georeference(tm, log)
    geo.save(out / "georef.json")
    # 3. locate
    lms = load_landmarks()
    loc = Locator(tm, geo)
    order = sorted(range(len(lms)), key=lambda i: -lms[i].get("footprint_r", 60))
    sites = {}
    for i in order:
        s = loc.locate(lms[i])
        sites[lms[i]["id"]] = s
    overrides = load_overrides()
    # 4. build + write, story-priority order
    entries = []
    claims = []
    schem_dir = out / "schematics"
    build_order = sorted(lms, key=lambda l: (l.get("tier", 9), lms.index(l)))
    for lm in build_order:
        lid = lm["id"]
        site = sites[lid]
        if only and lid not in only:
            claims.append((site.x, site.z, lm.get("footprint_r", 60)))
            continue
        tb = time.time()
        ctx = BuildContext(reg, tm, site, lm, seed=_seed(lid))
        if lid in overrides:
            build_override(ctx, overrides[lid])
            source = {"type": "community", **{k: overrides[lid].get(k) for k in
                                              ("file", "source_url", "author", "license", "fidelity_review")}}
        else:
            BUILDERS[lm["builder"]](ctx)
            fn = BUILDERS[lm["builder"]]
            source = {"type": "procedural", "generator": f"{fn.__module__}.{fn.__name__}",
                      "seed": _seed(lid), "version": __version__}
        files = export_landmark(ctx.struct, schem_dir, reg, W.data_version, lid) if schematics else []
        stats = apply_buffers(W, [ctx.terrain, ctx.struct], log=log)
        entries.append(_entry(lm, site, ctx, source, files, stats))
        claims.extend(ctx.claims or [(site.x, site.z, lm.get("footprint_r", 60))])
        log(f"  built {lid:24s} {stats['blocks']:>10,d} blocks in {stats['chunks']:>5d} chunks "
            f"({time.time() - tb:5.1f}s)")
    # 5. scatter settlements + roads
    settlements, roads = [], []
    if scatter_on and not only:
        log("scatter: planning settlements ...")
        plan = scatter.plan(tm, geo, claims, log=log)
        tbuf, sbuf = EditBuffer(reg), EditBuffer(reg)
        for k, st in enumerate(plan):
            ctx = scatter.build_settlement(reg, tm, st, seed=1000 + k)
            tbuf.merge_from(ctx.terrain)
            sbuf.merge_from(ctx.struct)
        lpts = [(e["id"], e["center"]["x"], e["center"]["z"]) for e in entries]
        edges = scatter.road_network(tm, plan, lpts)
        nodes = {s.id: (s.x, s.z) for s in plan}
        nodes.update({i: (x, z) for i, x, z in lpts})
        from .locate import Site

        def factory():
            s0 = Site(id="roads", x=int(tm.x0 + tm.shape[0] // 2), y=64, z=int(tm.z0 + tm.shape[1] // 2),
                      facing="south", angle=0.0, fit_radius=0, strategy="roads", anchor=(0, 0))
            return BuildContext(reg, tm, s0, {"id": "roads", "footprint_r": 0})
        rctx = scatter.paint_roads(factory, tm, nodes, edges)
        # roads first so settlements overwrite them where they meet
        stats = apply_buffers(W, [rctx.terrain, tbuf, sbuf], log=log)
        log(f"  scatter: {len(plan)} settlements, {len(edges)} road links, {stats['blocks']:,d} blocks")
        settlements = [{"id": s.id, "kind": s.kind, "nation": s.nation,
                        "center": {"x": s.x, "y": s.y + 1, "z": s.z}, "buildings": s.buildings,
                        "pois": {k: {"x": v[0], "y": v[1], "z": v[2]} for k, v in s.pois.items()}}
                       for s in plan]
        roads = [{"from": a, "to": b, "length": w} for a, b, w in edges]
    # 6. log + overview
    log_doc = {
        "generator": f"atla_builder {__version__}",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "world": {"name": src.name, "data_version": W.data_version, "sea_level": tm.sea_level,
                  "terrain_bounds": dict(zip(("min_x", "min_z", "max_x", "max_z"), map(int, tm.bounds))),
                  "georef": geo.to_json(), "output_world": dst.name},
        "coordinate_system": "Minecraft block coordinates (x east, z south, y up). centre.y is the walkable "
                             "surface at the landmark centre; POIs mark quest-relevant spots.",
        "quest_start": next((e["center"] for e in entries if e["id"] == "southern_water_tribe"), None),
        "landmarks": entries,
        "settlements": settlements,
        "roads": roads,
    }
    (out / "placements.json").write_text(json.dumps(log_doc, indent=2), encoding="utf-8")
    img = terrain_image(tm, 8)
    overlay_sites(img, tm, 8, sites, {l["id"]: l.get("footprint_r", 60) for l in lms})
    img.save(out / "overview.png")
    if zip_out:
        log("zipping output world ...")
        shutil.make_archive(str(out / dst.name), "zip", root_dir=dst.parent, base_dir=dst.name)
    log(f"done in {time.time() - t0:.0f}s -> {out}")
    return log_doc


def _seed(lid: str) -> int:
    h = 0
    for ch in lid:
        h = (h * 131 + ord(ch)) % 2_147_483_647
    return h


def _entry(lm, site, ctx: BuildContext, source, files, stats) -> dict:
    cx, cz, cr = (ctx.claims[0] if ctx.claims else (site.x, site.z, lm.get("footprint_r", 60)))
    cy = ctx.ground(cx, cz) + 1
    bbs = [b for b in (ctx.struct.bbox(), ctx.terrain.bbox()) if b]
    bb = None
    if bbs:
        bb = {"min": {"x": min(b[0] for b in bbs), "y": min(b[1] for b in bbs), "z": min(b[2] for b in bbs)},
              "max": {"x": max(b[3] for b in bbs), "y": max(b[4] for b in bbs), "z": max(b[5] for b in bbs)}}
    return {
        "id": lm["id"], "name": lm["name"], "nation": lm["nation"], "story_tier": lm.get("tier"),
        "episodes": lm.get("story", []),
        "center": {"x": int(cx), "y": int(cy), "z": int(cz)},
        "footprint_radius": round(float(cr), 1),
        "bbox": bb,
        "site": site.to_json(),
        "scale": ctx.scale,
        "schematic": {**source, "files": files},
        "terrain_integration": ctx.integration,
        "points_of_interest": ctx.pois,
        "notes": ctx.notes,
        "write_stats": stats,
    }
