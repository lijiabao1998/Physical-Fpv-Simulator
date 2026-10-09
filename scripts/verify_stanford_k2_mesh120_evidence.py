"""Reassemble and independently reproduce the immutable one-shot mesh120 result."""

import argparse
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from compare_stanford_k2_mesh120 import compare
from compare_stanford_k2_rates import require_reproduction

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = "a3b737252dd5893c4d2039ca9b049a4818b091cf5d771aa261a356f52cb66e2e"
SOURCE_COMMIT = "5655bda1527c0941f99717018dc06553a7283dea"
RUN_ID = "37960046810"


def archive_bytes(root=ROOT):
    manifest = json.loads((root / "docs/benchmarks/stanford-k2-mesh120-artifact.json").read_text())
    parts = manifest["parts"]
    if len(parts) != 3:
        raise ValueError("Mesh120 evidence part count changed")
    content = []
    for index, part in enumerate(parts, 1):
        expected = f"docs/benchmarks/stanford-k2-mesh120-evidence.zip.{index:03d}"
        if part["path"] != expected:
            raise ValueError("Mesh120 evidence part path changed")
        raw = (root / expected).read_bytes()
        if len(raw) != part["bytes"] or hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError("Mesh120 evidence part hash/size mismatch")
        content.append(raw)
    raw = b"".join(content)
    if len(raw) != 22462499 or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Reassembled mesh120 artifact identity changed")
    return raw


def verify(root=ROOT):
    raw = archive_bytes(root)
    with tempfile.TemporaryDirectory(prefix="fpv-mesh120-verify-") as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if (
                len(names) != 86
                or len(set(names)) != 86
                or any(name.startswith("/") or ".." in Path(name).parts for name in names)
            ):
                raise ValueError("Unexpected mesh120 artifact members")
            if any(name.startswith("evidence/mesh80/") for name in names):
                raise ValueError("Unreviewed new mesh80 execution")
            archive.extractall(directory)
        result = compare(directory / "evidence")
        if result["source_commit"] != SOURCE_COMMIT or result["run_id"] != RUN_ID:
            raise ValueError("Wrong mesh120 experiment identity")
        saved = json.loads((directory / "evidence/mesh-comparison.json").read_text())
        require_reproduction(saved, result)
        committed = json.loads(
            (root / "docs/benchmarks/stanford-k2-mesh120-result.json").read_text()
        )
        require_reproduction(committed, result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = verify()
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")
