"""Reassemble and independently reproduce the immutable one-shot tolerance result."""

import argparse
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from compare_stanford_k2_rates import require_reproduction
from compare_stanford_k2_tolerance import compare

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = "a35aa5d8dc2fb0c744f2f62fd4d0ea46eba553c4885aeed2a674fd2aa04b56da"
SOURCE_COMMIT = "c8e3088fd808b213992285cabfaf9b69e9528d89"
RUN_ID = "37954785347"


def archive_bytes(root=ROOT):
    manifest = json.loads(
        (root / "docs/benchmarks/stanford-k2-tolerance-artifact.json").read_text()
    )
    parts = manifest["parts"]
    if len(parts) != 4:
        raise ValueError("Tolerance evidence part count changed")
    content = []
    for index, part in enumerate(parts, 1):
        expected = f"docs/benchmarks/stanford-k2-tolerance-evidence.zip.{index:03d}"
        if part["path"] != expected:
            raise ValueError("Tolerance evidence part path changed")
        raw = (root / expected).read_bytes()
        if len(raw) != part["bytes"] or hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError("Tolerance evidence part hash/size mismatch")
        content.append(raw)
    raw = b"".join(content)
    if len(raw) != 27644650 or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("Reassembled tolerance artifact identity changed")
    return raw


def verify(root=ROOT):
    raw = archive_bytes(root)
    with tempfile.TemporaryDirectory(prefix="fpv-tolerance-verify-") as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if (
                len(names) != 72
                or len(set(names)) != 72
                or any(name.startswith("/") or ".." in Path(name).parts for name in names)
            ):
                raise ValueError("Unexpected tolerance artifact members")
            if any(name.startswith("evidence/mesh120/") for name in names):
                raise ValueError("Unreviewed mesh120 evidence")
            archive.extractall(directory)
        result = compare(directory / "evidence")
        if result["source_commit"] != SOURCE_COMMIT or result["run_id"] != RUN_ID:
            raise ValueError("Wrong tolerance experiment identity")
        saved = json.loads((directory / "evidence/tolerance-comparison.json").read_text())
        require_reproduction(saved, result)
        committed = json.loads(
            (root / "docs/benchmarks/stanford-k2-tolerance-result.json").read_text()
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
