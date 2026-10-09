"""Artifact visibility retries are bounded reads, never scientific retries."""

import importlib.util
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml


def module():
    spec = importlib.util.spec_from_file_location(
        "artifact_visibility", "scripts/verify_managed_input_artifact.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fixture():
    expected = {
        "artifact_id": 123,
        "run_id": "456",
        "source_commit": "a" * 40,
        "expected_digest": "b" * 64,
    }
    data = {
        "id": 123,
        "name": "k2-low-rate-model-inputs-456",
        "expired": False,
        "size_in_bytes": 1234,
        "digest": "sha256:" + "b" * 64,
        "workflow_run": {"id": 456, "head_sha": "a" * 40},
    }
    return expected, data


class Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_two_invisible_reads_then_exact_identity_succeeds():
    m = module()
    expected, data = fixture()
    clock = Clock()
    url = "https://api.github.com/repos/owner/repo/actions/artifacts/123"
    request = urllib.request.Request(url)
    calls = []

    def opener(actual, timeout):
        calls.append((actual.full_url, timeout))
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return io.BytesIO(json.dumps(data).encode())

    got, receipt = m.wait_for_metadata(
        request, expected, opener=opener, monotonic=clock.time, sleep=clock.sleep
    )
    assert got == data and receipt["attempts"] == 3 and receipt["elapsed_s"] == 10
    assert all(actual == url and timeout <= 10 for actual, timeout in calls)


def test_404_never_extends_fixed_deadline():
    m = module()
    expected, _ = fixture()
    clock = Clock()
    calls = []

    def opener(request, timeout):
        calls.append(timeout)
        raise urllib.error.HTTPError("same", 404, "Not Found", {}, None)

    with pytest.raises(TimeoutError, match="60 seconds"):
        m.wait_for_metadata(
            object(), expected, opener=opener, monotonic=clock.time, sleep=clock.sleep
        )
    assert clock.now == 60 and len(calls) == 12


@pytest.mark.parametrize("status", [401, 403, 429, 500, 504])
def test_other_http_failures_stop_without_retry(status):
    m = module()
    expected, _ = fixture()
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError("same", status, "Failure", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        m.wait_for_metadata(
            object(), expected, opener=opener, sleep=lambda seconds: pytest.fail("Must not retry")
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field,bad",
    [
        ("id", 124),
        ("expired", True),
        ("expired", 0),
        ("size_in_bytes", 0),
        ("size_in_bytes", True),
        ("name", "another-input"),
        ("digest", "sha256:" + "c" * 64),
        ("workflow_run", {"id": 457, "head_sha": "a" * 40}),
        ("workflow_run", {"id": 456, "head_sha": "d" * 40}),
    ],
)
def test_wrong_artifact_identity_fails_immediately(field, bad):
    m = module()
    expected, data = fixture()
    data[field] = bad
    with pytest.raises(ValueError):
        m.wait_for_metadata(
            object(),
            expected,
            opener=lambda *a, **k: io.BytesIO(json.dumps(data).encode()),
            sleep=lambda seconds: pytest.fail("Mismatch must not retry"),
        )


def test_late_response_and_oversized_body_are_not_accepted():
    m = module()
    expected, data = fixture()
    clock = Clock()

    def late(request, timeout):
        clock.now = 61
        return io.BytesIO(json.dumps(data).encode())

    with pytest.raises(TimeoutError):
        m.wait_for_metadata(
            object(), expected, opener=late, monotonic=clock.time, sleep=clock.sleep
        )
    with pytest.raises(ValueError, match="size bound"):
        m.wait_for_metadata(
            object(), expected, opener=lambda *a, **k: io.BytesIO(b" " * (m.MAX_RESPONSE_BYTES + 1))
        )
    assert m.SameEndpointOnly().redirect_request(None, None, 302, "", {}, "elsewhere") is None


def test_replacement_template_checks_old_attempt_before_new_preflight():
    path = Path("docs/experiments/stanford-k2-low-rate-model.workflow.yml")
    workflow = yaml.safe_load(path.read_text())
    steps = workflow["jobs"]["experiment"]["steps"]
    guard = steps[0]["run"]
    assert "37946424176" in guard
    assert "prior['run_attempt'] == 1" in guard
    assert "science[0]['conclusion'] == 'skipped'" in guard
    assert "k2-low-rate-model-20261009-v2.yml" in guard
    assert "data['total_count'] == 1" in guard
    compile(guard.split("python - <<'PY'\n")[1].rsplit("\nPY", 1)[0], "guard", "exec")
    verification = next(
        v for v in steps if v.get("run") == "python scripts/verify_managed_input_artifact.py"
    )
    assert "artifact-digest" in verification["env"]["INPUT_ARTIFACT_DIGEST"]
    upload = next(i for i, v in enumerate(steps) if v.get("id") == "input_upload")
    verify = steps.index(verification)
    solve = next(i for i, v in enumerate(steps) if " execute " in v.get("run", ""))
    assert upload < verify < solve
    active = Path(".github/workflows/k2-low-rate-model-20261009-v2.yml")
    if active.exists():
        assert active.read_bytes() == path.read_bytes()
