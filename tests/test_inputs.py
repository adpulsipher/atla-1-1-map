"""Input handling: Git LFS pointers from GitHub's "Download ZIP" and bad zips."""
import importlib
import sys

import pytest

from atla_builder import lfs
from atla_builder.pipeline import _extract_if_zip

POINTER = (b"version https://git-lfs.github.com/spec/v1\n"
           b"oid sha256:baf28b09a6bebd9e7fe468fcab3f98a1ec202664c5c96b91180f8ca04ccb4cdd\n"
           b"size 772572129\n")


def test_reads_lfs_pointer(tmp_path):
    p = tmp_path / "ATLAB9k.zip"
    p.write_bytes(POINTER)
    assert lfs.read_pointer(p) == ("baf28b09a6bebd9e7fe468fcab3f98a1ec202664c5c96b91180f8ca04ccb4cdd", 772572129)
    q = tmp_path / "real.zip"
    q.write_bytes(b"PK\x03\x04" + b"\0" * 2000)
    assert lfs.read_pointer(q) is None


def test_pointer_is_resolved_before_unzipping(tmp_path, monkeypatch):
    p = tmp_path / "ATLAB9k.zip"
    p.write_bytes(POINTER)
    calls = []

    def fake_fetch(pointer, dest, repo=None, log=print):
        calls.append((pointer, dest))
        raise lfs.LfsError("offline in tests")

    monkeypatch.setattr(lfs, "fetch", fake_fetch)
    with pytest.raises(lfs.LfsError):
        _extract_if_zip(p, tmp_path / "work", lambda *a: None)
    assert calls and calls[0][0] == p


def test_non_zip_gives_clear_error(tmp_path):
    p = tmp_path / "broken.zip"
    p.write_bytes(b"not a zip at all" * 200)
    with pytest.raises(ValueError, match="not a zip file"):
        _extract_if_zip(p, tmp_path / "work", lambda *a: None)


def test_importing_main_module_does_not_start_a_build(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["atla_builder"])
    sys.modules.pop("atla_builder.__main__", None)
    importlib.import_module("atla_builder.__main__")
