"""Render the complete, checksum-verified Stanford six-cell measured cohort.

Run from the repository root with the pinned plotting and numerical environment:
    python scripts/render_stanford_cohort.py --source results/stanford-cohort-v1
    python scripts/render_stanford_cohort.py --figure voltage-differences

Only actual discharge CSV measurements are plotted, on their commanded step clock.
This script performs no download, model solve, fit, smoothing, or extrapolation.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter
from render_stanford_measurements import DISPLAY_BINS, display_indices

from physical_fpv.stanford_cohort import summary_discharge
from physical_fpv.stanford_data import HEADERS

CELL_IDS = tuple(f"k{i}" for i in range(1, 7))
CSV_HEADER = "time_s,raw_signed_current_a,measured_voltage_v,measured_skin_temperature_k"
MANIFEST_SHA256 = "94bde5dd872de039d145abf33f66fc81c38897b4666d68586f00c950478dc482"
PROTOCOL_SHA256 = "56e6fad6558bbe3863e016d7aeafb131f7229c579518b40f51bbfac52354d294"
COLORS = ("#17669d", "#bd6700", "#008477", "#a3479d", "#ab4a45", "#383838")
LINESTYLES = ("-", "-", "--", "-", "--", ":")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def verify_summary(actual: dict, recorded: dict, cell_id: str) -> None:
    """Cross-check the complete CSV's units, sign, endpoints and current integral."""
    require(set(actual) == set(recorded), f"{cell_id}: changed summary schema")
    for key, value in actual.items():
        other = recorded[key]
        if isinstance(value, dict):
            verify_summary(value, other, cell_id)
        elif isinstance(value, str):
            require(value == other, f"{cell_id}: incorrect {key}")
        else:
            require(
                bool(np.isclose(value, other, rtol=1e-12, atol=1e-12)),
                f"{cell_id}: CSV disagrees with reported {key}",
            )


def load_evidence(source: Path, raw_dir: Path, manifest_path: Path) -> tuple:
    """Fail closed for partial reports or changed CSV, raw source, identity or units."""
    report_bytes = (source / "report.json").read_bytes()
    report = json.loads(report_bytes)
    require(report.get("all_sources_inspected") is True, "All six sources must be inspected")
    require(
        report.get("all_pairwise_metrics_available") is True,
        "All 15 pairs are required",
    )
    require(report.get("error") is None, "The source inspection reported an error")
    require(report.get("unavailable_pairs") == [], "The source report has unavailable pairs")
    require(report.get("new_model_solves") == 0, "Expected source-only evidence")
    require(report.get("fitting_performed") is False, "Expected unfitted source evidence")
    cases = report["cases"]
    require(
        len(cases) == 6 and {case["cell_id"] for case in cases} == set(CELL_IDS),
        "Expected exactly k1 through k6, each once",
    )
    pairs = report["pairwise_comparisons"]
    require(
        len(pairs) == 15
        and {(p["reference_id"], p["candidate_id"]) for p in pairs}
        == set(itertools.combinations(CELL_IDS, 2)),
        "The report does not contain the complete 15-pair cohort",
    )
    for pair in pairs:
        for quantity, unit in (
            ("voltage_difference", "v"),
            ("measured_skin_temperature_difference", "k"),
            ("raw_signed_current_difference", "a"),
        ):
            for key in (
                f"rmse_{unit}",
                f"signed_time_mean_{unit}",
                f"max_absolute_{unit}",
            ):
                require(
                    bool(np.isfinite(pair[quantity][key])),
                    "Nonfinite source-pair metric",
                )

    manifest_bytes = manifest_path.read_bytes()
    require(sha256(manifest_bytes) == MANIFEST_SHA256, "Frozen manifest changed")
    manifest = json.loads(manifest_bytes)
    recorded_hashes = report["input"]["source_sha256"]
    require(
        recorded_hashes["data/stanford-manifest.json"] == MANIFEST_SHA256
        and recorded_hashes["docs/stanford-cohort-protocol.md"] == PROTOCOL_SHA256,
        "Report is not from the frozen cohort protocol and manifest",
    )
    require(manifest["dataset_doi"] == "10.17632/kxsbr4x3j2.2", "Unexpected source DOI")
    require(manifest["license"] == "CC-BY-4.0", "Unexpected source license")
    require(
        manifest["authors"] == ["Edoardo Catenaro", "Simona Onori"],
        "Unexpected source creators",
    )
    entries = {entry["filename"]: entry for entry in manifest["files"]}
    require(
        set(entries) == {f"NMC_{cell}_1C_25degC.xlsx" for cell in CELL_IDS},
        "Manifest must identify exactly the frozen six files",
    )
    cases = {case["cell_id"]: case for case in cases}
    traces, identities = {}, {}
    for cell_id in CELL_IDS:
        case = cases[cell_id]
        filename = f"NMC_{cell_id}_1C_25degC.xlsx"
        entry = entries[filename]
        integrity = case["integrity"]
        inspected = case["source_inspection"]
        require(inspected["source"] == integrity, f"{cell_id}: inconsistent raw identity")
        require(tuple(inspected["columns"]) == HEADERS, f"{cell_id}: raw units changed")
        require(inspected["dataset_doi"] == manifest["dataset_doi"], "Source DOI mismatch")
        require(inspected["authors"] == manifest["authors"], "Source attribution mismatch")
        require(inspected["license"] == manifest["license"], "Source license mismatch")
        require(
            integrity["filename"] == filename
            and integrity["bytes"] == entry["size"]
            and integrity["sha256"] == entry["content_details"]["sha256_hash"],
            f"{cell_id}: report raw identity does not match manifest",
        )
        raw_content = (raw_dir / filename).read_bytes()
        require(
            len(raw_content) == entry["size"] and sha256(raw_content) == integrity["sha256"],
            f"{cell_id}: cached workbook bytes do not match the inspected source",
        )
        csv_content = (source / f"{cell_id}-observed.csv").read_bytes()
        require(
            sha256(csv_content) == case["observed_csv_sha256"],
            f"{cell_id}: observed CSV checksum mismatch",
        )
        require(
            csv_content.splitlines()[0].decode("ascii") == CSV_HEADER,
            f"{cell_id}: observed CSV columns or units changed",
        )
        observed = np.loadtxt(io.BytesIO(csv_content), delimiter=",", skiprows=1)
        verify_summary(summary_discharge(observed, cell_id), case["observed_discharge"], cell_id)
        traces[cell_id] = observed
        identities[cell_id] = {
            **integrity,
            "observed_csv_sha256": case["observed_csv_sha256"],
            "download_url": entry["content_details"]["download_url"],
            "quality_flags": case["quality_flags"],
        }
    return report, manifest, traces, identities, sha256(report_bytes)


def render(
    source: Path,
    report: dict,
    manifest: dict,
    traces: dict,
    identities: dict,
    digest: str,
    *,
    display_compression: bool = False,
):
    """Plot measured samples, optionally retaining extrema for a compact SVG."""
    title = "Stanford LG M50: six measured discharges"
    retained = {
        cell: (
            np.unique(
                np.concatenate(
                    [display_indices(values[:, 0], values[:, column]) for column in (1, 2, 3)]
                )
            )
            if display_compression
            else np.arange(len(values))
        )
        for cell, values in traces.items()
    }
    versions = {
        "python": platform.python_version(),
        "matplotlib": matplotlib.__version__,
        "numpy": np.__version__,
    }
    provenance = {
        "identity": "Measured source only; no model prediction",
        "report_sha256": digest,
        "renderer_sha256": sha256(Path(__file__).read_bytes()),
        "source_doi": manifest["dataset_doi"],
        "creators": manifest["authors"],
        "license": manifest["license"],
        "sources": identities,
        "software": versions,
        "display": (
            f"Union of original first/min/max/last samples across three signals in {DISPLAY_BINS} "
            "time bins per cell; onset inset unreduced; original clock; no smoothing"
            if display_compression
            else "Every observed CSV row; original commanded step-time; no smoothing"
        ),
        "original_measurement_rows": sum(len(values) for values in traces.values()),
        "main_panel_retained_rows": sum(len(indices) for indices in retained.values()),
        "units": {
            "time": "s, original Step_Time(s)",
            "voltage": "V",
            "current": "A, original negative discharge sign",
            "skin_temperature": "degrees C; CSV kelvin minus 273.15",
        },
        "limitations": [
            "k2-k6 histories and fresh-cell eligibility remain unresolved",
            "Manufacturing batch identity is unverified",
            "Measurement and calibration uncertainty are unavailable",
            "No independent validation or physical-cause inference",
        ],
    }
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#63717c",
            "axes.linewidth": 0.7,
            "grid.color": "#d9e0e5",
            "grid.linewidth": 0.55,
            "svg.fonttype": "none",
            "svg.hashsalt": "stanford-six-cell-source",
            "path.simplify": False,
            "agg.path.chunksize": 0,
        }
    ):
        fig = plt.figure(figsize=(13.8, 11.2), facecolor="white")
        grid = fig.add_gridspec(
            3,
            1,
            left=0.092,
            right=0.703,
            top=0.83,
            bottom=0.225,
            height_ratios=[1.35, 0.95, 1.1],
            hspace=0.23,
        )
        axes = [fig.add_subplot(grid[0])]
        axes.extend(fig.add_subplot(grid[i], sharex=axes[0]) for i in (1, 2))
        fig.text(0.092, 0.958, title, fontsize=21, weight="bold")
        fig.text(
            0.092,
            0.927,
            "Measured source only  |  Nominal 25 °C / 1C  |  k1–k6, all 15 source pairs available",
            fontsize=11.5,
            color="#41515e",
        )
        handles = [
            Line2D([0], [0], color=color, ls=style, lw=2, label=cell)
            for cell, color, style in zip(CELL_IDS, COLORS, LINESTYLES, strict=True)
        ]
        fig.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(0.085, 0.908),
            ncol=6,
            frameon=False,
            handlelength=3,
            columnspacing=2.3,
            fontsize=11,
        )
        for index, (ax, column, ylabel) in enumerate(
            zip(
                axes,
                (2, 1, 3),
                ("Voltage [V]", "Raw current [A]", "Skin temperature [°C]"),
                strict=True,
            )
        ):
            for cell, color, style in zip(CELL_IDS, COLORS, LINESTYLES, strict=True):
                values = traces[cell][retained[cell]]
                y = values[:, column] - (273.15 if column == 3 else 0)
                ax.plot(values[:, 0], y, color=color, ls=style, lw=1.0, alpha=0.95)
                ax.plot(values[[0, -1], 0], y[[0, -1]], "o", color=color, ms=3.5, zorder=5)
            ax.set_ylabel(ylabel, labelpad=10)
            ax.set_xlim(0, 3535)
            ax.set_xticks(np.arange(0, 3501, 500))
            ax.grid(axis="both")
            ax.text(
                -0.132,
                1.02,
                "ABC"[index],
                transform=ax.transAxes,
                weight="bold",
                fontsize=12,
            )
            if index < 2:
                ax.tick_params(labelbottom=False)
        axes[0].set_ylim(2.43, 4.16)
        axes[0].set_yticks([2.5, 3, 3.5, 4])
        axes[1].yaxis.set_major_formatter(FormatStrFormatter("%.4f"))
        axes[1].set_yticks([-5.0004, -5.0002, -5.0000])
        axes[1].set_ylim(-5.00050, -4.99997)
        axes[1].text(
            0.015,
            1.055,
            "Zoomed current scale; negative = discharge",
            transform=axes[1].transAxes,
            fontsize=9,
            color="#41515e",
        )
        axes[2].set_ylim(23.6, 36.2)
        axes[2].set_yticks([24, 27, 30, 33, 36])
        axes[2].set_xlabel("Commanded discharge step-time [s]", labelpad=9)

        onset = fig.add_axes([0.775, 0.673, 0.198, 0.156])
        first_min = min(values[0, 0] for values in traces.values())
        onset.axvspan(0, first_min, facecolor="#fff1d8", edgecolor="#b79b69", hatch="///", lw=0)
        for cell, color, style in zip(CELL_IDS, COLORS, LINESTYLES, strict=True):
            values = traces[cell]
            selected = values[:, 0] <= 5
            onset.plot(values[selected, 0], values[selected, 2], color=color, ls=style, lw=1.2)
            onset.plot(values[0, 0], values[0, 2], "o", color=color, ms=4)
        onset.set(
            xlim=(0, 5),
            ylim=(3.81, 4.08),
            xticks=[0, 1, 3, 5],
            yticks=[3.85, 3.95, 4.05],
            xlabel="Original step-time [s]",
            ylabel="V",
        )
        onset.grid(axis="y")
        onset.set_title("First measured voltage samples", loc="left", fontsize=10.5, pad=11)
        onset.xaxis.label.set_fontsize(9)
        onset.yaxis.label.set_fontsize(9)
        onset.tick_params(labelsize=9)
        fig.text(
            0.775,
            0.600,
            "Hatched: no cell observed yet.\nDots: actual first / last observations.",
            fontsize=9,
            color="#41515e",
            linespacing=1.5,
        )

        fig.text(0.767, 0.56, "Recorded windows [s]", weight="bold", fontsize=11)
        fig.text(0.767, 0.533, "Cell", fontsize=9, color="#41515e")
        fig.text(0.86, 0.533, "First", ha="right", fontsize=9, color="#41515e")
        fig.text(0.976, 0.533, "Last", ha="right", fontsize=9, color="#41515e")
        for index, (cell, color) in enumerate(zip(CELL_IDS, COLORS, strict=True)):
            y = 0.504 - index * 0.029
            values = traces[cell]
            fig.text(0.767, y, cell, color=color, weight="bold", fontsize=10)
            fig.text(0.86, y, f"{values[0, 0]:.4f}", ha="right", fontsize=10)
            fig.text(0.976, y, f"{values[-1, 0]:.4f}", ha="right", fontsize=10)
        fig.text(
            0.767,
            0.307,
            "Each trace starts at its recorded first\nsample and stops at its own endpoint.\n"
            "Missing prefixes and tails stay absent.",
            fontsize=9,
            linespacing=1.55,
            color="#41515e",
        )

        flags = [
            f"{cell}: {', '.join(identities[cell]['quality_flags'])}"
            for cell in CELL_IDS
            if identities[cell]["quality_flags"]
        ]
        require(
            not flags,
            "This layout requires explicit accommodation of source quality flags",
        )
        notes = [
            "All recorded discharge samples are drawn; no smoothing, time shift or normalization. "
            "Temperature is measured skin temperature.",
            "k2–k6 prior histories / fresh-cell eligibility and common manufacturing batch "
            "are unverified.",
            "Measurement / calibration uncertainty is unavailable; no uncertainty bands. "
            "No independent validation or physical cause is established.",
            "Source files: NMC_k1_1C_25degC.xlsx through NMC_k6_1C_25degC.xlsx. "
            "Workbook and CSV hashes verified against the complete report.",
        ]
        if display_compression:
            notes[0] = (
                f"Display: original first/min/max/last samples per {DISPLAY_BINS} time bins, "
                "union across signals; full CSVs/statistics unchanged."
            )
            notes[3] = (
                "No smoothing or time shift; every bin's measured extrema and endpoints retained. "
                "Source workbook and CSV hashes verified."
            )
        for y, note in zip((0.155, 0.132, 0.109, 0.086), notes, strict=True):
            fig.text(0.092, y, note, fontsize=9.1, color="#344550")
        fig.text(
            0.092,
            0.054,
            "Data: Edoardo Catenaro & Simona Onori  |  DOI 10.17632/kxsbr4x3j2.2  |  CC BY 4.0",
            fontsize=9.5,
            url=manifest["dataset_url"],
        )
        fig.text(0.092, 0.030, f"Report SHA256: {digest}", fontsize=8.5, color="#41515e")
        metadata = json.dumps(provenance, sort_keys=True)
        output = source / (
            "cohort-measurements-compact.svg" if display_compression else "cohort-measurements.svg"
        )
        preview = None if display_compression else source / "cohort-measurements.png"
        fig.savefig(output, metadata={"Title": title, "Description": metadata, "Date": None})
        if preview is not None:
            fig.savefig(preview, dpi=170, metadata={"Title": title, "Description": metadata})
        plt.close(fig)
    return {
        "svg": str(output),
        "png": str(preview) if preview is not None else None,
        "report_sha256": digest,
        "source_measurement_rows": sum(len(values) for values in traces.values()),
        "main_panel_retained_rows": sum(len(indices) for indices in retained.values()),
    }


def render_voltage_differences(
    source: Path,
    report: dict,
    manifest: dict,
    traces: dict,
    identities: dict,
    digest: str,
) -> dict:
    """Expose all 15 reported source-pair voltage RMSEs without modifying the overlay."""
    matrix = np.full((6, 6), np.nan)
    index = {cell: position for position, cell in enumerate(CELL_IDS)}
    intervals = {}
    for pair in report["pairwise_comparisons"]:
        reference, candidate = pair["reference_id"], pair["candidate_id"]
        value_mv = pair["voltage_difference"]["rmse_v"] * 1000
        require(value_mv >= 0, "Source-pair RMSE must be nonnegative")
        matrix[index[reference], index[candidate]] = value_mv
        matrix[index[candidate], index[reference]] = value_mv
        intervals[f"{reference}-{candidate}"] = pair["common_observed_interval_s"]
    require(np.isfinite(matrix).sum() == 30, "Expected 15 unique source-pair RMSEs")
    title = "Measured source-to-source voltage differences"
    metadata = {
        "identity": "Measured source-to-source voltage RMSE, not model error",
        "report_sha256": digest,
        "renderer_sha256": sha256(Path(__file__).read_bytes()),
        "source_doi": manifest["dataset_doi"],
        "creators": manifest["authors"],
        "license": manifest["license"],
        "sources": identities,
        "unit": "mV",
        "display": "All 15 unique unordered pairs; symmetric entries repeated; diagonal N/A",
        "integration": "Exact time integral of squared piecewise-linear voltage differences",
        "pairwise_common_observed_intervals_s": intervals,
        "limitations": [
            "Each pair can have a different common observed time interval",
            "No inference of shared history, manufacturing batch, thermal behavior or cause",
            "Measurement uncertainty is unavailable; no statistical classification",
            "No model validation or model-error comparison",
        ],
        "software": {
            "python": platform.python_version(),
            "matplotlib": matplotlib.__version__,
            "numpy": np.__version__,
        },
    }
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "svg.fonttype": "none",
            "svg.hashsalt": "stanford-six-cell-voltage-differences",
        }
    ):
        fig = plt.figure(figsize=(11.4, 10.0), facecolor="white")
        fig.text(0.06, 0.956, title, fontsize=20, weight="bold")
        fig.text(
            0.06,
            0.923,
            "Nominal 25 °C / 1C  |  All 15 source pairs  |  Time-weighted RMSE [mV]",
            fontsize=12,
            color="#41515e",
        )
        ax = fig.add_axes([0.11, 0.285, 0.66, 0.585])
        cmap = plt.get_cmap("Blues").copy()
        cmap.set_bad("#eef1f4")
        image = ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=0, vmax=180)
        ax.set_xticks(np.arange(6), labels=CELL_IDS)
        ax.set_yticks(np.arange(6), labels=CELL_IDS)
        ax.xaxis.tick_top()
        ax.tick_params(axis="both", length=0, labelsize=12, pad=10)
        ax.set_xticks(np.arange(-0.5, 6, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 6, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(which="minor", bottom=False, left=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        for row, col in itertools.product(range(6), repeat=2):
            value = matrix[row, col]
            diagonal = row == col
            label = "N/A" if diagonal else f"{value:.2f}"
            color = "#75818b" if diagonal else ("white" if value >= 100 else "#18364d")
            ax.text(
                col,
                row,
                label,
                ha="center",
                va="center",
                fontsize=14,
                color=color,
                weight="normal" if diagonal else "bold",
            )
        cax = fig.add_axes([0.806, 0.335, 0.025, 0.46])
        colorbar = fig.colorbar(image, cax=cax, ticks=[0, 30, 60, 90, 120, 150, 180])
        colorbar.set_label("Source-to-source voltage RMSE [mV]", labelpad=13)
        colorbar.outline.set_visible(False)
        colorbar.ax.tick_params(length=0, labelsize=10, pad=6)
        fig.text(
            0.162,
            0.257,
            "Symmetric display: each pair is repeated. Diagonal: not applicable.",
            fontsize=10,
            color="#41515e",
        )

        notes = [
            "Each pair uses its own common observed time window; overlap intervals differ "
            "and are recorded in report.json.",
            "Original commanded step-times; exact squared-difference integration. "
            "No extrapolation, offset, smoothing or normalization.",
            "Voltage similarity does not establish shared histories, manufacturing batch, "
            "thermal behavior or a physical cause.",
            "k2–k6 histories and measurement uncertainty remain unresolved. "
            "Measured skin-temperature spread is shown in the companion overlay.",
            "These are measured-source differences, not model errors or independent validation.",
        ]
        for y, note in zip((0.202, 0.178, 0.154, 0.130, 0.106), notes, strict=True):
            fig.text(0.06, y, note, fontsize=9.0, color="#344550")
        fig.text(
            0.06,
            0.062,
            "Data: Edoardo Catenaro & Simona Onori  |  DOI 10.17632/kxsbr4x3j2.2  |  CC BY 4.0",
            fontsize=10,
            url=manifest["dataset_url"],
        )
        fig.text(0.06, 0.036, f"Report SHA256: {digest}", fontsize=8.5, color="#41515e")
        encoded = json.dumps(metadata, sort_keys=True)
        output = source / "cohort-voltage-differences.svg"
        preview = source / "cohort-voltage-differences.png"
        fig.savefig(output, metadata={"Title": title, "Description": encoded, "Date": None})
        fig.savefig(preview, dpi=170, metadata={"Title": title, "Description": encoded})
        plt.close(fig)
    return {
        "svg": str(output),
        "png": str(preview),
        "report_sha256": digest,
        "unique_source_pairs": len(intervals),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("results/stanford-cohort-v1"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/stanford/raw"))
    parser.add_argument("--manifest", type=Path, default=Path("data/stanford-manifest.json"))
    parser.add_argument(
        "--figure",
        choices=("measurements", "voltage-differences", "compact", "both"),
        default="measurements",
        help="Select the overlay, supplementary source-RMSE matrix, or both",
    )
    args = parser.parse_args()
    evidence = load_evidence(args.source, args.raw_dir, args.manifest)
    if args.figure in ("measurements", "both"):
        print(json.dumps(render(args.source, *evidence), indent=2))
    if args.figure in ("voltage-differences", "both"):
        print(json.dumps(render_voltage_differences(args.source, *evidence), indent=2))
    if args.figure == "compact":
        print(json.dumps(render(args.source, *evidence, display_compression=True), indent=2))


if __name__ == "__main__":
    main()
