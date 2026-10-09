"""Render the fixed Stanford k1 raw-source pilot; no model or fitted curve is used.

Requires matplotlib and the optional workbook dependencies, alongside the package.
Run from the repository root: python scripts/render_stanford_measurements.py
"""

from __future__ import annotations

import argparse
import html
import io
import json
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl

from physical_fpv.stanford_data import HEADERS, inspect_records, validate_workbook_bytes

SOURCE_FILENAME = "NMC_k1_1C_25degC.xlsx"
DISPLAY_BINS = 120
COLOR = "#175b91"


def load_source(manifest_path: Path, raw_dir: Path) -> tuple[dict, dict, np.ndarray]:
    """Check the pinned bytes and complete raw schema before selecting either phase."""
    manifest = json.loads(manifest_path.read_text())
    entry = next(item for item in manifest["files"] if item["filename"] == SOURCE_FILENAME)
    content = (raw_dir / SOURCE_FILENAME).read_bytes()
    integrity = validate_workbook_bytes(content, entry)
    if not openpyxl.DEFUSEDXML:
        raise RuntimeError(
            "Install the pinned optional workbook dependencies, including defusedxml"
        )
    workbook = openpyxl.load_workbook(
        io.BytesIO(content), read_only=True, data_only=True, keep_links=False
    )
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Expected the qualified single-sheet source")
        stream = workbook.worksheets[0].iter_rows(values_only=True)
        if tuple(next(stream)) != HEADERS:
            raise ValueError("Source schema or units changed")
        rows = list(stream)
    finally:
        workbook.close()
    report, discharge = inspect_records(rows)
    if not report["canonical_six_step_sequence"] or discharge is None:
        raise ValueError("Expected the fixed six-step pilot with one discharge phase")
    report["source"] = integrity
    return manifest, report, np.asarray([row[1:] for row in rows], dtype=float)


def display_indices(time: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Retain actual first/min/max/last samples in each equal-time display bin.

    This is display compression only: no averaging, interpolation, or source rewrite.
    Per-bin extrema and endpoints survive in their original chronological order.
    """
    bins = np.minimum(
        ((time - time[0]) / (time[-1] - time[0]) * DISPLAY_BINS).astype(int),
        DISPLAY_BINS - 1,
    )
    kept = set()
    for number in np.unique(bins):
        positions = np.flatnonzero(bins == number)
        kept.update(
            (
                int(positions[0]),
                int(positions[-1]),
                int(positions[np.argmin(values[positions])]),
                int(positions[np.argmax(values[positions])]),
            )
        )
    return np.asarray(sorted(kept))


def render(manifest: dict, report: dict, values: np.ndarray, output: Path, preview: Path | None):
    rest = values[values[:, 2] == 4]
    discharge = values[values[:, 2] == 5]
    origin = float(np.median(discharge[:, 0] - discharge[:, 1]))
    if np.max(np.abs(discharge[:, 0] - discharge[:, 1] - origin)) > 1e-7:
        raise ValueError("Source test and discharge step clocks no longer agree")
    rest_time = rest[:, 0] - origin
    discharge_time = discharge[:, 1]  # Preserve the recorded Step_Time(s), including 1.0006.
    first = float(discharge_time[0])
    mean_current = report["discharge"]["recorded_current_a"]
    software = {
        "python": platform.python_version(),
        "matplotlib": matplotlib.__version__,
        "openpyxl": openpyxl.__version__,
        "numpy": np.__version__,
    }
    title = "Measured LG M50: Stanford k1 pilot"
    description = (
        "Three measured-source panels show pre-discharge rest and discharge: signed current, "
        "terminal voltage, and surface temperature. Time is relative to the commanded discharge "
        f"start; the first discharge observation remains at {first:.4f} seconds. "
        "The inset shows actual current samples and hatches the unobserved initial interval. "
        "Discharge current is negative in the source. The temperature is a surface measurement, "
        "not inferred core or ambient temperature. This figure contains no model predictions. "
        f"Display compression retains first/min/max/last samples in {DISPLAY_BINS} time bins "
        "per phase and series; inset samples are unreduced. The source workbook is unchanged. "
        f"Source: {', '.join(manifest['authors'])}; DOI {manifest['dataset_doi']}; "
        f"{manifest['license']}. SHA256 {report['source']['sha256']}. "
        f"Rendering versions: {json.dumps(software, sort_keys=True)}."
    )
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#59636b",
            "axes.linewidth": 0.7,
            "grid.color": "#d8dde2",
            "grid.linewidth": 0.5,
            "svg.fonttype": "none",
            "svg.hashsalt": "stanford-k1-source",
            "path.simplify": False,
        }
    ):
        fig, axes = plt.subplots(
            3,
            1,
            figsize=(11.4, 9.4),
            sharex=True,
            gridspec_kw={"height_ratios": [1.45, 1, 1]},
        )
        fig.subplots_adjust(left=0.095, right=0.975, top=0.845, bottom=0.245, hspace=0.20)
        fig.suptitle(title, x=0.095, y=0.981, ha="left", fontsize=19, weight="bold")
        fig.text(
            0.095,
            0.944,
            "Source condition: 1C / nominal 25 °C   |   NMC_k1_1C_25degC.xlsx",
            fontsize=11.5,
        )
        fig.text(
            0.095,
            0.915,
            f"Measured source only   •   {len(rest):,} rest + {len(discharge):,} discharge records",
            color="#43515d",
            fontsize=11,
        )

        panels = [(4, "Current [A]"), (3, "Voltage [V]"), (5, "Surface temperature [°C]")]
        plotted_samples = 0
        for ax, (column, label) in zip(axes, panels, strict=True):
            ax.axvspan(rest_time[0], 0, color="#f0f2f4", zorder=0)
            ax.axvline(0, color="#60676e", linestyle="--", linewidth=0.9, zorder=2)
            # Separate artists intentionally leave the interval between phases unconnected.
            for time, phase in ((rest_time, rest), (discharge_time, discharge)):
                keep = display_indices(time, phase[:, column])
                plotted_samples += len(keep)
                ax.plot(time[keep], phase[keep, column], color=COLOR, linewidth=1.15)
            ax.set_ylabel(label)
            ax.grid(axis="y")
            ax.tick_params(axis="both", labelsize=10)
        axes[0].set_ylim(-5.7, 0.7)
        axes[0].set_yticks([-5, -2.5, 0])
        axes[0].text(
            0.23,
            1.04,
            "Pre-discharge rest",
            transform=axes[0].transAxes,
            ha="center",
            fontsize=11,
            weight="bold",
        )
        axes[0].text(
            0.75,
            1.04,
            "Discharge",
            transform=axes[0].transAxes,
            ha="center",
            fontsize=11,
            weight="bold",
        )
        axes[0].text(
            0.66,
            0.42,
            f"Mean measured current\n{mean_current:.6f} A",
            transform=axes[0].transAxes,
            color=COLOR,
            fontsize=11,
        )
        axes[1].set_ylim(2.40, 4.35)
        axes[1].set_yticks([2.5, 3.0, 3.5, 4.0])
        axes[2].set_ylim(24.6, 31.8)
        axes[2].set_yticks([25, 27, 29, 31])
        axes[2].set_xlim(-3700, 3500)
        axes[2].set_xticks([-3600, -2400, -1200, 0, 1200, 2400, 3390])
        axes[2].set_xlabel("Time relative to commanded discharge start [s]", labelpad=9)

        inset = axes[0].inset_axes([0.075, 0.15, 0.34, 0.56])
        inset.axvspan(0, first, facecolor="#fff0d1", hatch="///", edgecolor="#d5b05b", lw=0)
        inset.axvline(0, color="#60676e", linestyle="--", linewidth=0.75)
        for time, phase in ((rest_time, rest), (discharge_time, discharge)):
            take = (time >= -2) & (time <= 3.1)
            inset.plot(time[take], phase[take, 4], "o", color=COLOR, markersize=3.7)
        inset.set(xlim=(-2, 3.1), ylim=(-5.8, 1.0), xticks=[-2, 0, 1, 3], yticks=[-5, 0])
        inset.tick_params(labelsize=8, pad=2)
        inset.set_xlabel("Onset detail [s]", fontsize=9, labelpad=2)
        inset.set_ylabel("A", fontsize=9, labelpad=3)
        inset.set_title(f"No discharge samples in 0 ≤ t < {first:.4f} s", fontsize=9, pad=6)
        inset.annotate(
            f"First: {first:.4f} s",
            xy=(first, discharge[0, 4]),
            xytext=(1.35, -1.9),
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": "#59636b", "lw": 0.7},
        )

        fig.text(
            0.095,
            0.166,
            "Blue lines: measured samples. Gray region: pre-rest. Dashed line: commanded start.",
            fontsize=10,
        )
        fig.text(
            0.095,
            0.140,
            "Raw current sign retained (negative = discharge). "
            "Surface temperature is measured skin temperature.",
            fontsize=10,
        )
        fig.text(
            0.095,
            0.114,
            f"Display: original first/min/max/last samples in {DISPLAY_BINS} time bins per phase; "
            "no smoothing.",
            fontsize=9.5,
        )
        fig.text(
            0.095,
            0.090,
            "Inset uses every sample in view. Full raw workbook remains unchanged; "
            "no time-zero sample is added.",
            fontsize=9.5,
        )
        fig.text(
            0.095,
            0.057,
            "Data: Edoardo Catenaro & Simona Onori  |  "
            f"DOI: {manifest['dataset_doi']}  |  CC BY 4.0",
            fontsize=9.5,
            url=manifest["dataset_url"],
        )
        fig.text(
            0.095,
            0.033,
            f"Source SHA256: {report['source']['sha256']}",
            fontsize=8.1,
            color="#43515d",
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
                "Creator": "scripts/render_stanford_measurements.py",
                "Source": manifest["dataset_url"],
                "Rights": manifest["license_url"],
            },
        )
        if preview is not None:
            preview.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(preview, dpi=150, facecolor="white")
        plt.close(fig)

    # Keep SVG text as text and expose a useful screen-reader description.
    svg = output.read_text()
    start = svg.index("<svg ")
    end = svg.index(">", start)
    svg = (
        svg[:end]
        + ' role="img" aria-labelledby="source-title source-description"'
        + svg[end : end + 1]
        + f'\n<title id="source-title">{html.escape(title)}</title>'
        + f'\n<desc id="source-description">{html.escape(description)}</desc>'
        + svg[end + 1 :]
    )
    output.write_text(svg)
    return {
        "output": str(output),
        "bytes": output.stat().st_size,
        "source_sha256": report["source"]["sha256"],
        "verified_source_rows": report["measurement_rows"],
        "selected_measurement_rows": len(rest) + len(discharge),
        "main_panel_vertices": plotted_samples,
        "first_discharge_step_time_s": first,
        "models_run": 0,
        "software": software,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/stanford-manifest.json"))
    parser.add_argument("--raw", type=Path, default=Path("data/stanford/raw"))
    parser.add_argument("--out", type=Path, default=Path("docs/benchmarks/stanford-k1-source.svg"))
    parser.add_argument(
        "--preview-png", type=Path, help="Optional raster preview for visual review"
    )
    args = parser.parse_args()
    manifest, report, values = load_source(args.manifest, args.raw)
    print(json.dumps(render(manifest, report, values, args.out, args.preview_png), indent=2))


if __name__ == "__main__":
    main()
