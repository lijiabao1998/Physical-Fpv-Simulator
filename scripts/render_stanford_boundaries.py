"""Plot recorded finite-delay ratios; no interpolation, resistance fit or model run."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BOUNDARIES = (
    ("charge_start", "Charge start (rest → CC)"),
    ("cv_stop", "CV stop (CV → rest)"),
    ("discharge_start", "Discharge start (rest → discharge)"),
    ("discharge_stop", "Discharge stop (discharge → rest)"),
)
COLORS = ("#176B89", "#E07B39", "#5C8D46", "#925DA1", "#BA4755", "#635A4C")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("results/stanford-boundaries-v1/report.json")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("results/stanford-boundaries-v1/ratios.svg")
    )
    args = parser.parse_args()
    report = json.loads(args.source.read_text())
    cases = sorted(report["cases"], key=lambda case: case["cell_id"])
    if not report["complete"] or [c["cell_id"] for c in cases] != [f"k{i}" for i in range(1, 7)]:
        raise ValueError("This six-cell figure requires all six qualified cases")
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 8.6), sharex=True)
    fig.subplots_adjust(top=0.86, bottom=0.25, left=0.085, right=0.975, hspace=0.33, wspace=0.24)
    points = 0
    for axis, (boundary_id, title) in zip(axes.flat, BOUNDARIES, strict=True):
        unstable = 0
        for color, case in zip(COLORS, cases, strict=True):
            boundary = next(b for b in case["analysis"]["boundaries"] if b["id"] == boundary_id)
            samples = boundary["delayed_comparisons"]
            if any(p["apparent_transient_ratio_ohm"] is None for p in samples):
                raise ValueError("Undefined ratio needs an explicit missing-data figure")
            x = [p["post_elapsed_since_inferred_commanded_origin_s"] for p in samples]
            y = [1000 * p["apparent_transient_ratio_ohm"] for p in samples]
            axis.plot(
                x, y, color=color, marker="o", markersize=3, linewidth=1.1, label=case["cell_id"]
            )
            axis.scatter(x[:1], y[:1], color=color, marker="s", s=35, zorder=3)
            unstable += sum(p["ill_conditioned"] for p in samples)
            points += len(samples)
        axis.set_title(title, loc="left", fontsize=11, fontweight="bold")
        axis.set_ylabel("Apparent ΔV/ΔI (mΩ)")
        axis.grid(alpha=0.23)
        axis.text(
            0.98,
            0.03,
            f"{unstable}/60 small-ΔI pairs",
            transform=axis.transAxes,
            ha="right",
            fontsize=8,
            color="#625348",
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    for axis in axes[-1]:
        axis.set_xlabel("Observed delay since next commanded-step origin (s)")
    fig.suptitle(
        "Six-cell recorded boundary responses", x=0.085, ha="left", fontsize=19, fontweight="bold"
    )
    fig.text(
        0.085,
        0.91,
        "Nominal 25°C / 1C files · squares: primary pairs · lines connect measured samples, no fit",
        fontsize=10,
    )
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="lower center", bbox_to_anchor=(0.53, 0.17), ncol=6, frameon=False
    )
    fig.text(
        0.085,
        0.055,
        "Ratios use the last pre-step sample and each of the first 10 post-step samples; "
        "current is charge-positive.\n"
        "Small ΔI means |ΔI| < 0.5 A. Actual delays/current, state and relaxation differ; "
        "measurement uncertainty is unknown.\n"
        "These ratios do not identify ohmic/contact resistance or exclude a fixed-R component. "
        "No model run or fitting.\n"
        "Source: Catenaro & Onori, DOI 10.17632/kxsbr4x3j2.2, CC BY 4.0. "
        "Derived analysis; authors do not endorse it.",
        fontsize=8.6,
        linespacing=1.45,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160, metadata={"Creator": "Physical FPV Simulator"})
    plt.close(fig)
    print(
        json.dumps(
            {"observed_pairs_plotted": points, "output": str(args.out), "model_runs": 0, "fits": 0}
        )
    )


if __name__ == "__main__":
    main()
