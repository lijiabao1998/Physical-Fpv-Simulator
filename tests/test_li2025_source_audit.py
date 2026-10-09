"""The narrow source inspector must reject unpinned bytes before ZIP parsing."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_li2025_source.py"


@pytest.mark.parametrize("optimization", [[], ["-O"]])
def test_unpinned_source_rejected_before_output(tmp_path, optimization):
    archive = tmp_path / "wrong.zip"
    archive.write_bytes(b"This is not the published source archive")
    result = subprocess.run(
        [sys.executable, *optimization, str(SCRIPT), str(archive)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Source SHA256 mismatch" in result.stderr
    assert not (tmp_path / "results").exists()
