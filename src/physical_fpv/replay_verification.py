"""Offline verification of the two saved current-source replay artifact formats.

The caller-supplied receipt is the trust anchor, not a digital signature or a
fresh CI query. No model code, network client or archive extraction is used.
"""

from __future__ import annotations

import ast
import bisect
import csv
import hashlib
import io
import json
import math
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 512
MAX_ROWS = 200_000
RELATIVE_ROUNDOFF = 1e-11
ABSOLUTE_ROUNDOFF = 1e-12
WORKFLOW = ".github/workflows/current-source-replay-20261009.yml"


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(raw):
    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("JSON exceeds verifier size limit")
    return json.loads(raw, object_pairs_hook=_object, parse_constant=nonfinite)


def _same(actual, expected, label):
    if actual != expected:
        raise ValueError(f"Evidence mismatch: {label}")


def _close(actual, expected, label):
    if (
        isinstance(expected, bool)
        or not isinstance(expected, (int, float))
        or not math.isfinite(expected)
        or not math.isclose(actual, expected, rel_tol=RELATIVE_ROUNDOFF, abs_tol=ABSOLUTE_ROUNDOFF)
    ):
        raise ValueError(f"Recomputed metric mismatch: {label}")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _member_name(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != name.rstrip("/")
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Unsafe or ambiguous archive member name")


def _archive(path, digest, size):
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("Invalid archive SHA256 in receipt")
    if type(size) is not int or not 0 < size <= MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds verifier size limit")
    _same(path.stat().st_size, size, "ZIP byte count")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    _same(len(raw), size, "bounded ZIP byte count")
    _same(_sha(raw), digest, "ZIP SHA256")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.infolist()
        if len(info) > MAX_MEMBERS or sum(m.file_size for m in info) > MAX_EXPANDED_BYTES:
            raise ValueError("Expanded archive exceeds verifier limits")
        names = set()
        result = {}
        for member in info:
            _member_name(member.filename)
            if member.filename in names or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Duplicate or symlink archive member")
            names.add(member.filename)
            if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise ValueError("Unsupported archive compression method")
            if member.flag_bits & 1:
                raise ValueError("Encrypted evidence is unsupported")
            if not member.is_dir():
                result[member.filename] = archive.read(member)
        return result


def _curve(raw, columns):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Missing or duplicate CSV columns")
    if not set(columns) <= set(reader.fieldnames):
        raise ValueError("Missing required CSV observables")
    result = {key: [] for key in columns}
    for index, row in enumerate(reader):
        if index >= MAX_ROWS or None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed or oversized CSV")
        for key in columns:
            value = float(row[key])
            if not math.isfinite(value):
                raise ValueError("Nonfinite CSV observable")
            result[key].append(value)
    time = result[columns[0]]
    if len(time) < 2 or any(b <= a for a, b in zip(time, time[1:], strict=False)):
        raise ValueError("CSV times must be strictly increasing")
    return result


def _interp(time, values, query):
    if not time[0] <= query <= time[-1]:
        raise ValueError("Metric reconstruction would extrapolate")
    index = min(bisect.bisect_right(time, query) - 1, len(time) - 2)
    fraction = (query - time[index]) / (time[index + 1] - time[index])
    return values[index] + fraction * (values[index + 1] - values[index])


def _spatial(coarse, fine):
    ct, ft = coarse["time_s"], fine["time_s"]
    _same(ct[0], ft[0], "coarse/fine initial time")
    stop = min(ct[-1], ft[-1])
    common = sorted({t for t in ct + ft if t <= stop} | {stop})
    if fine["capacity_ah"][-1] <= 0:
        raise ValueError("Invalid fine cutoff capacity")
    result = {}
    for column, key in [
        ("voltage_v", "voltage_max_difference_v"),
        ("temperature_k", "temperature_max_difference_k"),
    ]:
        result[key] = max(
            abs(_interp(ct, coarse[column], t) - _interp(ft, fine[column], t)) for t in common
        )
    result["capacity_relative_difference"] = (
        abs(coarse["capacity_ah"][-1] - fine["capacity_ah"][-1]) / fine["capacity_ah"][-1]
    )
    return result


def _contract(manifest, inputs):
    expected = {"manifest.json"} | {"files/" + name for name in manifest["staged_files_sha256"]}
    _same(set(inputs), expected, "input member set")
    for path, digest in manifest["staged_files_sha256"].items():
        _member_name(path)
        _same(_sha(inputs["files/" + path]), digest, f"staged source {path}")
    for path, digest in manifest["source_sha256"].items():
        if path == "validation.py::write_timeseries":
            source = inputs["files/src/physical_fpv/validation.py"].decode()
            functions = [
                n
                for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == "write_timeseries"
            ]
            if len(functions) != 1:
                raise ValueError("Missing or ambiguous recorded analysis function")
            actual = _sha(ast.dump(functions[0], include_attributes=False).encode())
        else:
            _member_name(path)
            actual = _sha(inputs["files/" + path])
        _same(actual, digest, f"calculation contract {path}")


def _k1_voltage(outputs, prefix, fine, report):
    residual = _curve(
        outputs[prefix + "mesh120-residuals.csv"],
        ["time_s", "measured_voltage_v", "predicted_voltage_v", "voltage_error_v"],
    )
    observed = _curve(
        outputs["source-inspection/observed-discharge.csv"], ["commanded_step_time_s", "voltage_v"]
    )
    time, error = residual["time_s"], residual["voltage_error_v"]
    ot = observed["commanded_step_time_s"]
    _same([time[0], time[-1]], report["common_observed_interval_s"], "residual comparison window")
    _same([time[0], time[-1]], [ot[0], min(ot[-1], fine["time_s"][-1])], "observed overlap")
    expected_knots = sorted(
        {time[0], time[-1]} | {t for t in ot + fine["time_s"] if time[0] < t < time[-1]}
    )
    _same(time, expected_knots, "complete union of residual knots")
    for i, t in enumerate(time):
        measured = _interp(ot, observed["voltage_v"], t)
        predicted = _interp(fine["time_s"], fine["voltage_v"], t)
        _close(residual["measured_voltage_v"][i], measured, "measured residual voltage")
        _close(residual["predicted_voltage_v"][i], predicted, "predicted residual voltage")
        _close(error[i], predicted - measured, "signed residual")
    squared = math.fsum(
        (b - a) * (x * x + x * y + y * y) / 3
        for a, b, x, y in zip(time[:-1], time[1:], error[:-1], error[1:], strict=True)
    )
    rmse = math.sqrt(squared / (time[-1] - time[0]))
    maximum = max(map(abs, error))
    _close(rmse, report["voltage_rmse_v"], "voltage RMSE")
    _close(maximum, report["voltage_max_absolute_error_v"], "maximum voltage error")
    thresholds = report["empirical_thresholds"]
    _same(thresholds["voltage_rmse_v"], 0.05, "frozen RMSE gate")
    _same(thresholds["voltage_max_error_v"], 0.3, "frozen maximum-error gate")
    gates = report["electrical_gates"]
    _same(gates["voltage_rmse"], rmse <= 0.05, "voltage RMSE verdict")
    _same(gates["voltage_max"], maximum <= 0.3, "maximum-error verdict")
    if not gates or any(type(value) is not bool for value in gates.values()):
        raise ValueError("Electrical gates must be explicit booleans")
    _same(report["electrical_gates_passed"], all(gates.values()), "aggregate empirical verdict")
    return {
        "passed": report["electrical_gates_passed"],
        "voltage_rmse_v": rmse,
        "voltage_max_absolute_error_v": maximum,
        "recomputed_gates": ["voltage_rmse", "voltage_max"],
        "other_gates": "recorded, not independently reconstructed",
    }


def verify_replay(receipt_path: Path, input_zip: Path, output_zip: Path) -> dict:
    """Verify bounded saved artifacts against a caller-chosen receipt, without execution."""
    try:
        with receipt_path.open("rb") as stream:
            receipt_raw = stream.read(8 * 1024 * 1024 + 1)
        receipt = _json(receipt_raw)
        case = receipt["case"]
        if case not in {"k1", "thermal"}:
            raise ValueError("Unsupported replay case")
        _same(receipt["workflow_path"], WORKFLOW, "supported replay protocol")
        if (
            type(receipt["ci_run_id"]) is not int
            or receipt["ci_run_id"] <= 0
            or re.fullmatch(r"[0-9a-f]{40}", receipt["commit_sha"]) is None
        ):
            raise ValueError("Invalid run/commit identity")
        if type(receipt["run_attempt"]) is not int or receipt["run_attempt"] != 1:
            raise ValueError("Expected explicit integer attempt 1")
        inputs = _archive(input_zip, receipt["input_zip_sha256"], receipt["input_zip_bytes"])
        outputs = _archive(
            output_zip, receipt["artifact_zip_sha256"], receipt["artifact_zip_bytes"]
        )
        _same(set(outputs), set(receipt["artifact_files"]), "output member set")
        for path, digest in receipt["artifact_files"].items():
            _same(_sha(outputs[path]), digest, f"output member {path}")
        manifest = _json(inputs["manifest.json"])
        _same(
            _sha(inputs["manifest.json"]), receipt["input_manifest_sha256"], "input manifest SHA256"
        )
        _same(manifest, receipt["input_manifest"], "input manifest")
        _contract(manifest, inputs)
        _same(manifest["source_commit_sha"], receipt["commit_sha"], "execution source commit")
        _same(manifest["case"], case, "input case")
        _same(_sha(inputs["files/" + WORKFLOW]), receipt["workflow_sha256"], "launch workflow")
        _same(
            outputs[f"current-source-replay/{case}-inputs/manifest.json"],
            inputs["manifest.json"],
            "echoed manifest",
        )
        prefix = f"current-source-replay/{case}/"
        for filename, field in [
            ("launch", "launch_receipt"),
            ("external-exit", "external_exit"),
            ("status", "supervisor_status"),
        ]:
            _same(_json(outputs[prefix + filename + ".json"]), receipt[field], filename)
        for field in ["launch_receipt", "external_exit"]:
            identity = receipt[field]
            _same(identity["source_commit"], receipt["commit_sha"], "receipt commit")
            _same(identity["run_id"], str(receipt["ci_run_id"]), "receipt run")
            _same(identity["case"], case, "receipt case")
        if type(receipt["external_exit"]["exit_code"]) is not int:
            raise ValueError("External exit code must be an integer")
        _same(receipt["external_exit"]["exit_code"], 0, "completed external execution")
        _same(receipt["supervisor_status"]["status"], "completed", "completed supervisor")
        columns = ["time_s", "voltage_v", "capacity_ah", "temperature_k"]
        if case == "k1":
            report = _json(outputs[prefix + "report.json"])
            _same(report, receipt["report"], "k1 report")
            _same(report["inputs"]["source_commit_sha"], receipt["commit_sha"], "k1 report commit")
            _same(_json(outputs[prefix + "input.json"]), report["inputs"], "k1 executed inputs")
            _same(
                report["inputs"]["source_sha256"], manifest["source_sha256"], "k1 source contract"
            )
            _same(receipt["source_sha256"], manifest["source_sha256"], "receipt source contract")
            coarse = _curve(outputs[prefix + "mesh80-timeseries.csv"], columns)
            fine = _curve(outputs[prefix + "mesh120-timeseries.csv"], columns)
            recorded = report["spatial_numerical_check"]
            models = [report["cases"][str(n)]["model"] for n in (80, 120)]
            empirical = _k1_voltage(outputs, prefix, fine, report["cases"]["120"])
            _same(
                empirical["passed"],
                report["electrical_pilot_gates_passed"],
                "report empirical verdict",
            )
        else:
            _same(
                receipt["calculation_contract"],
                manifest["source_sha256"],
                "thermal source contract",
            )
            recorded = _json(outputs[prefix + "comparison.json"])
            _same(recorded, receipt["comparison"], "thermal comparison")
            coarse = _curve(inputs["files/docs/benchmarks/thermal-grid80-reference.csv"], columns)
            fine = _curve(outputs[prefix + "timeseries.csv"], columns)
            metadata = _json(outputs[prefix + "metadata.json"])
            _same(metadata, receipt["metadata"], "thermal metadata")
            _same(
                _json(outputs[prefix + "input.json"]), manifest["config"], "thermal executed config"
            )
            _same(metadata["config"], manifest["config"], "thermal reported config")
            models = [
                _json(inputs["files/docs/benchmarks/thermal-representative-grid80.json"]),
                metadata,
            ]
            empirical = {
                "passed": None,
                "reason": "No empirical comparison in this representative numerical replay",
            }
        for model, mesh in zip(models, (80, 120), strict=True):
            _same(model["config"]["mesh_points"], mesh, "recorded mesh identity")
            if (
                type(model["physical_audit"]["passed"]) is not bool
                or type(model["voltage_cutoff_reached"]) is not bool
            ):
                raise ValueError("Recorded audit and cutoff flags must be booleans")
        numerical = _spatial(coarse, fine)
        for key, value in numerical.items():
            _close(value, recorded[key], key)
        recorded_audits = all(
            m["physical_audit"]["passed"] is True and m["voltage_cutoff_reached"] is True
            for m in models
        )
        numerical["passed"] = (
            numerical["voltage_max_difference_v"] <= 0.005
            and numerical["temperature_max_difference_k"] <= 0.1
            and numerical["capacity_relative_difference"] <= 0.01
            and recorded_audits
        )
        if type(recorded["passed"]) is not bool:
            raise ValueError("Numerical verdict must be boolean")
        _same(numerical["passed"], recorded["passed"], "numerical verdict")
        return {
            "schema_version": 1,
            "receipt_sha256": _sha(receipt_raw),
            "input_zip_sha256": receipt["input_zip_sha256"],
            "output_zip_sha256": receipt["artifact_zip_sha256"],
            "integrity": "verified_against_receipt",
            "trust_anchor": "caller-supplied receipt; no signature or remote CI verification",
            "case": case,
            "source_commit_sha": receipt["commit_sha"],
            "source_ci_run_id": receipt["ci_run_id"],
            "input_files_verified": len(manifest["staged_files_sha256"]),
            "output_files_verified": len(outputs),
            "numerical": numerical,
            "empirical": empirical,
            "physical_audits": "recorded flags; internal states are not reconstructed",
            "metric_reproduction_tolerance": {
                "relative": RELATIVE_ROUNDOFF,
                "absolute": ABSOLUTE_ROUNDOFF,
            },
            "new_solver_runs": 0,
            "new_downloads": 0,
        }
    except (
        KeyError,
        TypeError,
        UnicodeError,
        zipfile.BadZipFile,
        csv.Error,
        RecursionError,
        AttributeError,
    ) as error:
        raise ValueError(f"Malformed or incomplete replay evidence: {error}") from error
