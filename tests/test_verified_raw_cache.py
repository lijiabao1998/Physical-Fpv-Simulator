"""Transport never substitutes missing/corrupt raw bytes or invokes acquisition."""

import hashlib
import importlib
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
cache = importlib.import_module("verified_raw_cache")
logger = importlib.import_module("log_raw_source_requests")


@pytest.fixture
def payloads(tmp_path, monkeypatch):
    spec = cache.specification()
    for index, entry in enumerate(spec["files"]):
        content = f"synthetic test fixture {index}".encode()
        entry["bytes"] = len(content)
        entry["sha256"] = hashlib.sha256(content).hexdigest()
        if "md5" in entry:
            entry["md5"] = hashlib.md5(content, usedforsecurity=False).hexdigest()
        path = tmp_path / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    monkeypatch.setattr(cache, "specification", lambda root=tmp_path: spec)
    return tmp_path, spec


def remove_payloads(root, spec):
    for entry in spec["files"]:
        (root / entry["path"]).unlink()


def test_exact_manifest_identity_includes_protocol_and_file_bytes(tmp_path):
    original = cache.specification()
    assert len(original["files"]) == 6
    assert sum(entry["bytes"] for entry in original["files"]) == 26_818_880
    for name in cache.MANIFESTS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    assert cache.cache_key(cache.specification(tmp_path)) == cache.cache_key(original)
    path = tmp_path / cache.MANIFESTS[-1]
    path.write_bytes(path.read_bytes() + b"\n")
    assert cache.cache_key(cache.specification(tmp_path)) != cache.cache_key(original)


def test_round_trip_rehashes_every_input_without_network(payloads, monkeypatch):
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("No network"))
    root, spec = payloads
    originals = {entry["path"]: (root / entry["path"]).read_bytes() for entry in spec["files"]}
    cache.pack(root)
    remove_payloads(root, spec)
    assert cache.restore(root) == spec
    assert {path: (root / path).read_bytes() for path in originals} == originals
    for entry in spec["files"]:
        path = root / entry["path"]
        original = path.read_bytes()
        path.write_bytes(b"X" + original[1:])
        with pytest.raises(ValueError, match="mismatch"):
            cache.verify_files(root)
        path.write_bytes(original)


def test_missing_payload_cannot_seed_cache(payloads):
    root, spec = payloads
    (root / spec["files"][0]["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        cache.pack(root)
    assert not (root / cache.BUNDLE).exists()


def test_corrupt_existing_payload_is_not_replaced(payloads):
    root, spec = payloads
    cache.pack(root)
    bad = root / spec["files"][0]["path"]
    bad.write_bytes(b"bad")
    with pytest.raises(ValueError, match="mismatch"):
        cache.restore(root)
    assert bad.read_bytes() == b"bad"


def rewrite_bundle(root, transform):
    path = root / cache.BUNDLE
    with zipfile.ZipFile(path) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for info, content in transform(members):
            archive.writestr(info, content)
    path.write_bytes(output.getvalue())


@pytest.mark.parametrize(
    "damage", ["missing", "extra", "duplicate", "bytes", "manifest", "symlink", "compressed"]
)
def test_bad_bundle_fails_before_any_installation(payloads, damage):
    root, spec = payloads
    cache.pack(root)
    remove_payloads(root, spec)

    def alter(members):
        if damage == "missing":
            return members[:-1]
        if damage == "duplicate":
            return members + [members[-1]]
        if damage == "extra":
            return members + [(zipfile.ZipInfo("../escape"), b"bad")]
        index = 0 if damage == "manifest" else 1
        info, content = members[index]
        if damage in {"bytes", "manifest"}:
            members[index] = (info, b"X" + content[1:])
        elif damage == "symlink":
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        elif damage == "compressed":
            info.compress_type = zipfile.ZIP_DEFLATED
        return members

    with (
        pytest.warns(UserWarning)
        if damage == "duplicate"
        else __import__("contextlib").nullcontext()
    ):
        rewrite_bundle(root, alter)
    with pytest.raises(ValueError):
        cache.restore(root)
    assert all(not (root / entry["path"]).exists() for entry in spec["files"])


def test_symlinked_parent_and_hardlink_rejected(payloads, tmp_path):
    root, spec = payloads
    source = root / spec["files"][0]["path"]
    os.link(source, root / "other-link")
    with pytest.raises(ValueError, match="linked"):
        cache.verify_files(root)
    (root / "other-link").unlink()
    parent = root / "link"
    parent.symlink_to(source.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        cache.regular_bytes(root, "link/" + source.name, 100)


def test_key_has_no_restore_prefix_equivalence():
    spec = cache.specification()
    other = json.loads(json.dumps(spec))
    other["files"][0]["sha256"] = "0" * 64
    assert cache.cache_key(spec) != cache.cache_key(other)


def test_logger_reports_only_known_input_never_url_headers_or_redirect_token():
    spec = cache.specification()
    output = io.StringIO()
    audit = logger.request_logger(spec, output)
    audit("urllib.Request", (spec["files"][0]["source"], b"secret-body", {"token": "secret"}))
    audit("urllib.Request", ("https://example.test/private?token=secret", b"", {}))
    text = output.getvalue()
    assert text == "Pinned source request: data/raw/LGM50_cell02.csv\n"
    assert "secret" not in text and "https" not in text


def test_fifo_rejected_without_blocking(tmp_path):
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(ValueError, match="Nonregular"):
        cache.regular_bytes(tmp_path, "pipe", 100)


def test_symlink_cache_root_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink cache root"):
        cache.safe_path(linked, "file")
