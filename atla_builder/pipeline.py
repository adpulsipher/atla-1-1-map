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

from . import __version__, datapack, lfs, scatter
from .anvil import World, copy_world
from .blocks import Registry
from .buffer import EditBuffer, apply_buffers
from .geo import GeoRef, register
from .locate import ROOT, Locator, load_landmarks
from .render import overlay_sites, terrain_image
from .schem import export_landmark
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


def build_with_override(ctx: BuildContext, lm: dict, spec: dict, work: Path, log, root: Path = ROOT) -> dict:
    """Place a reviewed community build.

    mode "replace": the build *is* the landmark (procedural builder skipped).
    mode "core":    the procedural landmark is built first, then the area
                    around ``core_poi`` is cleared and the build dropped in
                    (e.g. a community Fire Nation palace inside the caldera).
    """
    from .imports import load_build, place_build

    build = load_build(spec, ctx.reg, root, work)
    mode = spec.get("mode", "replace")
    if mode == "core":
        BUILDERS[lm["builder"]](ctx)
        poi = ctx.pois[spec["core_poi"]]
        X, _, Z = build.size
        q = {"south": 0, "west": 1, "north": 2, "east": 3}[spec.get("facing") or
                                                          {0: "south", 1: "west", 2: "north", 3: "east"}[int(spec.get("rotate", 0)) % 4]]
        fx, fz = (X, Z) if q % 2 == 0 else (Z, X)
        m = int(spec.get("clear_margin", 6))
        ctx.struct.clear_box(poi["x"] - fx // 2 - m, poi["z"] - fz // 2 - m,
                             poi["x"] + fx // 2 + m, poi["z"] + fz // 2 + m)
        info = place_build(ctx, build, spec, at=(poi["x"], poi["z"]),
                           ground_y=spec.get("y") if isinstance(spec.get("y"), int) else poi["y"] - 1)
    else:
        info = place_build(ctx, build, spec)
    for name, p in spec.get("pois", {}).items():  # optional hand-picked POIs, build-local coords
        ctx.poi(name, *p[:3], p[3] if len(p) > 3 else "")
    log(f"    {lm['id']}: community build '{build.name}' ({build.source_format}, "
        f"{info['size'][0]}x{info['size'][1]}x{info['size'][2]}) placed in {mode} mode")
    return info


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
        source = None
        if lid in overrides:
            spec = overrides[lid]
            try:
                info = build_with_override(ctx, lm, spec, work, log)
                source = {"type": "community", "mode": spec.get("mode", "replace"), "placement": info,
                          **{k: spec.get(k) for k in ("file", "world", "source_url", "author", "license",
                                                      "fidelity_review")}}
            except Exception as e:  # missing download, unsupported format...
                log(f"    ! {lid}: community build not used ({e}); falling back to the procedural build")
                ctx = BuildContext(reg, tm, site, lm, seed=_seed(lid))
        if source is None:
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
    # 7. the Atlas: teleport-menu item, arrival points checked against the written world
    dp = datapack.write_datapack(log_doc, dst / "datapacks", World(dst, Registry(W.data_version)))
    shutil.copytree(Path(dp["path"]), out / "datapack" / datapack.PACK, dirs_exist_ok=True)
    log(f"  atlas datapack: {dp['destinations']} destinations on {dp['pages']} book pages")
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
