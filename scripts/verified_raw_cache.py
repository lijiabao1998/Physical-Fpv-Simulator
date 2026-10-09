"""Offline, exact-manifest raw-input cache. No network or model execution."""

import argparse
import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    "data/manifest.json",
    "data/thermal-manifest.json",
    "data/stanford-manifest.json",
    "docs/stanford-acquisition-protocol.md",
)
FORMAT = "physical-fpv-six-raw-inputs-v1"
BUNDLE = ".cache/fpv-raw-v1/bundle.zip"
MAX_BUNDLE_BYTES = 27_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def safe_path(root, relative):
    parts = PurePosixPath(relative).parts
    if (
        not parts
        or PurePosixPath(relative).is_absolute()
        or ".." in parts
        or "\\" in relative
        or str(PurePosixPath(relative)) != relative
    ):
        raise ValueError("Unsafe cache destination")
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Symlink cache root rejected")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symlink rejected: {relative}")
    return path


def regular_bytes(root, relative, limit):
    path = safe_path(root, relative)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        status = os.fstat(stream.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or status.st_size > limit:
            raise ValueError(f"Nonregular, linked or oversized input: {relative}")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Oversized input: {relative}")
    return data


def specification(root=ROOT):
    contents = {name: regular_bytes(root, name, 2_000_000) for name in MANIFESTS}
    chen, thermal, stanford = (json.loads(contents[name]) for name in MANIFESTS[:3])
    entries = []
    for entry in chen["files"]:
        entries.append(
            {
                "path": "data/raw/" + entry["name"],
                "bytes": entry["bytes"],
                "sha256": entry["sha256"],
                "md5": entry["md5"],
                "source": chen["record_url"] + "/files/" + entry["name"] + "?download=1",
                "doi": chen["dataset_doi"],
                "license": chen["license"],
            }
        )
    entries.append(
        {
            "path": "data/oregan/raw/validation.zip",
            "bytes": thermal["archive_bytes"],
            "sha256": thermal["archive_sha256"],
            "md5": thermal["archive_md5"],
            "source": thermal["archive_url"],
            "doi": thermal["dataset_doi"],
            "license": thermal["archive_license"],
        }
    )
    pilot = sorted(stanford["files"], key=lambda entry: entry["filename"])[:1]
    pilot.append(stanford["manufacturer_specification"])
    for entry in pilot:
        entries.append(
            {
                "path": "data/stanford/raw/" + entry["filename"],
                "bytes": entry["size"],
                "sha256": entry["content_details"]["sha256_hash"],
                "source": entry["content_details"]["download_url"],
                "license": "CC-BY-4.0",
                "doi": "10.17632/kxsbr4x3j2.2",
            }
        )
    expected = {
        "data/raw/LGM50_cell02.csv",
        "data/raw/LGM50_cell03.csv",
        "data/raw/LGM50_cell04.csv",
        "data/oregan/raw/validation.zip",
        "data/stanford/raw/NMC_k1_1C_25degC.xlsx",
        "data/stanford/raw/manufactuer_specifications.xlsx",
    }
    if len(entries) != 6 or {entry["path"] for entry in entries} != expected:
        raise ValueError("Raw acquisition selection changed; review cache format first")
    for entry in entries:
        safe_path(root, entry["path"])
        if not isinstance(entry["bytes"], int) or not 0 < entry["bytes"] < 24_000_001:
            raise ValueError("Invalid raw byte budget")
    if sum(entry["bytes"] for entry in entries) >= MAX_BUNDLE_BYTES - 100_000:
        raise ValueError("Raw cache exceeds bounded budget")
    return {
        "format": FORMAT,
        "source_manifests": {name: json.loads(contents[name]) for name in MANIFESTS[:3]},
        "payload_modifications": "None: all six original payload byte sequences are unchanged",
        "license_urls": {"CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/"},
        "manifest_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in contents.items()
        },
        "files": entries,
    }


def cache_key(spec):
    return "fpv-raw-v1-" + hashlib.sha256(canonical(spec)).hexdigest()


def verify_content(content, entry):
    if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError(f"Raw size/SHA256 mismatch: {entry['path']}")
    if "md5" in entry and hashlib.md5(content, usedforsecurity=False).hexdigest() != entry["md5"]:
        raise ValueError(f"Raw MD5 mismatch: {entry['path']}")


def verify_files(root=ROOT):
    spec = specification(root)
    for entry in spec["files"]:
        verify_content(regular_bytes(root, entry["path"], entry["bytes"]), entry)
    return spec


def pack(root=ROOT):
    spec = verify_files(root)
    target = safe_path(root, BUNDLE)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in [("manifest.json", canonical(spec))] + [
                (entry["path"], regular_bytes(root, entry["path"], entry["bytes"]))
                for entry in spec["files"]
            ]:
                if name != "manifest.json":
                    verify_content(content, next(e for e in spec["files"] if e["path"] == name))
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, content)
        if temporary.stat().st_size > MAX_BUNDLE_BYTES:
            raise ValueError("Oversized cache bundle")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return spec


def restore(root=ROOT):
    spec = specification(root)
    raw = regular_bytes(root, BUNDLE, MAX_BUNDLE_BYTES)
    expected = {entry["path"]: entry for entry in spec["files"]}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != 7 or len(set(names)) != 7 or set(names) != {"manifest.json", *expected}:
            raise ValueError("Unexpected or duplicate cache members")
        if archive.comment:
            raise ValueError("Unexpected cache archive metadata")
        for info in archive.infolist():
            mode = info.external_attr >> 16
            limit = (
                len(canonical(spec))
                if info.filename == "manifest.json"
                else expected[info.filename]["bytes"]
            )
            if (
                info.create_system != 3
                or not stat.S_ISREG(mode)
                or info.is_dir()
                or info.file_size != limit
                or info.compress_size != limit
                or info.compress_type != zipfile.ZIP_STORED
                or info.extra
                or info.comment
            ):
                raise ValueError("Unsafe or oversized cache member")
        if archive.read("manifest.json") != canonical(spec):
            raise ValueError("Cache manifest identity mismatch")
        # Validate all bytes before changing any destination; no extraction API is used.
        contents = {path: archive.read(path) for path in expected}
        for path, content in contents.items():
            verify_content(content, expected[path])
            existing = safe_path(root, path)
            if existing.exists():
                verify_content(regular_bytes(root, path, expected[path]["bytes"]), expected[path])
        with tempfile.TemporaryDirectory(prefix="fpv-raw-stage-", dir=Path(root)) as stage:
            for index, (path, content) in enumerate(contents.items()):
                staged = Path(stage) / str(index)
                staged.write_bytes(content)
                target = safe_path(root, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(target)
    return verify_files(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("key", "verify", "pack", "restore"))
    args = parser.parse_args()
    if args.operation == "key":
        print(cache_key(specification()))
    else:
        spec = {"verify": verify_files, "pack": pack, "restore": restore}[args.operation]()
        print(json.dumps({"verified_files": len(spec["files"]), "cache_key": cache_key(spec)}))


if __name__ == "__main__":
    main()
