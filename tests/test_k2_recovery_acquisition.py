"""Recovery scope and failure receipts, with no network or model execution."""

import importlib.util
import json
from pathlib import Path

import pytest


def module():
    spec = importlib.util.spec_from_file_location(
        "k2_acquisition", "scripts/acquire_stanford_k2_recovery.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def manifest():
    return json.loads(Path("data/stanford-manifest.json").read_text())


def test_only_k2_is_selected():
    m = module()
    selected = m.select_source(manifest())
    assert selected["filename"] == "NMC_k2_1C_25degC.xlsx"


@pytest.mark.parametrize("field", ["filename", "size", "sha256_hash", "download_url", "license"])
def test_changed_source_is_rejected(field):
    m = module()
    data = manifest()
    entry = m.select_source(data)
    if field == "license":
        data[field] = "unknown"
    elif field in ("sha256_hash", "download_url"):
        entry["content_details"][field] = "changed"
    else:
        entry[field] = "changed"
    with pytest.raises(ValueError):
        m.select_source(data)


def test_duplicate_source_is_rejected():
    m = module()
    data = manifest()
    data["files"].append(m.select_source(data))
    with pytest.raises(ValueError):
        m.select_source(data)


def test_transport_failure_stops_after_one_attempt_and_preserves_receipt(tmp_path, monkeypatch):
    m = module()
    (tmp_path / "data").mkdir()
    (tmp_path / "data/stanford-manifest.json").write_text(json.dumps(manifest()))
    calls = []

    def denied(request, timeout):
        calls.append(request.full_url)
        assert timeout == 60
        receipt = json.loads(
            (tmp_path / "results/stanford-k2-recovery-acquisition/receipt.json").read_text()
        )
        assert receipt["status"] == "started"
        assert receipt["attempted_downloads"] == 1
        raise OSError("synthetic transport failure")

    monkeypatch.setattr(m.urllib.request, "urlopen", denied)
    with pytest.raises(OSError):
        m.acquire(tmp_path)
    assert calls == [m.URL]
    receipt = json.loads(
        (tmp_path / "results/stanford-k2-recovery-acquisition/receipt.json").read_text()
    )
    assert receipt["status"] == "failed"


def test_total_deadline_records_timeout(tmp_path, monkeypatch):
    m = module()
    (tmp_path / "data").mkdir()
    (tmp_path / "data/stanford-manifest.json").write_text(json.dumps(manifest()))
    prior = m.signal.getsignal(m.signal.SIGALRM)

    def stalled(request, timeout):
        m.signal.getsignal(m.signal.SIGALRM)(m.signal.SIGALRM, None)

    monkeypatch.setattr(m.urllib.request, "urlopen", stalled)
    with pytest.raises(TimeoutError, match="90-second"):
        m.acquire(tmp_path)
    assert m.signal.getsignal(m.signal.SIGALRM) == prior
    assert m.signal.getitimer(m.signal.ITIMER_REAL) == (0, 0)
    receipt = json.loads(
        (tmp_path / "results/stanford-k2-recovery-acquisition/receipt.json").read_text()
    )
    assert receipt["status"] == "failed"
    assert receipt["error_type"] == "TimeoutError"
    assert receipt["attempted_downloads"] == 1
    assert receipt["k6_downloads"] == 0
    assert not (tmp_path / "data/stanford/raw" / m.FILENAME).exists()


def test_corrupt_existing_source_is_not_replaced_or_refetched(tmp_path, monkeypatch):
    m = module()
    (tmp_path / "data/stanford/raw").mkdir(parents=True)
    (tmp_path / "data/stanford-manifest.json").write_text(json.dumps(manifest()))
    source = tmp_path / "data/stanford/raw" / m.FILENAME
    source.write_bytes(b"synthetic corrupt bytes")

    def forbidden(*args, **kwargs):
        raise AssertionError("Network must not be called")

    monkeypatch.setattr(m.urllib.request, "urlopen", forbidden)
    with pytest.raises(ValueError, match="SHA256"):
        m.acquire(tmp_path)
    assert source.read_bytes() == b"synthetic corrupt bytes"
    receipt = json.loads(
        (tmp_path / "results/stanford-k2-recovery-acquisition/receipt.json").read_text()
    )
    assert receipt["attempted_downloads"] == 0
    assert receipt["status"] == "failed"
