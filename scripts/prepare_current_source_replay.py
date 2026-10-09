"""Authenticate and durably stage bounded replay inputs; never solve a model."""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pybamm

NEW_PROFILE_SHA256 = "3ac01b06b0b43e6fa464d861e5117a7d28f1b4f55f339ec781069a76e74905a6"
PROTOCOL = "docs/current-source-replay-protocol.md"
WORKFLOW = ".github/workflows/current-source-replay-20261009.yml"


def script(root, name):
    spec = importlib.util.spec_from_file_location(name, root / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_implementation_delta(old, current):
    if set(old) != set(current):
        raise ValueError("Calculation contract file set changed")
    key = "src/physical_fpv/current_profile.py"
    if current[key] != NEW_PROFILE_SHA256:
        raise ValueError("Unreviewed current evaluator implementation")
    if {p for p in old if old[p] != current[p]} != {key}:
        raise ValueError("Replay scope requires only the reviewed evaluator source change")


def prepare(case, out, root=Path(".")):
    from physical_fpv.core import ModelConfig, parameter_fingerprint

    commit = os.environ.get("PHYSICAL_FPV_RESEARCH_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Exact source commit is required")
    if out.exists():
        raise ValueError("Never overwrite existing staged replay inputs")
    if case == "k1":
        from physical_fpv.stanford_benchmark import prepare_pilot, verify_protocol
        from physical_fpv.stanford_data import validate_workbook_bytes
        from physical_fpv.stanford_reference import load_mesh80_reference

        runner = script(root, "run_stanford_pilot")
        current = runner.source_digests()
        prior = json.loads(
            (root / "docs/benchmarks/stanford-k1-v3-verified-evidence.json").read_text()
        )
        verify_implementation_delta(prior["source_sha256"], current)
        verify_protocol(root)
        manifest = json.loads((root / "data/stanford-manifest.json").read_text())
        _, profile, config, assumptions = prepare_pilot(root / "data/stanford/raw", manifest)
        parameters = pybamm.ParameterValues("ORegan2022")
        parameters.update(
            {
                "Current function [A]": config.current_a,
                "Ambient temperature [K]": config.ambient_temperature_k,
                "Initial temperature [K]": config.initial_temperature_k,
                "Total heat transfer coefficient [W.m-2.K-1]": (
                    config.heat_transfer_coefficient_w_m2_k
                ),
            }
        )
        identity = hashlib.sha256(
            (
                parameter_fingerprint(parameters)
                + ":piecewise-linear-current:"
                + profile.fingerprint_sha256
            ).encode()
        ).hexdigest()
        reference = load_mesh80_reference(root, config, profile, identity)
        reference_identity = reference.metadata()["recorded_reference"]
        raw = [
            root / "data/stanford/raw" / assumptions["source"]["filename"],
            root / "data/stanford/raw" / manifest["manufacturer_specification"]["filename"],
        ]
        validate_workbook_bytes(raw[1].read_bytes(), manifest["manufacturer_specification"])
        config = replace(config, mesh_points=120)
    elif case == "thermal":
        cache = script(root, "grid_evidence_cache")
        current = cache.calculation_contract(root)
        prior = json.loads((root / "docs/benchmarks/grid120-verified-evidence.json").read_text())
        verify_implementation_delta(prior["calculation_contract"], current)
        reference_identity = json.loads(
            (root / "docs/benchmarks/thermal-reference-manifest.json").read_text()
        )
        for filename, key in [
            ("thermal-grid80-reference.csv", "csv_sha256"),
            ("thermal-representative-grid80.json", "metadata_sha256"),
        ]:
            if (
                hashlib.sha256((root / "docs/benchmarks" / filename).read_bytes()).hexdigest()
                != reference_identity[key]
            ):
                raise ValueError("Thermal reference identity changed")
        config = ModelConfig(
            parameter_set="ORegan2022",
            thermal="lumped",
            current_a=5,
            mesh_points=120,
            initial_temperature_k=297.75,
            heat_transfer_coefficient_w_m2_k=15,
        )
        if (
            asdict(replace(config, mesh_points=80)) != reference_identity["config"]
            or pybamm.__version__ != reference_identity["pybamm_version"]
        ):
            raise ValueError("Thermal replay config/version differs from reference")
        metadata = json.loads(
            (root / "docs/benchmarks/thermal-representative-grid80.json").read_text()
        )
        if (
            metadata["physical_audit"]["passed"] is not True
            or metadata["voltage_cutoff_reached"] is not True
        ):
            raise ValueError("Historical thermal reference lacks physical/cutoff qualification")
        parameters = pybamm.ParameterValues("ORegan2022")
        parameters.update(
            {
                "Current function [A]": config.current_a,
                "Ambient temperature [K]": config.ambient_temperature_k,
                "Initial temperature [K]": config.initial_temperature_k,
                "Total heat transfer coefficient [W.m-2.K-1]": (
                    config.heat_transfer_coefficient_w_m2_k
                ),
            }
        )
        if parameter_fingerprint(parameters) != reference_identity["parameter_fingerprint"]:
            raise ValueError("Thermal physical parameter identity differs from reference")
        assumptions, raw = {}, []
    else:
        raise ValueError("Only the two reviewed cases are supported")
    files = {p for p in current if "::" not in p}
    files.update(str(p.relative_to(root)) for p in (root / "src/physical_fpv").glob("*.py"))
    if case == "k1":
        files.update(
            [
                "docs/benchmarks/stanford-k1-v3-verified-evidence.json",
                "scripts/inspect_stanford_pilot.py",
                "docs/stanford-acquisition-protocol.md",
            ]
        )
    else:
        files.update(
            ["scripts/grid_evidence_cache.py", "docs/benchmarks/grid120-verified-evidence.json"]
        )
    files.update(
        [
            PROTOCOL,
            WORKFLOW,
            "scripts/prepare_current_source_replay.py",
            "requirements-data-lock.txt",
        ]
    )
    files.update(str(p.relative_to(root)) for p in raw)
    paths = sorted(files)
    manifest = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}
    out.mkdir(parents=True)
    for relative in paths:
        destination = out / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    record = {
        "case": case,
        "source_commit_sha": commit,
        "source_sha256": current,
        "staged_files_sha256": manifest,
        "config": asdict(config),
        "reference": reference_identity,
        "assumptions": assumptions,
        "python_version": platform.python_version(),
        "pybamm_version": pybamm.__version__,
        "numpy_version": np.__version__,
        "new_scientific_solves_planned": 1,
        "wall_limit_s": 1200,
        "worker_address_space_limit_bytes": 4_000_000_000,
        "fitting_performed": False,
        "new_dataset": False,
        "mixed_source_reference_explicit": True,
    }
    (out / "manifest.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"case": case, "prepared": True, "source_commit_sha": commit}))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["k1", "thermal"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.case, args.out)
