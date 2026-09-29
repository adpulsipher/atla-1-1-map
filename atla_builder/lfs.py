"""Resolve Git LFS pointer files (e.g. from GitHub's "Download ZIP").

GitHub source archives contain the small LFS *pointer* instead of the real
``ATLAB9k.zip``.  This module recognises such a pointer and downloads the real
object through the Git LFS batch API, verifying its SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "adpulsipher/atla-1-1-map"
SPEC = b"version https://git-lfs.github.com/spec/v1"


class LfsError(RuntimeError):
    pass


def read_pointer(path: Path) -> tuple[str, int] | None:
    """(oid, size) if ``path`` is a Git LFS pointer file, else None."""
    path = Path(path)
    try:
        if path.stat().st_size > 1024:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(SPEC):
        return None
    oid = re.search(rb"oid sha256:([0-9a-f]{64})", data)
    size = re.search(rb"size (\d+)", data)
    if not oid or not size:
        return None
    return oid.group(1).decode(), int(size.group(1))


def repo_slug(start: Path) -> str:
    """owner/repo from the git remote of ``start`` (falls back to DEFAULT_REPO)."""
    env = os.environ.get("ATLA_LFS_REPO")
    if env:
        return env
    try:
        url = subprocess.run(["git", "-C", str(start), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_REPO


def _request(url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    return urllib.request.urlopen(req, timeout=60)


def fetch(pointer: Path, dest: Path, repo: str | None = None, log=print) -> Path:
    """Download the object behind ``pointer`` to ``dest`` (reused if already valid)."""
    info = read_pointer(pointer)
    if info is None:
        raise LfsError(f"{pointer} is not a Git LFS pointer")
    oid, size = info
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size == size and _sha256(dest) == oid:
        log(f"using cached {dest}")
        return dest
    repo = repo or repo_slug(Path(pointer).resolve().parent)
    headers = {"Accept": "application/vnd.git-lfs+json", "Content-Type": "application/vnd.git-lfs+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    body = json.dumps({"operation": "download", "transfers": ["basic"],
                       "objects": [{"oid": oid, "size": size}]}).encode()
    batch = f"https://github.com/{repo}.git/info/lfs/objects/batch"
    log(f"{pointer.name} is a Git LFS pointer; fetching the real file ({size / 1e6:.0f} MB) from {repo} ...")
    try:
        with _request(batch, body, headers) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        hint = (" The repository is private: set GITHUB_TOKEN to a token with read access and retry."
                if e.code in (401, 403, 404) else "")
        raise LfsError(f"Git LFS batch request failed ({e.code} {e.reason}).{hint}") from e
    obj = resp.get("objects", [{}])[0]
    if "error" in obj:
        raise LfsError(f"GitHub LFS: {obj['error'].get('message')}")
    action = obj.get("actions", {}).get("download")
    if not action:
        raise LfsError("GitHub LFS returned no download URL")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    done = 0
    with _request(action["href"], None, action.get("header", {})) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if done % (50 << 20) < (1 << 20):
                log(f"  {done / 1e6:6.0f} / {size / 1e6:.0f} MB")
    if done != size or h.hexdigest() != oid:
        tmp.unlink(missing_ok=True)
        raise LfsError("downloaded file does not match the LFS pointer (size/SHA-256 mismatch)")
    os.replace(tmp, dest)
    log(f"downloaded {dest} (SHA-256 verified)")
    return dest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
