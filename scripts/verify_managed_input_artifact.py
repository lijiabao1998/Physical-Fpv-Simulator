"""Bounded verification of a just-uploaded artifact at its exact GitHub endpoint."""

import hashlib
import json
import os
import re
import signal
import time
import urllib.error
import urllib.request
from pathlib import Path

VISIBILITY_DEADLINE_S = 60
POLL_INTERVAL_S = 5
MAX_RESPONSE_BYTES = 1_048_576


class SameEndpointOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_metadata(data, *, artifact_id, run_id, source_commit, expected_digest):
    expected = {
        "id": artifact_id,
        "name": "k2-low-rate-model-inputs-" + run_id,
        "expired": False,
        "digest": "sha256:" + expected_digest,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError("Uploaded artifact identity or digest mismatch")
    if data.get("expired") is not False or type(data.get("id")) is not int:
        raise ValueError("Uploaded artifact identity has invalid types")
    if type(data.get("size_in_bytes")) is not int or data["size_in_bytes"] <= 0:
        raise ValueError("Uploaded artifact is empty or has invalid size")
    workflow = data.get("workflow_run", {})
    if str(workflow.get("id")) != run_id or workflow.get("head_sha") != source_commit:
        raise ValueError("Uploaded artifact execution identity mismatch")
    return data


def wait_for_metadata(
    request, expected, *, opener=None, monotonic=time.monotonic, sleep=time.sleep
):
    """Retry only HTTP404 at this same endpoint, under one fixed deadline."""
    if opener is None:
        opener = urllib.request.build_opener(SameEndpointOnly()).open
    start = monotonic()
    deadline = start + VISIBILITY_DEADLINE_S
    attempts = 0
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Artifact metadata remained unavailable within 60 seconds")
        attempts += 1
        try:
            with opener(request, timeout=min(10, remaining)) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Artifact metadata response exceeded size bound")
            data = verify_metadata(json.loads(raw), **expected)
            if monotonic() >= deadline:
                raise TimeoutError("Artifact verification exceeded fixed deadline")
            return data, {
                "attempts": attempts,
                "elapsed_s": monotonic() - start,
                "deadline_s": VISIBILITY_DEADLINE_S,
                "retry_status": 404,
            }
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Artifact metadata remained unavailable within 60 seconds"
                ) from error
            sleep(min(POLL_INTERVAL_S, remaining))


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    head = os.environ["GITHUB_SHA"]
    artifact = os.environ["INPUT_ARTIFACT_ID"]
    expected_digest = os.environ["INPUT_ARTIFACT_DIGEST"]
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not run_id.isdigit()
        or not artifact.isdigit()
        or int(artifact) <= 0
        or not re.fullmatch(r"[0-9a-f]{40}", head)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
    ):
        raise ValueError("Invalid managed artifact identity")
    url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    # OS deadline also covers a stalled DNS/native request, before any solve.
    signal.setitimer(signal.ITIMER_REAL, VISIBILITY_DEADLINE_S)
    try:
        data, polling = wait_for_metadata(
            request,
            {
                "artifact_id": int(artifact),
                "run_id": run_id,
                "source_commit": head,
                "expected_digest": expected_digest,
            },
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    manifest = Path("results/k2-low-rate-model/inputs/manifest.json")
    receipt = {
        "artifact_id": int(artifact),
        "run_id": run_id,
        "source_commit": head,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "artifact_sha256": data["digest"],
        "verified_not_expired": True,
        "metadata_visibility": polling,
    }
    Path("results/k2-low-rate-model/upload-receipt.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({"artifact_id": int(artifact), "verified": True, **polling}))


if __name__ == "__main__":
    main()
