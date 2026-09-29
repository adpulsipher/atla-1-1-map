"""Isometric previews of a built landmark with its surrounding terrain."""
from __future__ import annotations

import numpy as np

from .render import iso_render
from .terrain import NONE, SURFACE_BLOCKS


def landmark_voxels(ctx, margin: int = 24, max_side: int = 900):
    bb = [b for b in (ctx.struct.bbox(), ctx.terrain.bbox()) if b]
    if not bb:
        return [], None
    x0 = min(b[0] for b in bb) - margin
    z0 = min(b[2] for b in bb) - margin
    x1 = max(b[3] for b in bb) + margin
    z1 = max(b[5] for b in bb) + margin
    if x1 - x0 > max_side:
        c = (x0 + x1) // 2
        x0, x1 = c - max_side // 2, c + max_side // 2
    if z1 - z0 > max_side:
        c = (z0 + z1) // 2
        z0, z1 = c - max_side // 2, c + max_side // 2
    W, L = x1 - x0 + 1, z1 - z0 + 1
    g = ctx.tm.window(x0, z0, W, L, "ground").astype(np.int64)
    w = ctx.tm.window(x0, z0, W, L, "water").astype(np.int64)
    s = ctx.tm.window(x0, z0, W, L, "surf")
    lut = np.zeros(256, np.int64)
    for cat, (t, _) in SURFACE_BLOCKS.items():
        lut[cat] = ctx.reg.id(t)
    X, Z = np.meshgrid(np.arange(W) + x0, np.arange(L) + z0, indexing="ij")
    ok = g != NONE
    vox = [(X[ok], g[ok], Z[ok], lut[s[ok]])]
    for k in (1, 2, 3):
        vox.append((X[ok], g[ok] - k, Z[ok], lut[s[ok]]))
    wm = w != NONE
    vox.append((X[wm], w[wm], Z[wm], np.full(wm.sum(), ctx.reg.id("minecraft:water[level=0]"))))
    for buf in (ctx.terrain, ctx.struct):
        for xs, ys, zs, ids, _md in buf.iter_voxels():
            m = (xs >= x0) & (xs <= x1) & (zs >= z0) & (zs <= z1)
            vox.append((xs[m], ys[m], zs[m], ids[m].astype(np.int64)))
    xs = np.concatenate([v[0] for v in vox])
    ys = np.concatenate([v[1] for v in vox])
    zs = np.concatenate([v[2] for v in vox])
    ids = np.concatenate([v[3] for v in vox])
    key = ((xs - x0) * (L + 1) + (zs - z0)) * 1024 + (ys + 128)
    # keep the last write for duplicated positions
    rev = np.arange(key.size)[::-1]
    _, first = np.unique(key[::-1], return_index=True)
    keep = rev[first]
    return [(xs[keep], ys[keep], zs[keep], ids[keep])], (x0, z0, x1, z1)


def render_landmark(ctx, path, max_px: int = 2400, margin: int = 24, max_side: int = 900):
    vox, box = landmark_voxels(ctx, margin, max_side)
    img = iso_render(ctx.reg, vox, max_px=max_px)
    if img is not None:
        img.save(path)
    return box


def render_topdown(ctx, path, scale: int = 2, margin: int = 24, max_side: int = 1400):
    from PIL import Image

    from .render import block_color

    vox, box = landmark_voxels(ctx, margin, max_side)
    if not vox:
        return None
    xs, ys, zs, ids = vox[0]
    x0, z0, x1, z1 = box
    W, L = x1 - x0 + 1, z1 - z0 + 1
    names = [ctx.reg.parsed(i)[0] for i in range(len(ctx.reg))]
    air = np.array([n.split(":")[-1] in ("air", "cave_air") for n in names])
    m = ~air[ids]
    xs, ys, zs, ids = xs[m], ys[m], zs[m], ids[m]
    order = np.argsort(ys, kind="stable")
    top = np.full((W, L), -999, np.int64)
    col = np.zeros((W, L), np.int64)
    top[xs[order] - x0, zs[order] - z0] = ys[order]
    col[xs[order] - x0, zs[order] - z0] = ids[order]
    pal = np.array([block_color(n) for n in names], np.float32)
    rgb = pal[col]
    gx, gz = np.gradient(top.astype(np.float32))
    shade = np.clip(1.0 + (gx - gz) * 0.12, 0.55, 1.4)[..., None]
    img = np.clip(rgb * shade, 0, 255).astype(np.uint8).transpose(1, 0, 2)
    im = Image.fromarray(img, "RGB")
    if scale != 1:
        im = im.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST)
    im.save(path)
    return box
