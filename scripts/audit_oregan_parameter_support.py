"""Compare the unchanged kinetic laws to released points and inspect saved model support."""

import argparse
import hashlib
import inspect
import json
from pathlib import Path

import pybamm

from physical_fpv.attribution import write_evidence_attribution
from physical_fpv.parameter_support import (
    assess_surface_support,
    compare_fixed_functions,
    exchange_points,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/oregan-parameter-support"))
    args = parser.parse_args()
    manifest_path = Path("data/oregan-kinetics-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    parameters = pybamm.ParameterValues("ORegan2022")
    code = Path(inspect.getsourcefile(parameters["Negative electrode OCP [V]"]))
    if (
        pybamm.__version__ != manifest["pybamm_version"]
        or hashlib.sha256(code.read_bytes()).hexdigest() != manifest["parameter_source_sha256"]
    ):
        raise ValueError("Installed parameter representation differs from the audited source")
    points = exchange_points(Path.cwd(), manifest)
    evidence_path = Path("docs/benchmarks/stanford-k1-v3-verified-evidence.json")
    evidence = json.loads(evidence_path.read_text())
    model = evidence["report"]["cases"]["120"]["model"]
    if (
        model["config"]["parameter_set"] != "ORegan2022"
        or model["pybamm_version"] != pybamm.__version__
    ):
        raise ValueError("The saved curve does not use the audited parameter representation")
    for electrode in ("negative", "positive"):
        if (
            model["physical_audit"]["concentration_bounds"][electrode]["limit_mol_m3"]
            != parameters[f"Maximum concentration in {electrode} electrode [mol.m-3]"]
        ):
            raise ValueError("Saved stoichiometry uses a different maximum concentration")
    conductivity = manifest["positive_electronic_conductivity_measurement_conditions"]
    modeled_temperature = evidence["report"]["cases"]["120"]["temperature_domains"]["ranges"][
        "volume_average_prediction_c"
    ]
    report = {
        "purpose": (
            "No-solve published-representation and sampled-support audit; not new acceptance gates"
        ),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "original_archive_sha256": manifest["archive"]["sha256"],
        "installed_parameter_source_sha256": manifest["parameter_source_sha256"],
        "saved_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "saved_execution_commit": evidence["commit_sha"],
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (
                "src/physical_fpv/parameter_support.py",
                "scripts/audit_oregan_parameter_support.py",
            )
        },
        "comparison_conditions": manifest["comparison_conditions"],
        "fixed_function_comparison": compare_fixed_functions(points, parameters),
        "surface_stoichiometry_support": assess_surface_support(model, points),
        "temperature_only_check": evidence["report"]["cases"]["120"]["temperature_domains"],
        "additional_positive_conductivity_support": {
            **conductivity,
            "model_temperature_range_c": modeled_temperature,
            "above_nominal_sampled_temperature": (
                modeled_temperature[1] > conductivity["nominal_temperature_range_c"][1]
            ),
            "below_nominal_sampled_temperature": (
                modeled_temperature[0] < conductivity["nominal_temperature_range_c"][0]
            ),
            "crossing_times_s": None,
            "qualification": (
                "Additional source applicability annotation, not a retrospective gate change. "
                "Rounded CSV kelvin labels and paper nominal Celsius settings are both retained."
            ),
        },
        "saved_empirical_voltage_rmse_v": evidence["report"]["cases"]["120"]["voltage_rmse_v"],
        "saved_empirical_electrical_gates_passed": evidence["report"]["cases"]["120"][
            "electrical_gates_passed"
        ],
        "new_model_solves": 0,
        "fitting_performed": False,
        "interpretation": (
            "The installed functions are reduced fitted representations, not interpolants of the "
            "released points. Differences do not by themselves prove a code error or explain the "
            "external-cell residual. Temperature coverage alone is not full parameter validation."
        ),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    write_evidence_attribution(args.out, ["oregan2022_parameters", "stanford2021"])
    print(
        json.dumps(
            {
                "points": len(points),
                "new_model_solves": 0,
                "support": report["surface_stoichiometry_support"],
            }
        )
    )


if __name__ == "__main__":
    main()
