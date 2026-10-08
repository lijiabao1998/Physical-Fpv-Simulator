"""Package a completed single-case diagnostic without recomputing or fitting."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/polarization-grid120"))
    parser.add_argument(
        "--out", type=Path, default=Path("docs/benchmarks/polarization-grid120-summary.json")
    )
    args = parser.parse_args()

    def read(name):
        return json.loads((args.input / name).read_text())

    status, inputs = read("status.json"), read("input.json")
    if status["status"] not in {"completed", "diagnostic_check_failure"}:
        raise ValueError("No completed diagnostic to summarize; preserve the budget/solver failure")
    raw = read("polarization.json")
    scalar_keys = [
        "terminal_voltage_v",
        "bulk_ocv_v",
        "bulk_temperature_k",
        "imposed_surface_boundary_temperature_k",
        "ambient_temperature_k",
        "negative_volume_mean_stoichiometry",
        "positive_volume_mean_stoichiometry",
        "negative_surface_x_average_stoichiometry",
        "positive_surface_x_average_stoichiometry",
        "negative_surface_min_stoichiometry",
        "negative_surface_max_stoichiometry",
        "positive_surface_min_stoichiometry",
        "positive_surface_max_stoichiometry",
    ] + [term["signed_column"] for term in raw["voltage_terms"]]
    files = {
        str(p.relative_to(args.input)): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for p in sorted(args.input.rglob("*"))
        if p.is_file()
    }
    summary = {
        "scope": "One unchanged model diagnostic; experimental ORegan 30/36 FAIL remains",
        "status": status,
        "input": inputs,
        "outcome": read("outcome.json"),
        "repeatability": read("repeatability.json"),
        "accounting": raw["accounting"],
        "voltage_reconstruction_max_error_v": raw["voltage_reconstruction_max_error_v"],
        "mean_stoichiometry_charge_max_error": raw["mean_stoichiometry_charge_max_error"],
        "state_selection": raw["state_selection"],
        "states": [
            {
                "label": s["label"],
                "time_s": s["time_s"],
                "index": s["index"],
                "scalars": {k: s["scalars"][k] for k in scalar_keys},
            }
            for s in raw["states"]
        ],
        "voltage_terms": raw["voltage_terms"],
        "series_summaries": {k: raw["series"][k] for k in scalar_keys},
        "physical_audit": raw["result_metadata"]["physical_audit"],
        "limitations": raw["limitations"],
        "source_attribution": read("source-attribution.json"),
        "original_full_output_files": files,
        "packaging_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reproduce_full_outputs": (
            "python scripts/diagnose_polarization.py --timeout 1200 "
            "--out results/new-polarization-run"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.out), "outcome": summary["outcome"]}))


if __name__ == "__main__":
    main()
