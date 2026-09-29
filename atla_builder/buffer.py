"""Sparse world edit buffers, dense canvases and shared drawing primitives.

Two containers share one primitive API (:class:`Primitives`):

* :class:`EditBuffer` - sparse, world-coordinate, 16³ sections created on
  demand.  Used for anything map-scale (walls kilometres long, terrain pads).
* :class:`Canvas` - dense local volume, used for prefab buildings that are
  rotated / mirrored before being pasted into an :class:`EditBuffer`.

Every write carries a *mode*:

``SET``       overwrite whatever is there,
``SOFT``      only replace air, fluids, plants, leaves and snow layers,
``AIR_ONLY``  only replace air.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .blocks import AIR, NOOP, Registry, format_state, is_air, replaceable

SET, SOFT, AIR_ONLY = 1, 2, 3


def _as_id(reg: Registry, b) -> int:
    if isinstance(b, (int, np.integer)):
        return int(b)
    return reg.id(b)


class Primitives:
    """Geometry helpers implemented on top of ``_fill_mask``."""

    reg: Registry

    # subclasses implement -------------------------------------------------
    def _fill_mask(self, x0: int, y0: int, z0: int, mask: np.ndarray, ids, mode: int) -> None:
        raise NotImplementedError

    # ---------------------------------------------------------------------
    def B(self, name: str, **props) -> int:
        return self.reg(name, **props)

    def set(self, x: int, y: int, z: int, b, mode: int = SET) -> None:
        self._fill_mask(int(x), int(y), int(z), np.ones((1, 1, 1), bool), _as_id(self.reg, b), mode)

    def box(self, x0, y0, z0, x1, y1, z1, b, mode: int = SET, hollow: bool = False) -> None:
        """Inclusive axis-aligned box."""
        xa, xb = sorted((int(x0), int(x1)))
        ya, yb = sorted((int(y0), int(y1)))
        za, zb = sorted((int(z0), int(z1)))
        shape = (xb - xa + 1, yb - ya + 1, zb - za + 1)
        m = np.ones(shape, bool)
        if hollow and min(shape) > 2:
            m[1:-1, 1:-1, 1:-1] = False
        self._fill_mask(xa, ya, za, m, _as_id(self.reg, b), mode)

    def walls(self, x0, y0, z0, x1, y1, z1, b, mode: int = SET) -> None:
        """Four vertical walls of an inclusive box (no floor/ceiling)."""
        xa, xb = sorted((int(x0), int(x1)))
        ya, yb = sorted((int(y0), int(y1)))
        za, zb = sorted((int(z0), int(z1)))
        m = np.zeros((xb - xa + 1, yb - ya + 1, zb - za + 1), bool)
        m[0, :, :] = m[-1, :, :] = True
        m[:, :, 0] = m[:, :, -1] = True
        self._fill_mask(xa, ya, za, m, _as_id(self.reg, b), mode)

    def column_mask(self, x0: int, z0: int, mask2d: np.ndarray, y0: int, y1: int, b,
                    mode: int = SET) -> None:
        """Extrude a 2-D (x,z) mask between y0..y1 inclusive."""
        if y1 < y0 or not mask2d.any():
            return
        h = int(y1) - int(y0) + 1
        m = np.repeat(mask2d[:, None, :], h, axis=1)
        self._fill_mask(int(x0), int(y0), int(z0), m, _as_id(self.reg, b), mode)

    def disk_mask(self, r: float, rz: float | None = None, inner: float = 0.0,
                  inner_z: float | None = None) -> tuple[np.ndarray, int]:
        rz = r if rz is None else rz
        R = int(math.ceil(max(r, rz)))
        xs = np.arange(-R, R + 1)[:, None]
        zs = np.arange(-R, R + 1)[None, :]
        d = (xs / max(r, 1e-6)) ** 2 + (zs / max(rz, 1e-6)) ** 2
        m = d <= 1.0 + 1e-9
        if inner > 0:
            iz = inner if inner_z is None else inner_z
            di = (xs / inner) ** 2 + (zs / iz) ** 2
            m &= di > 1.0
        return m, R

    def cyl(self, cx, cz, y0, y1, r, b, mode: int = SET, hollow: bool = False,
            thickness: float = 1.0, rz: float | None = None) -> None:
        inner = (r - thickness) if hollow else 0.0
        inner_z = ((rz if rz is not None else r) - thickness) if hollow else None
        m, R = self.disk_mask(r + 0.35, None if rz is None else rz + 0.35,
                              inner + 0.35 if hollow else 0.0,
                              inner_z + 0.35 if hollow and inner_z else None)
        self.column_mask(int(cx) - R, int(cz) - R, m, int(y0), int(y1), b, mode)

    def cone(self, cx, cz, y0, height, r0, r1, b, mode: int = SET, hollow: bool = False) -> None:
        """Frustum from radius r0 at y0 to r1 at y0+height-1."""
        for i in range(int(height)):
            t = i / max(1, height - 1)
            r = r0 + (r1 - r0) * t
            if r < 0.3:
                self.set(cx, y0 + i, cz, b, mode)
                continue
            self.cyl(cx, cz, y0 + i, y0 + i, r, b, mode, hollow=hollow, thickness=1.2)

    def ellipsoid(self, cx, cy, cz, rx, ry, rz, b, mode: int = SET, hollow: bool = False,
                  lower: bool = True, upper: bool = True) -> None:
        RX, RY, RZ = (int(math.ceil(v)) for v in (rx, ry, rz))
        xs = np.arange(-RX, RX + 1)[:, None, None]
        ys = np.arange(-RY, RY + 1)[None, :, None]
        zs = np.arange(-RZ, RZ + 1)[None, None, :]
        d = (xs / (rx + 0.3)) ** 2 + (ys / (ry + 0.3)) ** 2 + (zs / (rz + 0.3)) ** 2
        m = d <= 1.0
        if hollow:
            di = (xs / max(rx - 0.7, 0.5)) ** 2 + (ys / max(ry - 0.7, 0.5)) ** 2 + (zs / max(rz - 0.7, 0.5)) ** 2
            m &= di > 1.0
        if not lower:
            m[:, :RY, :] = False
        if not upper:
            m[:, RY + 1:, :] = False
        self._fill_mask(int(cx) - RX, int(cy) - RY, int(cz) - RZ, m, _as_id(self.reg, b), mode)

    def line(self, p0, p1, b, mode: int = SET, width: int = 1) -> None:
        (x0, y0, z0), (x1, y1, z1) = p0, p1
        n = int(max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))) + 1
        t = np.linspace(0.0, 1.0, n)
        xs = np.rint(x0 + (x1 - x0) * t).astype(int)
        ys = np.rint(y0 + (y1 - y0) * t).astype(int)
        zs = np.rint(z0 + (z1 - z0) * t).astype(int)
        bid = _as_id(self.reg, b)
        r = width // 2
        for dx in range(-r, width - r):
            for dz in range(-r, width - r):
                self.points(xs + dx, ys, zs + dz, bid, mode)

    def points(self, xs, ys, zs, b, mode: int = SET) -> None:
        xs = np.asarray(xs, dtype=np.int64).ravel()
        ys = np.asarray(ys, dtype=np.int64).ravel()
        zs = np.asarray(zs, dtype=np.int64).ravel()
        if xs.size == 0:
            return
        ids = np.broadcast_to(np.asarray(_as_id(self.reg, b) if not isinstance(b, np.ndarray) else b,
                                         dtype=np.uint16), xs.shape)
        x0, y0, z0 = xs.min(), ys.min(), zs.min()
        shape = (xs.max() - x0 + 1, ys.max() - y0 + 1, zs.max() - z0 + 1)
        if shape[0] * shape[1] * shape[2] <= 8_000_000:
            vol = np.zeros(shape, np.uint16)
            vol[xs - x0, ys - y0, zs - z0] = ids
            self._fill_mask(int(x0), int(y0), int(z0), vol != 0, vol, mode)
        else:  # very sparse and spread out: chunk the list
            order = np.argsort(xs, kind="stable")
            for part in np.array_split(order, max(2, int(math.ceil(xs.size / 50_000)))):
                if part.size:
                    self.points(xs[part], ys[part], zs[part], ids[part].copy(), mode)

    def stairs(self, name: str, facing: str, half: str = "bottom") -> int:
        return self.reg(name, facing=facing, half=half, shape="straight", waterlogged=False)

    def slab(self, name: str, typ: str = "bottom") -> int:
        return self.reg(name, type=typ, waterlogged=False)


# --------------------------------------------------------------------------
class Canvas(Primitives):
    """Dense local volume indexed [x, y, z]; id 0 means 'leave untouched'."""

    def __init__(self, reg: Registry, size: tuple[int, int, int]):
        self.reg = reg
        self.ids = np.zeros(size, np.uint16)
        self.mode = np.zeros(size, np.uint8)

    @property
    def size(self) -> tuple[int, int, int]:
        return self.ids.shape  # type: ignore[return-value]

    def _fill_mask(self, x0, y0, z0, mask, ids, mode):
        X, Y, Z = self.ids.shape
        sx, sy, sz = mask.shape
        ax, ay, az = max(0, x0), max(0, y0), max(0, z0)
        bx, by, bz = min(X, x0 + sx), min(Y, y0 + sy), min(Z, z0 + sz)
        if ax >= bx or ay >= by or az >= bz:
            return
        m = mask[ax - x0:bx - x0, ay - y0:by - y0, az - z0:bz - z0]
        tgt = self.ids[ax:bx, ay:by, az:bz]
        tm = self.mode[ax:bx, ay:by, az:bz]
        if isinstance(ids, np.ndarray):
            src = ids[ax - x0:bx - x0, ay - y0:by - y0, az - z0:bz - z0]
            m = m & (src != 0)
            tgt[m] = src[m]
        else:
            tgt[m] = ids
        tm[m] = mode

    def get(self, x, y, z) -> int:
        return int(self.ids[x, y, z])

    def replace(self, frm, to) -> None:
        f, t = _as_id(self.reg, frm), _as_id(self.reg, to)
        self.ids[self.ids == f] = t

    def rotated(self, quarter_turns: int) -> "Canvas":
        q = quarter_turns % 4
        ids, mode = self.ids, self.mode
        for _ in range(q):
            ids = np.flip(ids.transpose(2, 1, 0), axis=0)
            mode = np.flip(mode.transpose(2, 1, 0), axis=0)
        out = Canvas(self.reg, ids.shape)
        lut = self.reg.rotation_lut(q)
        out.ids = lut[ids]
        out.mode = mode.copy()
        return out

    def flipped_y(self) -> "Canvas":
        out = Canvas(self.reg, self.ids.shape)
        lut = self.reg.mirror_y_lut()
        out.ids = lut[self.ids[:, ::-1, :]]
        out.mode = self.mode[:, ::-1, :].copy()
        return out

    def connect(self) -> None:
        """Compute fence / wall / pane connection properties from neighbours."""
        connect_shapes(self.reg, self.ids)

    def paste(self, buf: "EditBuffer", wx: int, wy: int, wz: int, mode: int | None = None) -> None:
        """Paste so that canvas (0,0,0) lands on world (wx,wy,wz)."""
        if mode is None:
            for md in (SET, SOFT, AIR_ONLY):
                sel = (self.mode == md) & (self.ids != 0)
                if sel.any():
                    buf._fill_mask(wx, wy, wz, sel, self.ids, md)
        else:
            buf._fill_mask(wx, wy, wz, self.ids != 0, self.ids, mode)


# --------------------------------------------------------------------------
_FAMILY_CACHE: dict[int, tuple[int, bool]] = {}
_NON_FULL = ("stairs", "slab", "fence", "wall", "door", "pane", "bars", "lantern", "torch",
             "carpet", "button", "lever", "sign", "banner", "chain", "rod", "candle", "pot",
             "leaves", "glass", "ladder", "rail", "plate", "trapdoor", "head", "skull",
             "campfire", "scaffolding", "bed", "flower", "sapling", "grass", "snow", "vine")


def _family(reg: Registry, i: int) -> tuple[int, bool]:
    """(family, is_full_solid) - family 1 fence, 2 wall, 3 pane/bars."""
    r = _FAMILY_CACHE.get((id(reg), i))
    if r is not None:
        return r
    name, _ = reg.parsed(i)
    base = name.split(":")[-1]
    fam = 0
    if base.endswith("_fence") and "gate" not in base:
        fam = 1
    elif base.endswith("_wall") and "sign" not in base and "banner" not in base \
            and "torch" not in base and "head" not in base and "fan" not in base:
        fam = 2
    elif base.endswith("glass_pane") or base == "iron_bars":
        fam = 3
    full = i > AIR and fam == 0 and not any(t in base for t in _NON_FULL) \
        and not is_air(name, {}) and base not in ("water", "lava")
    r = (fam, full)
    _FAMILY_CACHE[(id(reg), i)] = r
    return r


def connect_shapes(reg: Registry, ids: np.ndarray) -> None:
    uniq = np.unique(ids)
    fams = {int(u): _family(reg, int(u)) for u in uniq}
    targets = [u for u, (f, _) in fams.items() if f]
    if not targets:
        return
    fam_arr = np.zeros(len(reg), np.uint8)
    full_arr = np.zeros(len(reg), bool)
    for u, (f, full) in fams.items():
        fam_arr[u] = f
        full_arr[u] = full
    padded = np.pad(ids, 1)
    fam_p = fam_arr[padded]
    full_p = full_arr[padded]
    dirs = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
    cache: dict[tuple[int, int], int] = {}
    for u in targets:
        f = fams[u][0]
        xs, ys, zs = np.nonzero(ids == u)
        bits = np.zeros(xs.size, np.int64)
        for k, (dname, (dx, dz)) in enumerate(dirs.items()):
            nf = fam_p[xs + 1 + dx, ys + 1, zs + 1 + dz]
            nfull = full_p[xs + 1 + dx, ys + 1, zs + 1 + dz]
            ok = (nf == f) | nfull | ((f == 2) & (nf == 3)) | ((f == 3) & (nf == 2))
            bits |= ok.astype(np.int64) << k
        name, props = reg.parsed(u)
        for b in np.unique(bits):
            key = (u, int(b))
            nid = cache.get(key)
            if nid is None:
                p = {k: v for k, v in props.items() if k not in dirs and k != "up"}
                on = {d: bool(int(b) >> k & 1) for k, d in enumerate(dirs)}
                if f == 2:
                    for d in dirs:
                        p[d] = "low" if on[d] else "none"
                    straight = (on["north"] and on["south"] and not on["east"] and not on["west"]) or \
                               (on["east"] and on["west"] and not on["north"] and not on["south"])
                    p["up"] = "false" if straight else "true"
                else:
                    for d in dirs:
                        p[d] = "true" if on[d] else "false"
                nid = reg.id(format_state(name, p))
                cache[key] = nid
            sel = bits == b
            ids[xs[sel], ys[sel], zs[sel]] = nid


# --------------------------------------------------------------------------
class EditBuffer(Primitives):
    """Sparse world-space edits grouped into 16³ sections."""

    def __init__(self, reg: Registry):
        self.reg = reg
        self.secs: dict[tuple[int, int, int], tuple[np.ndarray, np.ndarray]] = {}
        self.block_entities: list[dict] = []

    def __len__(self) -> int:
        return len(self.secs)

    def _sec(self, cx: int, sy: int, cz: int):
        k = (cx, sy, cz)
        s = self.secs.get(k)
        if s is None:
            s = (np.zeros((16, 16, 16), np.uint16), np.zeros((16, 16, 16), np.uint8))
            self.secs[k] = s
        return s

    def _fill_mask(self, x0, y0, z0, mask, ids, mode):
        sx, sy, sz = mask.shape
        arr = isinstance(ids, np.ndarray)
        for cx in range(x0 >> 4, (x0 + sx - 1 >> 4) + 1):
            ax, bx = max(x0, cx * 16), min(x0 + sx, cx * 16 + 16)
            for cz in range(z0 >> 4, (z0 + sz - 1 >> 4) + 1):
                az, bz = max(z0, cz * 16), min(z0 + sz, cz * 16 + 16)
                sub_xz = mask[ax - x0:bx - x0, :, az - z0:bz - z0]
                if not sub_xz.any():
                    continue
                for cy in range(y0 >> 4, (y0 + sy - 1 >> 4) + 1):
                    ay, by = max(y0, cy * 16), min(y0 + sy, cy * 16 + 16)
                    m = sub_xz[:, ay - y0:by - y0, :]
                    if arr:
                        src = ids[ax - x0:bx - x0, ay - y0:by - y0, az - z0:bz - z0]
                        m = m & (src != 0)
                    if not m.any():
                        continue
                    sid, smode = self._sec(cx, cy, cz)
                    # section arrays are [y, z, x]
                    tgt = sid[ay - cy * 16:by - cy * 16, az - cz * 16:bz - cz * 16, ax - cx * 16:bx - cx * 16]
                    tmd = smode[ay - cy * 16:by - cy * 16, az - cz * 16:bz - cz * 16, ax - cx * 16:bx - cx * 16]
                    mt = m.transpose(1, 2, 0)
                    if arr:
                        tgt[mt] = src.transpose(1, 2, 0)[mt]
                    else:
                        tgt[mt] = ids
                    tmd[mt] = mode

    def fill_columns(self, x0: int, z0: int, ylo: np.ndarray, yhi: np.ndarray, b,
                     mode: int = SET) -> None:
        """For every column (x0+i, z0+j) fill ylo[i,j] <= y < yhi[i,j].

        ``b`` is a block (id / state string) or an int array shaped like ylo.
        """
        ylo = np.asarray(ylo, dtype=np.int32)
        yhi = np.asarray(yhi, dtype=np.int32)
        W, L = ylo.shape
        per_col = isinstance(b, np.ndarray)
        bid = None if per_col else _as_id(self.reg, b)
        for cx in range(x0 >> 4, (x0 + W - 1 >> 4) + 1):
            ax, bx = max(x0, cx * 16), min(x0 + W, cx * 16 + 16)
            for cz in range(z0 >> 4, (z0 + L - 1 >> 4) + 1):
                az, bz = max(z0, cz * 16), min(z0 + L, cz * 16 + 16)
                lo = ylo[ax - x0:bx - x0, az - z0:bz - z0]
                hi = yhi[ax - x0:bx - x0, az - z0:bz - z0]
                valid = hi > lo
                if not valid.any():
                    continue
                ymin, ymax = int(lo[valid].min()), int(hi[valid].max()) - 1
                ids2 = b[ax - x0:bx - x0, az - z0:bz - z0].astype(np.uint16) if per_col else None
                for cy in range(ymin >> 4, (ymax >> 4) + 1):
                    ys = np.arange(cy * 16, cy * 16 + 16)[:, None, None]
                    # [y, z, x]
                    m = (ys >= lo.T[None]) & (ys < hi.T[None])
                    if not m.any():
                        continue
                    sid, smode = self._sec(cx, cy, cz)
                    sl = (slice(None), slice(az - cz * 16, bz - cz * 16), slice(ax - cx * 16, bx - cx * 16))
                    tgt = sid[sl]
                    tmd = smode[sl]
                    if per_col:
                        full = np.broadcast_to(ids2.T[None], m.shape)
                        m = m & (full != 0)
                        tgt[m] = full[m]
                    else:
                        tgt[m] = bid
                    tmd[m] = mode

    def add_block_entity(self, x: int, y: int, z: int, nbt_factory) -> None:
        """``nbt_factory(chunk_data_version) -> Compound`` (without x/y/z), or None to skip."""
        self.block_entities.append({"pos": (x, y, z), "factory": nbt_factory})

    def clear_box(self, x0: int, z0: int, x1: int, z1: int, y0: int = -64, y1: int = 319) -> None:
        """Forget every edit inside the box (used to swap in an imported build)."""
        for (cx, cy, cz), (sid, smd) in self.secs.items():
            if cx * 16 > x1 or cx * 16 + 15 < x0 or cz * 16 > z1 or cz * 16 + 15 < z0 \
                    or cy * 16 > y1 or cy * 16 + 15 < y0:
                continue
            ys = slice(max(y0 - cy * 16, 0), min(y1 - cy * 16, 15) + 1)
            zs = slice(max(z0 - cz * 16, 0), min(z1 - cz * 16, 15) + 1)
            xs = slice(max(x0 - cx * 16, 0), min(x1 - cx * 16, 15) + 1)
            sid[ys, zs, xs] = 0
            smd[ys, zs, xs] = 0
        self.block_entities = [b for b in self.block_entities
                               if not (x0 <= b["pos"][0] <= x1 and z0 <= b["pos"][2] <= z1
                                       and y0 <= b["pos"][1] <= y1)]

    def merge_from(self, other: "EditBuffer") -> None:
        for k, (oid, omd) in other.secs.items():
            sid, smd = self._sec(*k)
            m = omd != 0
            sid[m] = oid[m]
            smd[m] = omd[m]
        self.block_entities.extend(other.block_entities)

    def bbox(self) -> tuple[int, int, int, int, int, int] | None:
        if not self.secs:
            return None
        keys = np.array(list(self.secs.keys()))
        mins = keys.min(axis=0) * 16
        maxs = keys.max(axis=0) * 16 + 15
        return int(mins[0]), int(mins[1]), int(mins[2]), int(maxs[0]), int(maxs[1]), int(maxs[2])

    def iter_voxels(self):
        """Yield (xs, ys, zs, ids) arrays per section for exporting/rendering."""
        for (cx, cy, cz), (sid, smd) in self.secs.items():
            m = (smd != 0) & (sid != NOOP)
            if not m.any():
                continue
            ys, zs, xs = np.nonzero(m)
            yield xs + cx * 16, ys + cy * 16, zs + cz * 16, sid[ys, zs, xs], smd[ys, zs, xs]

    def count(self) -> int:
        return int(sum(int((m != 0).sum()) for _, m in self.secs.values()))


# --------------------------------------------------------------------------
def apply_buffers(world, buffers: Iterable[EditBuffer], out_region_dir=None, log=print,
                  promote_full: bool = True) -> dict:
    """Apply buffers (in order) to the world's chunks and rewrite regions.

    ``promote_full`` marks edited proto-chunks (e.g. WorldPainter's
    ``liquid_carvers`` status) as ``full`` so the game does not run vanilla
    feature generation (trees, lakes, flowers) over the new structures.
    """
    from nbtlib import tag as T

    buffers = [b for b in buffers if b is not None and (b.secs or b.block_entities)]
    reg = world.reg
    by_chunk: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for bi, b in enumerate(buffers):
        for (cx, cy, cz) in b.secs:
            by_chunk.setdefault((cx, cz), []).append((bi, cy, 0))
        for be in b.block_entities:
            x, y, z = be["pos"]
            by_chunk.setdefault((x >> 4, z >> 4), [])
    by_region: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for (cx, cz) in by_chunk:
        by_region.setdefault((cx >> 5, cz >> 5), []).append((cx, cz))

    stats = {"chunks": 0, "missing_chunks": 0, "blocks": 0}
    luts = _LutCache(reg)
    for (rx, rz), chunks in sorted(by_region.items()):
        rf = world.region(rx, rz)
        for (cx, cz) in chunks:
            ch = world.load_chunk(cx, cz)
            if ch is None:
                stats["missing_chunks"] += 1
                continue
            lo_sy, hi_sy = ch.section_range()
            for b in buffers:
                for cy in sorted({k[1] for k in b.secs if k[0] == cx and k[2] == cz}):
                    if cy < lo_sy or cy > hi_sy:
                        continue  # outside the world's build height
                    sid, smd = b.secs[(cx, cy, cz)]
                    arr = ch.section_array(cy, create=True)
                    repl_lut, air_lut = luts.get()
                    m1 = smd == SET
                    m2 = (smd == SOFT) & repl_lut[arr]
                    m3 = (smd == AIR_ONLY) & air_lut[arr]
                    m = m1 | m2 | m3
                    if m.any():
                        arr[m] = sid[m]
                        ch.mark_dirty(cy)
                        stats["blocks"] += int(m.sum())
            bes_here = [be for b in buffers for be in b.block_entities
                        if be["pos"][0] >> 4 == cx and be["pos"][2] >> 4 == cz]
            if ch.dirty or bes_here:
                root = ch.encode()
                if promote_full:
                    st = str(root.get("Status", "minecraft:full"))
                    if st.split(":")[-1] != "full":
                        root["Status"] = T.String("minecraft:full")
                        stats["promoted"] = stats.get("promoted", 0) + 1
                for be in bes_here:
                    x, y, z = be["pos"]
                    nbt = be["factory"](ch.data_version or world.data_version)
                    if nbt is None:
                        continue
                    nbt["x"], nbt["y"], nbt["z"] = T.Int(x), T.Int(y), T.Int(z)
                    ch.add_block_entity(nbt)
                rf.put_nbt(cx & 31, cz & 31, root)
                stats["chunks"] += 1
        target = None if out_region_dir is None else out_region_dir / rf.path.name
        rf.save(target)
        world.drop_region(rx, rz)
    return stats


class _LutCache:
    def __init__(self, reg: Registry):
        self.reg = reg
        self.n = -1
        self.luts = None

    def get(self):
        if self.n != len(self.reg):
            self.luts = (self.reg.lut(replaceable), self.reg.lut(is_air))
            self.n = len(self.reg)
        return self.luts
