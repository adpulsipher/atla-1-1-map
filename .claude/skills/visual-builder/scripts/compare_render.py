#!/usr/bin/env python3
"""Render a build and compare it with the reference image.

Usage:
    python compare_render.py REFERENCE.png PAGE.html|URL [--out DIR] [--scale 1]
    python compare_render.py REFERENCE.png --render SCREENSHOT.png [--out DIR]

Renders the page in a headless browser at the reference's size (Python
Playwright if installed, otherwise a Chrome/Chromium binary on PATH), then
writes render.png, side_by_side.png and diff.png (bright = mismatch) to DIR
and prints a mismatch score (0% = identical).  Needs Pillow and numpy.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageChops, ImageOps
except ImportError:  # pragma: no cover
    sys.exit("Pillow and numpy are required: pip install pillow numpy")


def to_url(target: str) -> str:
    if "://" in target:
        return target
    return Path(target).resolve().as_uri()


def render_playwright(url: str, w: int, h: int, scale: float, out: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": int(w / scale), "height": int(h / scale)},
                                device_scale_factor=scale)
        page.goto(url, wait_until="networkidle")
        page.screenshot(path=str(out), full_page=False)
        browser.close()
    return True


def find_chrome() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base:
        for cand in sorted(Path(base).glob("chromium*/chrome-linux*/chrome")):
            return str(cand)
    return None


def render_cli(url: str, w: int, h: int, out: Path) -> bool:
    chrome = find_chrome()
    if not chrome:
        return False
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           f"--window-size={w},{h}", f"--screenshot={out}", url]
    subprocess.run(cmd, capture_output=True, timeout=120)
    return out.exists()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("page", nargs="?", help="HTML file or URL to render")
    ap.add_argument("--render", help="use an existing screenshot instead of rendering")
    ap.add_argument("--out", default="compare")
    ap.add_argument("--scale", type=float, default=1.0, help="device pixel ratio of the reference (2 for retina)")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ref = Image.open(a.reference).convert("RGB")
    render_path = out / "render.png"
    if a.render:
        shutil.copy(a.render, render_path)
    elif a.page:
        url = to_url(a.page)
        ok = render_playwright(url, ref.width, ref.height, a.scale, render_path) or \
            render_cli(url, ref.width, ref.height, render_path)
        if not ok:
            sys.exit("No headless browser found (install Playwright or Chrome), or pass --render SCREENSHOT.png")
    else:
        sys.exit("give a PAGE to render or --render SCREENSHOT.png")

    ren = Image.open(render_path).convert("RGB")
    if ren.size != ref.size:
        print(f"note: render {ren.size} resized to reference {ref.size} for comparison")
        ren = ren.resize(ref.size, Image.LANCZOS)
    diff = ImageChops.difference(ref, ren)
    arr = np.asarray(diff, dtype=np.float32)
    score = arr.mean() / 255 * 100
    # share of pixels that are visibly different (>10% in any channel)
    changed = (arr.max(axis=2) > 25).mean() * 100
    ImageOps.autocontrast(diff.convert("L")).save(out / "diff.png")
    side = Image.new("RGB", (ref.width * 2 + 10, ref.height), (255, 0, 255))
    side.paste(ref, (0, 0))
    side.paste(ren, (ref.width + 10, 0))
    side.save(out / "side_by_side.png")
    print(f"mean mismatch: {score:.2f}%   visibly different pixels: {changed:.1f}%")
    print(f"wrote {out / 'render.png'}, {out / 'side_by_side.png'}, {out / 'diff.png'}")
    # rows/columns with the most mismatch point at layout offsets
    rows = arr.max(axis=2).mean(axis=1)
    cols = arr.max(axis=2).mean(axis=0)
    print(f"worst row band: y~{int(rows.argmax())}   worst column band: x~{int(cols.argmax())}")


if __name__ == "__main__":
    main()
