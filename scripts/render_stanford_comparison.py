"""Render frozen Stanford k1 evidence without fitting or running a battery model.

Example (from the repository root):
    python scripts/render_stanford_comparison.py --evidence-dir results/stanford-k1-pilot \
        --out docs/benchmarks/stanford-k1-comparison.svg --preview-png /tmp/comparison.png

Normal mode requires a completed two-grid report. Explicit --partial mode accepts
the actual completed mesh80 report/CSVs and labels spatial verification unavailable.
All scores and gate outcomes are read from frozen reports. CSV/source consistency
checks verify the plotted data, not a new model or a recomputed qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from render_stanford_measurements import DISPLAY_BINS, display_indices

from physical_fpv.stanford_data import inspect_pilot

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6"
TIMESERIES_HEADER = "time_s,voltage_v,capacity_ah,temperature_k,lithium_inventory_mol"
RESIDUAL_HEADER = (
    "time_s,measured_voltage_v,predicted_voltage_v,voltage_error_v,"
    "measured_skin_k,predicted_average_k,temperature_proxy_error_k"
)
COLORS = {"source": "#175b91", "80": "#d2831c", "120": "#9a367b"}
STYLES = {"source": "-", "80": (0, (5, 2.5)), "120": "-"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON value in {path.name}: {value}")

    value = json.loads(path.read_text(), parse_constant=reject_constant)
    require(isinstance(value, dict), f"{path.name} must contain a JSON object")
    return value


def load_csv(path: Path, header: str) -> np.ndarray:
    with path.open() as stream:
        require(stream.readline().strip() == header, f"Unexpected units/schema: {path.name}")
        values = np.loadtxt(stream, delimiter=",", ndmin=2)
    require(
        values.shape[1] == len(header.split(","))
        and len(values) >= 2
        and np.isfinite(values).all()
        and np.all(np.diff(values[:, 0]) > 0),
        f"{path.name} needs finite values and strictly increasing times",
    )
    return values


def close(actual, expected, description: str, atol: float = 1e-9) -> None:
    require(
        np.shape(actual) == np.shape(expected) and np.allclose(actual, expected, rtol=0, atol=atol),
        f"Evidence mismatch: {description}",
    )


def load_evidence(evidence: Path, manifest_path: Path, raw: Path, partial: bool = False) -> dict:
    """Validate real curves; never construct a substitute final report or grid-120 curve."""
    meshes = ("80",) if partial else ("80", "120")
    report_name = "mesh80-report.json" if partial else "report.json"
    required = [report_name, "input.json"] + [
        f"mesh{mesh}-{kind}.csv" for mesh in meshes for kind in ("timeseries", "residuals")
    ]
    missing = [name for name in required if not (evidence / name).is_file()]
    require(
        not missing,
        (
            "Actual mesh-80 evidence is required; missing: "
            if partial
            else "Completed two-grid evidence is required; missing: "
        )
        + ", ".join(missing)
        + ". No model is run and no curves are invented.",
    )
    recorded, inputs = (load_json(evidence / name) for name in required[:2])
    if partial:
        require(
            not (evidence / "report.json").exists(),
            "A final report exists; use normal mode rather than omit the grid-120 evidence",
        )
        report, cases, numerical = None, {"80": recorded}, None
    else:
        report, cases, numerical = recorded, recorded["cases"], recorded["spatial_numerical_check"]
        require(report["inputs"] == inputs, "input.json differs from the frozen report inputs")
        require(set(cases) == {"80", "120"}, "Both grid-80 and grid-120 reports required")
    execution = {}
    for name in ("status.json", "stage.json"):
        if (evidence / name).exists():
            execution[name] = load_json(evidence / name)
            if not partial:
                require(
                    execution[name]["status"] == "completed",
                    f"{name} does not record completion",
                )
    if not partial:
        for key in (
            "independent_thermal_validation_established",
            "whole_cohort_validation_established",
            "fitting_performed",
        ):
            require(report[key] is False, f"This renderer cannot represent changed scope: {key}")
        require(
            report["existing_oregan_empirical_failures"] == "30/36; unchanged",
            "Expected the retained ORegan 30/36 empirical failures",
        )
        require(
            isinstance(numerical["passed"], bool),
            "Spatial numerical stage has no recorded outcome",
        )
    require(inputs["fitting_performed"] is False, "This renderer requires the unfitted pilot")
    code_hashes = inputs["source_sha256"]
    require(
        isinstance(code_hashes, dict)
        and bool(code_hashes)
        and all(
            isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")
            for value in code_hashes.values()
        ),
        "Frozen code/source SHA256 identities are missing or invalid",
    )
    require(
        sha256(manifest_path) == code_hashes["data/stanford-manifest.json"],
        "Manifest differs from the source manifest recorded by the solver",
    )
    manifest = load_json(manifest_path)
    source_report, observed = inspect_pilot(raw, manifest)
    require(
        source_report["source"]["sha256"] == SOURCE_SHA256
        and source_report["canonical_six_step_sequence"]
        and observed is not None,
        "Expected the checksum-qualified Stanford k1 source and six-phase protocol",
    )
    require(
        observed.ndim == 2
        and observed.shape[1] == 4
        and len(observed) >= 2
        and np.isfinite(observed).all()
        and np.all(np.diff(observed[:, 0]) > 0),
        "Source discharge values or clocks are not qualified",
    )
    assumptions = inputs["assumptions"]
    close(observed[0, 0], 1.0006, "first source timestamp must remain at 1.0006 s")
    close(observed[[0, -1], 0], assumptions["observed_interval_s"], "source interval")
    close([0, observed[0, 0]], assumptions["missing_initial_interval_s"], "initial gap")
    require(
        assumptions["source"]["sha256"] == SOURCE_SHA256
        and assumptions["initial_interval_is_measured"] is False
        and assumptions["independent_thermal_validation_established"] is False,
        "Source identity or thermal/initial-interval assumptions changed",
    )
    curves, residuals = {}, {}
    for mesh in meshes:
        case = cases[mesh]
        model, config = case["model"], case["model"]["config"]
        require(
            config == dict(inputs["config"], mesh_points=int(mesh))
            and config["model"] == "DFN"
            and config["parameter_set"] == "ORegan2022"
            and config["thermal"] == "lumped"
            and config["heat_transfer_coefficient_w_m2_k"] == 15
            and config["tolerance"] > 0
            and config["sample_period_s"] > 0,
            f"Grid {mesh} differs from the declared DFN / ORegan2022 / h15 pilot",
        )
        require(
            case["source_sha256"] == SOURCE_SHA256
            and case["fitting_performed"] is False
            and case["independent_thermal_validation_established"] is False
            and model["pybamm_version"] == inputs["pybamm_version"]
            and model["current_protocol"]["fingerprint_sha256"]
            == assumptions["current_profile_sha256"],
            f"Grid {mesh} source, forcing, software or scope differs from frozen inputs",
        )
        gates = case["electrical_gates"]
        require(
            bool(gates)
            and all(isinstance(value, bool) for value in gates.values())
            and case["electrical_gates_passed"] is all(gates.values()),
            f"Grid {mesh} electrical gate report is incomplete/inconsistent",
        )
        require(
            set(case["thermal_proxy_gates"]) == {"rmse", "maximum_error"}
            and all(isinstance(value, bool) for value in case["thermal_proxy_gates"].values()),
            f"Grid {mesh} thermal-proxy gate report is incomplete",
        )
        for key in (
            "voltage_rmse_v",
            "voltage_max_absolute_error_v",
            "temperature_proxy_rmse_k",
            "temperature_proxy_max_absolute_error_k",
            "capacity_relative_error",
            "energy_relative_error",
            "observed_time_coverage",
        ):
            require(np.isfinite(case[key]) and case[key] >= 0, f"Invalid frozen score: {key}")
        curve = load_csv(evidence / f"mesh{mesh}-timeseries.csv", TIMESERIES_HEADER)
        residual = load_csv(evidence / f"mesh{mesh}-residuals.csv", RESIDUAL_HEADER)
        close(curve[0, 0], 0, f"grid {mesh} starts at the commanded origin")
        for endpoint in (case["predicted_endpoint_time_s"], model["endpoint_time_s"]):
            close(curve[-1, 0], endpoint, f"grid {mesh} endpoint")
        close(observed[-1, 0], case["measured_endpoint_time_s"], "measured endpoint")
        start, stop = observed[0, 0], min(observed[-1, 0], curve[-1, 0])
        require(stop > start, f"Grid {mesh} does not cover the observed interval")
        close([start, stop], case["common_observed_interval_s"], f"grid {mesh} overlap")
        common = np.unique(
            np.r_[
                start,
                observed[(observed[:, 0] > start) & (observed[:, 0] < stop), 0],
                curve[(curve[:, 0] > start) & (curve[:, 0] < stop), 0],
                stop,
            ]
        )
        close(residual[:, 0], common, f"grid {mesh} residual time support")
        measured_v = np.interp(common, observed[:, 0], observed[:, 2])
        measured_t = np.interp(common, observed[:, 0], observed[:, 3])
        predicted_v = np.interp(common, curve[:, 0], curve[:, 1])
        predicted_t = np.interp(common, curve[:, 0], curve[:, 3])
        expected = np.column_stack(
            (
                common,
                measured_v,
                predicted_v,
                predicted_v - measured_v,
                measured_t,
                predicted_t,
                predicted_t - measured_t,
            )
        )
        close(residual, expected, f"grid {mesh} residual/source/model values")
        curves[mesh], residuals[mesh] = curve, residual
    if not partial:
        require(
            cases["80"]["model"]["parameter_fingerprint"]
            == cases["120"]["model"]["parameter_fingerprint"],
            "Grid parameter fingerprints differ",
        )
        require(
            report["electrical_pilot_gates_passed"] is cases["120"]["electrical_gates_passed"],
            "Pilot electrical outcome differs from the grid-120 report",
        )
        for mesh, label in (("80", "coarse"), ("120", "fine")):
            close(curves[mesh][-1, 0], numerical[f"{label}_cutoff_time_s"], f"{label} endpoint")
            require(numerical[f"{label}_mesh"] == int(mesh), "Numerical grid identity changed")
            close(
                numerical[f"{label}_tolerance"],
                inputs["config"]["tolerance"],
                f"{label} solver tolerance",
                atol=0,
            )
    return {
        "report": report,
        "inputs": inputs,
        "cases": cases,
        "numerical": numerical,
        "partial": partial,
        "report_name": report_name,
        "execution_status": execution,
        "manifest": manifest,
        "source_report": source_report,
        "observed": observed,
        "curves": curves,
        "residuals": residuals,
        "evidence_sha256": {name: sha256(evidence / name) for name in required},
    }


def verdict(value: bool) -> str:
    return "PASS" if value else "FAIL"


def render(bundle: dict, output: Path, preview: Path | None) -> dict:
    manifest, cases, partial = bundle["manifest"], bundle["cases"], bundle["partial"]
    observed, curves, residuals = bundle["observed"], bundle["curves"], bundle["residuals"]
    primary_mesh = "80" if partial else "120"
    inputs, fine = bundle["inputs"], cases[primary_mesh]
    numerical, config = bundle["numerical"], inputs["config"]
    report_name = bundle["report_name"]
    spatial_verdict = "UNAVAILABLE" if partial else verdict(numerical["passed"])
    thresholds = fine["empirical_thresholds"]
    first, source_end = observed[[0, -1], 0]
    end = max(source_end, *(curve[-1, 0] for curve in curves.values()))
    software = {
        "python": platform.python_version(),
        "matplotlib": matplotlib.__version__,
        "numpy": np.__version__,
        "openpyxl": openpyxl.__version__,
    }
    provenance = {
        "evidence_sha256": bundle["evidence_sha256"],
        "source_sha256": SOURCE_SHA256,
        "source_commit_sha": inputs.get("source_commit_sha"),
        "calculation_file_sha256": inputs["source_sha256"],
        "parameter_fingerprint": fine["model"]["parameter_fingerprint"],
        "current_profile_sha256": inputs["assumptions"]["current_profile_sha256"],
        "renderer_sha256": sha256(Path(__file__)),
        "display_helper_sha256": sha256(
            Path(__file__).with_name("render_stanford_measurements.py")
        ),
        "rendering_software": software,
        "recorded_solver_software": {
            key: inputs[key] for key in ("python_version", "pybamm_version", "numpy_version")
        },
        "recorded_numerical_config": config,
        f"frozen_grid_{primary_mesh}_scores": {
            key: fine[key]
            for key in (
                "voltage_rmse_v",
                "voltage_max_absolute_error_v",
                "capacity_relative_error",
                "energy_relative_error",
                "observed_time_coverage",
                "temperature_proxy_rmse_k",
                "temperature_proxy_max_absolute_error_k",
            )
        },
        "frozen_spatial_check": numerical,
        "partial_evidence": partial,
        "frozen_score_source": report_name,
        "execution_status": bundle["execution_status"],
    }
    title = (
        "Stanford k1: preliminary grid-80 evidence"
        if partial
        else "Stanford k1: measurement vs frozen prediction"
    )
    grid_description = "grid-80" if partial else "grid-80/grid-120"
    partial_notice = (
        "Preliminary grid-80 view: no completed grid-120 evidence or final two-grid report. "
        "Spatial verification is unavailable; a completed mesh-80 curve does not establish it. "
        if partial
        else "Completed two-grid evidence. "
    )
    description = (
        partial_notice
        + f"Three panels show measured voltage and skin temperature, DFN {grid_description} "
        "predicted voltage and volume-average temperature, and signed predicted-minus-measured "
        "voltage residuals on each model's actual observed overlap. Every curve ends at its own "
        f"recorded endpoint. No source sample is added in 0 <= t < {first:.4f} seconds. "
        "Initial and post-source current continuations are declared input hypotheses, "
        f"not measurements. The grid-{primary_mesh} electrical empirical gate is "
        f"{verdict(fine['electrical_gates_passed'])}; the 80-to-120 spatial numerical "
        f"check is {spatial_verdict}. These are separate conclusions. "
        f"Thermal-proxy gates are {verdict(all(fine['thermal_proxy_gates'].values()))}. "
        "Thermal qualification is not established: measured skin and predicted volume average "
        "are different observables, and h=15 W/m2/K is an unidentified fixture hypothesis. "
        "ORegan empirical failures remain 30/36; no whole-cohort or full-model validation. "
        f"Scores come unchanged from {report_name}. RMSE thresholds are aggregate criteria, "
        "not pointwise confidence/tolerance bands; no such band is drawn. "
        f"Display compression retains actual first/min/max/last samples in {DISPLAY_BINS} "
        "equal-time bins independently per series; no smoothing or new samples. "
        "The initial-time inset is unreduced. Full numeric CSVs/workbook remain unchanged. "
        f"Data: {', '.join(manifest['authors'])}; DOI {manifest['dataset_doi']}; "
        f"{manifest['license']} ({manifest['license_url']}). "
        "Changes to source presentation: time in commanded discharge-step seconds, "
        "temperature displayed in degrees Celsius, display compression and model overlay. "
        f"Full provenance and unrounded frozen values: {json.dumps(provenance, sort_keys=True)}"
    )
    vertices = 0
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#59636b",
            "axes.linewidth": 0.7,
            "grid.color": "#d8dde2",
            "grid.linewidth": 0.5,
            "svg.fonttype": "none",
            "svg.hashsalt": "stanford-k1-frozen-comparison",
            "path.simplify": False,
        }
    ):
        fig, axes = plt.subplots(3, 1, figsize=(12.6, 10.8), sharex=True)
        fig.subplots_adjust(left=0.085, right=0.705, top=0.795, bottom=0.315, hspace=0.24)
        fig.suptitle(title, x=0.085, y=0.977, ha="left", fontsize=20, weight="bold")
        fig.text(
            0.085,
            0.935,
            "LG M50  •  1C / nominal 25 °C  •  DFN + ORegan2022 / lumped thermal  •  no new fit",
            fontsize=11.5,
        )
        summaries = [
            (
                0.085,
                f"Electrical empirical gate [{primary_mesh}]",
                verdict(fine["electrical_gates_passed"]),
            ),
            (0.395, "Spatial numerical check [80 → 120]", spatial_verdict),
            (0.725, "Thermal qualification", "NOT ESTABLISHED"),
        ]
        for x, label, result in summaries:
            fig.text(x, 0.887, label, fontsize=10, color="#43515d")
            fig.text(x, 0.861, result, fontsize=13, weight="bold", color="#273a4a")

        for ax in axes:
            ax.axvspan(0, first, facecolor="#fff0d1", hatch="///", edgecolor="#d5b05b", lw=0)
            if end > source_end:
                ax.axvspan(source_end, end, color="#f0f2f4", zorder=0)
            ax.grid(axis="y")
            ax.tick_params(labelsize=9)
            ax.set_xlim(0, end * 1.012)

        def plot_line(ax, time, values, key, label=None):
            nonlocal vertices
            keep = display_indices(time, values)
            vertices += len(keep)
            line = ax.plot(
                time[keep],
                values[keep],
                color=COLORS[key],
                linestyle=STYLES[key],
                linewidth=1.2 if key == "source" else 1.45,
                label=label,
            )[0]
            ax.plot(time[-1], values[-1], "o", color=COLORS[key], markersize=3.4)
            return line

        legend = []
        for index, (source_col, model_col, offset, ylabel) in enumerate(
            ((2, 1, 0, "Voltage [V]"), (3, 3, 273.15, "Temperature [°C]"))
        ):
            ax = axes[index]
            source_line = plot_line(
                ax, observed[:, 0], observed[:, source_col] - offset, "source", "Measured source"
            )
            handles = [source_line]
            for mesh in curves:
                curve = curves[mesh]
                handles.append(
                    plot_line(
                        ax,
                        curve[:, 0],
                        curve[:, model_col] - offset,
                        mesh,
                        f"Predicted grid {mesh}",
                    )
                )
            if index == 0:
                legend = handles
            ax.set_ylabel(ylabel)
        axes[1].text(
            0.02,
            0.85,
            "Measured skin vs predicted volume average",
            transform=axes[1].transAxes,
            fontsize=8.7,
            color="#43515d",
        )
        for mesh in curves:
            residual = residuals[mesh]
            plot_line(axes[2], residual[:, 0], residual[:, 3] * 1000, mesh)
        axes[2].axhline(0, color="#59636b", lw=0.75, zorder=0)
        axes[2].set_ylabel("Voltage residual [mV]\npredicted − measured")
        axes[2].set_xlabel("Time from commanded discharge start [s]", labelpad=7)
        fig.legend(
            handles=legend,
            loc="upper left",
            bbox_to_anchor=(0.075, 0.835),
            frameon=False,
            ncols=3,
            fontsize=9.5,
            handlelength=3,
            columnspacing=2,
        )
        # The true one-second source gap is too narrow on the main 3400-second axes.
        inset = axes[0].inset_axes([0.075, 0.105, 0.30, 0.41])
        inset.axvspan(0, first, facecolor="#fff0d1", hatch="///", edgecolor="#d5b05b", lw=0)
        take = observed[:, 0] <= 3.1
        inset.plot(observed[take, 0], observed[take, 2], "o", color=COLORS["source"], ms=3)
        for mesh in curves:
            curve = curves[mesh]
            # Include the next real model sample; let the inset clip its linear segment.
            count = min(len(curve), np.searchsorted(curve[:, 0], 3.1, side="right") + 1)
            inset.plot(
                curve[:count, 0],
                curve[:count, 1],
                color=COLORS[mesh],
                linestyle=STYLES[mesh],
                lw=1,
            )
        inset.set_xlim(0, 3.1)
        inset.set_xticks([0, first, 3], ["0", "1.0006", "3"])
        inset.tick_params(labelsize=7, pad=2)
        inset.set_title("Onset [s]: hatched = unobserved", fontsize=8, pad=4)

        def side_note(ax, title_text, lines):
            ax.text(1.055, 1.03, title_text, transform=ax.transAxes, fontsize=10, weight="bold")
            ax.text(
                1.055,
                0.87,
                "\n".join(lines),
                transform=ax.transAxes,
                va="top",
                fontsize=9,
                linespacing=1.50,
                color="#344652",
            )

        failed = [
            key.replace("_", " ") for key, value in fine["electrical_gates"].items() if not value
        ]
        side_note(
            axes[0],
            f"Frozen electrical scores [{primary_mesh}]",
            [
                f"RMSE: {fine['voltage_rmse_v'] * 1000:.4f} mV",
                f"Max |error|: {fine['voltage_max_absolute_error_v'] * 1000:.4f} mV",
                f"Capacity error: {fine['capacity_relative_error']:.4%}",
                f"Energy error: {fine['energy_relative_error']:.4%}",
                f"Observed-time coverage: {fine['observed_time_coverage']:.4%}",
                "Failed gates: "
                + (
                    ", ".join(failed)
                    if 0 < len(failed) <= 1
                    else str(len(failed))
                    if failed
                    else "none"
                ),
            ],
        )
        side_note(
            axes[1],
            f"Thermal proxy: {verdict(all(fine['thermal_proxy_gates'].values()))} [{primary_mesh}]",
            [
                f"RMSE: {fine['temperature_proxy_rmse_k']:.4f} K "
                f"(gate ≤ {thresholds['temperature_rmse_k']:g} K)",
                f"Max |error|: {fine['temperature_proxy_max_absolute_error_k']:.4f} K "
                f"(gate ≤ {thresholds['temperature_max_error_k']:g} K)",
                "h = 15 W/m²/K: prior hypothesis",
                "Fixture h and ambient trace unavailable",
                "No independent thermal validation",
            ],
        )
        if partial:
            spatial_lines = [
                "UNAVAILABLE: no grid-120 evidence",
                "No completed two-grid report",
                "Grid-80 physical audits: " + verdict(fine["model"]["physical_audit"]["passed"]),
                "Spatial agreement remains unverified",
                "No pointwise RMSE band is drawn",
            ]
        else:
            spatial_lines = [
                f"Max |ΔV|: {numerical['voltage_max_difference_v'] * 1000:.4f} mV",
                f"Max |ΔT|: {numerical['temperature_max_difference_k']:.6f} K",
                f"Cutoff-capacity Δ: {numerical['capacity_relative_difference']:.4%}",
                "Shared interval; spatial check only",
                "No pointwise RMSE band is drawn",
            ]
        side_note(axes[2], "Spatial check [80 → 120]", spatial_lines)
        endpoint_text = "  /  ".join(
            f"grid {mesh}: {curves[mesh][-1, 0]:.6f} s"
            + (" (V cutoff)" if cases[mesh]["model"]["voltage_cutoff_reached"] else " (stop)")
            for mesh in curves
        )
        commit = inputs.get("source_commit_sha") or "not recorded; file hashes embedded in SVG"
        footer = [
            f"Endpoints: measured {source_end:.6f} s  /  {endpoint_text}. "
            "Dots mark actual endpoints.",
            f"No source sample for 0 ≤ t < {first:.4f} s. Gray tail, if present: "
            "model-only constant-current continuation; no observed extrapolation.",
            f"Electrical thresholds: RMSE ≤ {thresholds['voltage_rmse_v'] * 1000:g} mV; "
            f"max |error| ≤ {thresholds['voltage_max_error_v'] * 1000:g} mV; "
            f"capacity/energy ≤ {thresholds['capacity_relative_error']:.0%}/"
            f"{thresholds['energy_relative_error']:.0%}; "
            f"coverage ≥ {thresholds['min_coverage']:.0%}; "
            "cutoff + audit required.",
            f"Display: first/min/max/last samples per {DISPLAY_BINS} time bins; inset unreduced. "
            "No smoothing. Full numeric CSVs and workbook unchanged.",
            f"Numerics: recorded rtol = atol = {config['tolerance']:g}; "
            f"requested samples every {config['sample_period_s']:g} s; event endpoint retained; "
            f"PyBaMM {inputs['pybamm_version']}; Matplotlib {matplotlib.__version__}.",
            f"Calculation commit: {commit}. {report_name} SHA256: "
            f"{bundle['evidence_sha256'][report_name][:16]}… (full identities embedded).",
            f"Source SHA256: {SOURCE_SHA256}",
            f"Data: {' & '.join(manifest['authors'])}  |  "
            f"DOI: {manifest['dataset_doi']}  |  CC BY 4.0. Source presentation adapted.",
            "ORegan empirical failures: 30/36, unchanged. "
            "One preselected external-source pilot; no whole-cohort or full-model validation.",
        ]
        for index, line in enumerate(footer):
            fig.text(
                0.085,
                0.252 - index * 0.026,
                line,
                fontsize=8.6 if index != 6 else 8.1,
                color="#43515d" if index < 8 else "#273a4a",
                weight="bold" if index == 8 else "normal",
                url=manifest["dataset_url"] if index == 7 else None,
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output,
            format="svg",
            facecolor="white",
            metadata={
                "Title": title,
                "Description": description,
                "Date": None,
                "Creator": "scripts/render_stanford_comparison.py",
                "Source": manifest["dataset_url"],
                "Rights": manifest["license_url"],
            },
        )
        if preview is not None:
            preview.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(preview, format="png", dpi=150, facecolor="white")
        plt.close(fig)
    svg = output.read_text()
    end_tag = svg.index(">", svg.index("<svg "))
    svg = (
        svg[:end_tag]
        + ' role="img" aria-labelledby="comparison-title comparison-description"'
        + svg[end_tag : end_tag + 1]
        + f'\n<title id="comparison-title">{html.escape(title)}</title>'
        + f'\n<desc id="comparison-description">{html.escape(description)}</desc>'
        + svg[end_tag + 1 :]
    )
    output.write_text(svg)
    return {
        "output": str(output),
        "preview_png": str(preview) if preview else None,
        "bytes": output.stat().st_size,
        "main_panel_vertices": vertices,
        "source_sha256": SOURCE_SHA256,
        "evidence_sha256": bundle["evidence_sha256"],
        "partial_evidence": partial,
        "frozen_score_source": report_name,
        "plotted_meshes": list(curves),
        "spatial_verification": spatial_verdict,
        "models_run": 0,
        "fitting_performed": False,
        "software": software,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Standalone accessible SVG")
    parser.add_argument("--preview-png", type=Path, help="Optional PNG for visual review")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Render actual mesh-80 evidence only; mark spatial verification unavailable",
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/stanford-manifest.json")
    parser.add_argument("--raw", type=Path, default=ROOT / "data/stanford/raw")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".svg":
        parser.error("--out must be an .svg file")
    if args.preview_png and args.preview_png.suffix.lower() != ".png":
        parser.error("--preview-png must be a .png file")
    try:
        bundle = load_evidence(args.evidence_dir, args.manifest, args.raw, partial=args.partial)
        result = render(bundle, args.out, args.preview_png)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"Cannot render verified evidence: {error}")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
