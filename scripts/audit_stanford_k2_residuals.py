"""Post-hoc residual localization using archived curves only; no solve or fitting."""

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import numpy as np


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def crossings(time, values):
    """Strict sign changes of a piecewise-linear trace, without noise smoothing."""
    output = []
    for i in range(len(time) - 1):
        if values[i] * values[i + 1] < 0:
            output.append(
                float(time[i] - values[i] * (time[i + 1] - time[i]) / (values[i + 1] - values[i]))
            )
    return output


def stats(time, error, start, stop):
    time, error = np.asarray(time), np.asarray(error)
    if (
        time.ndim != 1
        or error.shape != time.shape
        or len(time) < 2
        or not np.isfinite(time).all()
        or not np.isfinite(error).all()
        or np.any(np.diff(time) <= 0)
        or not time[0] <= start < stop <= time[-1]
    ):
        raise ValueError("Invalid residual interval or samples")
    x = np.unique(np.r_[start, time[(time > start) & (time < stop)], stop])
    e = np.interp(x, time, error)
    dt = np.diff(x)
    squared = float(np.sum(dt * (e[:-1] ** 2 + e[:-1] * e[1:] + e[1:] ** 2) / 3))
    signed = float(np.sum(dt * (e[:-1] + e[1:]) / 2))
    return {
        "interval_s": [float(start), float(stop)],
        "duration_s": float(stop - start),
        "signed_mean_v": signed / (stop - start),
        "rmse_v": (squared / (stop - start)) ** 0.5,
        "integrated_squared_error_v2_s": squared,
        "max_absolute_error_v": float(max(abs(e))),
        "max_absolute_error_time_s": float(x[np.argmax(abs(e))]),
        "first_error_v": float(e[0]),
        "last_error_v": float(e[-1]),
    }


def audit(root=Path(".")):
    verifier = load_module(root / "scripts/verify_stanford_k2_recovery.py", "k2_verifier")
    verifier.verify(root)
    path = root / "docs/benchmarks/stanford-k2-recovery-evidence.zip"
    with zipfile.ZipFile(path) as archive:
        prefix = "stanford-k2-recovery/"
        report = json.loads(archive.read(prefix + "report.json"))
        curves = {
            mesh: np.genfromtxt(
                io.BytesIO(archive.read(prefix + f"mesh{mesh}-residuals.csv")),
                delimiter=",",
                names=True,
            )
            for mesh in (80, 120)
        }
        with np.load(io.BytesIO(archive.read(prefix + "mesh120-arrays.npz"))) as arrays:
            fine_time = arrays["time_s"]
            fine_voltage = arrays["voltage_v"]
            fine_temperature = arrays["temperature_k"]
        snapshot = json.loads(archive.read(prefix + "mesh120-snapshot.json"))
    k1_path = root / "docs/benchmarks/stanford-k1-v3-verified-evidence.json"
    k1 = json.loads(k1_path.read_text())
    saved = k1["preserved_mesh120_curve"]
    compressed = (root / saved["path"]).read_bytes()
    csv = gzip.decompress(compressed)
    if (
        hashlib.sha256(compressed).hexdigest() != saved["gzip_sha256"]
        or hashlib.sha256(csv).hexdigest() != saved["csv_sha256"]
    ):
        raise ValueError("Preserved k1 fine curve changed")
    common_files = set(k1["source_sha256"]) & set(report["inputs"]["source_sha256"])
    if any(k1["source_sha256"][p] != report["inputs"]["source_sha256"][p] for p in common_files):
        raise ValueError("Shared k1/k2 scientific implementation differs")
    k1_curve = np.genfromtxt(io.BytesIO(csv), delimiter=",", names=True)
    common_stop = min(fine_time[-1], k1_curve["time_s"][-1])
    common_time = np.unique(
        np.r_[
            fine_time[fine_time <= common_stop],
            k1_curve["time_s"][k1_curve["time_s"] <= common_stop],
            common_stop,
        ]
    )
    difference = np.interp(common_time, fine_time, fine_voltage) - np.interp(
        common_time, k1_curve["time_s"], k1_curve["voltage_v"]
    )
    bounds = snapshot["model"]["physical_audit"]["concentration_bounds"]
    support_path = root / "docs/benchmarks/oregan-parameter-support.json"
    support = json.loads(support_path.read_text())
    state_limits = {
        electrode: {
            "saved_surface_stoichiometry_min": value["surface_min_mol_m3"] / value["limit_mol_m3"],
            "saved_surface_stoichiometry_max": value["surface_max_mol_m3"] / value["limit_mol_m3"],
            "support_crossing_time_s": None,
            "missing_time_series": True,
            "released_exchange_current_sampled_envelope": support["surface_stoichiometry_support"][
                electrode
            ]["sampled_stoichiometry_envelope"],
        }
        for electrode, value in bounds.items()
    }
    results = {}
    for mesh, curve in curves.items():
        case = report["cases"][str(mesh)]
        t, e = curve["time_s"], curve["voltage_error_v"]
        full = stats(t, e, t[0], t[-1])
        if not np.isclose(full["rmse_v"], case["voltage_rmse_v"], atol=1e-12, rtol=0):
            raise ValueError("Archived residuals do not reproduce the official RMSE")
        observed_start, observed_stop = case["assumptions"]["observed_interval_s"]
        boundaries = np.linspace(observed_start, observed_stop, 5)
        regions = []
        for quarter, (start, stop) in enumerate(
            zip(boundaries[:-1], boundaries[1:], strict=True), 1
        ):
            stop = min(stop, t[-1])
            if start >= stop:
                continue
            region = stats(t, e, start, stop)
            region["observed_duration_quarter"] = quarter
            region["squared_error_fraction"] = (
                region["integrated_squared_error_v2_s"] / full["integrated_squared_error_v2_s"]
            )
            regions.append(region)
        changes = crossings(t, e)
        sign_boundaries = [float(t[0]), *changes, float(t[-1])]
        signs = []
        for start, stop in zip(sign_boundaries[:-1], sign_boundaries[1:], strict=True):
            region = stats(t, e, start, stop)
            region["sign"] = "positive" if region["signed_mean_v"] > 0 else "negative"
            region["squared_error_fraction"] = (
                region["integrated_squared_error_v2_s"] / full["integrated_squared_error_v2_s"]
            )
            signs.append(region)
        results[str(mesh)] = {
            "full": full,
            "equal_observed_duration_quarters": regions,
            "strict_sign_change_times_s": changes,
            "sign_regions": signs,
            "unmodeled_observed_tail_s": observed_stop - float(t[-1]),
            "temperature_proxy": {
                "sign_change_times_s": crossings(t, curve["temperature_proxy_error_k"]),
                "first_error_k": float(curve["temperature_proxy_error_k"][0]),
                "last_error_k": float(curve["temperature_proxy_error_k"][-1]),
                "model_25c_crossings_s_in_common_window": crossings(
                    t, curve["predicted_average_k"] - 298.15
                ),
                "skin_25c_crossings_s_in_common_window": crossings(
                    t, curve["measured_skin_k"] - 298.15
                ),
            },
        }
        if not np.isclose(sum(r["squared_error_fraction"] for r in regions), 1, atol=1e-12):
            raise ValueError("Descriptive quarters do not partition the full score")
    return {
        "source_ci_run_id": verifier.RUN_ID,
        "source_commit_sha": verifier.SOURCE_COMMIT,
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "analysis_status": "post_hoc_descriptive_localization_not_causal_identification",
        "error_sign": "prediction minus measurement",
        "regime_rule": (
            "four equal full observed-duration quarters; final quarter stops at model event"
        ),
        "integration_rule": (
            "exact integral of piecewise-linear residual squared on all archived knots"
        ),
        "new_source_downloads": 0,
        "new_model_solves": 0,
        "parameter_fitting_performed": False,
        "acceptance_gate_changed": False,
        "cases": results,
        "k1_comparison": {
            "role": "descriptive frozen prediction comparison, not isolated causal experiment",
            "source_evidence_sha256": hashlib.sha256(k1_path.read_bytes()).hexdigest(),
            "curve_gzip_sha256": saved["gzip_sha256"],
            "matching_calculation_files": sorted(common_files),
            "mesh": 120,
            "shared_interval_s": [0.0, float(common_stop)],
            "max_absolute_prediction_difference_v": float(max(abs(difference))),
            "max_difference_time_s": float(common_time[np.argmax(abs(difference))]),
            "k1_case_voltage_rmse_v": k1["report"]["cases"]["120"]["voltage_rmse_v"],
            "measurement_windows_identical": False,
            "forcing_and_initial_temperatures_identical": False,
            "generalization_established": False,
        },
        "saved_state_extrema": state_limits,
        "parameter_support_source_sha256": hashlib.sha256(support_path.read_bytes()).hexdigest(),
        "fine_model_temperature_support_crossings": {
            "heat_capacity_lower_25c_s": crossings(fine_time, fine_temperature - 298.15),
            "positive_coating_conductivity_upper_35c_s": crossings(
                fine_time, fine_temperature - 308.15
            ),
            "times_are_piecewise_linear_crossings_of_saved_model_outputs": True,
        },
        "scientific_empirical_pass": False,
        "causal_identification_established": False,
    }, curves


def plot(curves, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    fine = curves[120]
    t = fine["time_s"]
    axes[0].plot(t, fine["measured_voltage_v"], color="#27364b", label="Measured voltage")
    axes[0].plot(t, fine["predicted_voltage_v"], color="#b14b2a", label="DFN grid120")
    axes[0].set_ylabel("Voltage (V)")
    axes[0].legend(loc="upper right")
    for mesh, color in [(80, "#9aa7b3"), (120, "#b14b2a")]:
        axes[1].plot(
            curves[mesh]["time_s"],
            curves[mesh]["voltage_error_v"] * 1000,
            color=color,
            label=f"Grid{mesh}",
        )
    axes[1].axhline(0, color="#27364b", lw=0.8)
    axes[1].set_ylabel("Voltage error (mV)")
    axes[1].legend(loc="lower left")
    axes[2].plot(t, fine["temperature_proxy_error_k"], color="#347c73")
    axes[2].axhline(0, color="#27364b", lw=0.8)
    axes[2].set_ylabel("Average − skin (K)")
    axes[2].set_xlabel("Commanded discharge time (s); common observed window only")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Stanford k2: converged, but voltage RMSE still fails\n"
        "55.003 mV > 50 mV · no fitting · thermal difference is a proxy",
        fontsize=15,
    )
    fig.savefig(path, dpi=170, metadata={"Creator": "Physical FPV zero-solve residual audit"})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results/stanford-k2-residual-audit"))
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    if args.render_only:
        path = Path("docs/benchmarks/stanford-k2-recovery-evidence.zip")
        if hashlib.sha256(path.read_bytes()).hexdigest() != (
            "2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d"
        ):
            raise ValueError("Archived plot source changed")
        with zipfile.ZipFile(path) as archive:
            curves = {
                mesh: np.genfromtxt(
                    io.BytesIO(archive.read(f"stanford-k2-recovery/mesh{mesh}-residuals.csv")),
                    delimiter=",",
                    names=True,
                )
                for mesh in (80, 120)
            }
        args.out.mkdir(parents=True, exist_ok=True)
        plot(curves, args.out / "residual-audit.png")
        return
    result, curves = audit()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if args.plot:
        plot(curves, args.out / "residual-audit.png")
    print(json.dumps(result["cases"]["120"], indent=2))


if __name__ == "__main__":
    main()
