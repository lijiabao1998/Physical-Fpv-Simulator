"""Verify durable k2 receipts and recompute spatial comparison without any solve."""

import hashlib
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

ZIP_SHA256 = "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
RUN_ID = 37871885149
SOURCE_COMMIT = "50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84"


def historical_dependency_check(recorded, current):
    """Only the unused value-at evaluator may differ in this historical audit."""
    changed = sorted(k for k in set(recorded) | set(current) if recorded.get(k) != current.get(k))
    if set(changed) - {"src/physical_fpv/current_profile.py"}:
        raise ValueError("Historical array-verification dependencies changed")
    return changed


def historical_spatial_comparison(runner, out, recorded):
    """Recompute arrays under pinned analysis dependencies, never certify current forcing."""
    import numpy as np

    from physical_fpv.thermal_benchmark import thermal_numerics

    inputs = json.loads((out / "input.json").read_text())
    changed = historical_dependency_check(inputs["source_sha256"], runner.source_digests())
    coarse, fine = (runner.load_snapshot(out, mesh) for mesh in (80, 120))
    if (
        not coarse.parameter_fingerprint
        == fine.parameter_fingerprint
        == inputs["parameter_current_fingerprint"]
    ):
        raise ValueError("Historical meshes differ in recorded parameter/forcing identity")
    numerical = thermal_numerics(coarse, fine)
    stop = min(coarse.time_s[-1], fine.time_s[-1])
    times = np.unique(
        np.r_[coarse.time_s[coarse.time_s <= stop], fine.time_s[fine.time_s <= stop], stop]
    )
    dv = np.interp(times, coarse.time_s, coarse.voltage_v) - np.interp(
        times, fine.time_s, fine.voltage_v
    )
    dt = np.interp(times, coarse.time_s, coarse.temperature_k) - np.interp(
        times, fine.time_s, fine.temperature_k
    )
    numerical.update(
        {
            "shared_time_interval_s": [float(times[0]), float(stop)],
            "voltage_peak_difference_time_s": float(times[np.argmax(abs(dv))]),
            "temperature_peak_difference_time_s": float(times[np.argmax(abs(dt))]),
            "coarse_cutoff_time_s": float(coarse.time_s[-1]),
            "fine_cutoff_time_s": float(fine.time_s[-1]),
        }
    )
    if numerical != recorded["spatial_numerical_check"]:
        raise ValueError("Saved-array spatial comparison changed")
    return changed


def verify(root=Path(".")):
    archive = root / "docs/benchmarks/stanford-k2-recovery-evidence.zip"
    evidence = json.loads((root / "docs/benchmarks/stanford-k2-recovery-summary.json").read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIP_SHA256:
        raise ValueError("Recovery artifact bytes changed")
    if (
        evidence["ci_run_id"] != RUN_ID
        or evidence["source_commit_sha"] != SOURCE_COMMIT
        or evidence["evidence_zip_sha256"] != ZIP_SHA256
        or evidence["original_attempt_status"] != "unknown"
        or evidence["this_window_new_solves"] != [80, 120]
        or evidence["publication_runs_no_new_scientific_k2_solve"] is not True
        or evidence["evidence_artifact_id"] != 11590408911
        or evidence["inputs_artifact_id"] != 11590866548
        or evidence["inputs_zip_sha256"]
        != "6c992750395a4e8d4e320b856ec3a944d66b5107051413a6d69e835a10af2b1a"
        or evidence["ci_url"]
        != f"https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/{RUN_ID}"
    ):
        raise ValueError("Recovery provenance changed")
    spec = importlib.util.spec_from_file_location("frozen_k2", root / "scripts/run_stanford_k2.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with tempfile.TemporaryDirectory() as temporary:
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                relative = Path(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe recovery archive path")
                target = Path(temporary) / relative
                if not member.is_dir():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zipped.read(member))
        out = Path(temporary) / "stanford-k2-recovery"
        recorded = json.loads((out / "report.json").read_text())
        status = json.loads((out / "status.json").read_text())
        external = json.loads((out / "external-exit.json").read_text())
        if (
            recorded != evidence["report"]
            or status != evidence["supervisor_status"]
            or external != evidence["external_exit"]
            or status["status"] != "completed"
            or not 0 < status["elapsed_s"] < 1200
            or external["exit_code"] != 0
            or external["commit"] != SOURCE_COMMIT
            or external["run_id"] != str(RUN_ID)
        ):
            raise ValueError("Recovery terminal receipts changed")
        changed = historical_spatial_comparison(runner, out, recorded)
        recomputed = recorded  # Authenticated historical report, not a new-code result.
        if (
            recomputed["source_window_empirical_qualification_passed"] is not False
            or recomputed["numerically_qualified_conditional_prediction_passed"] is not False
            or recomputed["spatial_numerical_check"]["passed"] is not True
            or recomputed["cases"]["120"]["electrical_gates"]["voltage_rmse"] is not False
        ):
            raise ValueError("Known empirical failure or numerical qualification was erased")
    return {
        "verified": True,
        "verification_scope": "authenticated historical arrays and original source commit only",
        "current_calculation_compatible": not changed,
        "current_source_mismatches": changed,
        "source_commit_sha": SOURCE_COMMIT,
        "new_simulation_run": False,
        "source_ci_run_id": RUN_ID,
        "numerical_pass": True,
        "empirical_pass": False,
        "conditional_prediction_qualified": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
