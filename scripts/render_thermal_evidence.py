"""Render all residual CSV samples as standalone SVG evidence; no plotting dependency."""

import argparse
import html
import json
from pathlib import Path

import numpy as np

COLORS = ("#1464a5", "#d66c18")


def render(case, csv_path, output):
    values = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if values.ndim != 2 or values.shape[1] != 7 or not np.isfinite(values).all():
        raise ValueError("Expected finite seven-column common-interval residual CSV")
    time = values[:, 0]
    width, height = 960, 1220
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#213547;font-size:14px}</style>",
    ]

    def text(x, y, content, size=14):
        parts.append(
            f'<text x="{x}" y="{y}" style="font-size:{size}px">{html.escape(content)}</text>'
        )

    text(
        72,
        35,
        f"LG M50 cell{case['cell']} | {case['c_rate']:g}C | "
        f"nominal {case['nominal_temperature_c']}°C",
        24,
    )
    text(72, 61, "ORegan2022 / DFN / grid40 / published h15 / no new fit or voltage alignment")
    text(
        72,
        85,
        f"Coverage {case['time_coverage']:.2%}; empirical "
        f"{'PASS' if case['empirical_gate_passed'] else 'FAIL'}; "
        f"numerical {case['numerical_status'].upper()}",
    )
    panels = [
        ("Voltage [V]", [values[:, 1], values[:, 2]], ["Measured", "Predicted"]),
        (
            "Temperature [°C]",
            [values[:, 4] - 273.15, values[:, 5] - 273.15],
            ["Measured surface", "Predicted volume average"],
        ),
        ("Voltage residual [mV]", [values[:, 3] * 1000], ["Predicted minus measured"]),
        ("Temperature residual [K]", [values[:, 6]], ["Volume average minus surface"]),
    ]
    for index, (label, series, names) in enumerate(panels):
        left, top, plot_width, plot_height = 90, 135 + index * 245, 810, 160
        low = min(float(a.min()) for a in series)
        high = max(float(a.max()) for a in series)
        spread = max(high - low, 1e-6)
        low -= 0.08 * spread
        high += 0.08 * spread
        text(72, top - 14, label, 17)
        for i in range(5):
            fraction = i / 4
            y = top + plot_height * (1 - fraction)
            value = low + (high - low) * fraction
            parts.append(
                f'<line x1="{left}" y1="{y}" x2="{left + plot_width}" y2="{y}" stroke="#dce2e8"/>'
            )
            text(15, y + 5, f"{value:.2f}")
            x = left + plot_width * fraction
            text(x - 12, top + plot_height + 22, f"{time[0] + (time[-1] - time[0]) * fraction:.0f}")
        for number, array in enumerate(series):
            points = " ".join(
                f"{left + plot_width * (t - time[0]) / (time[-1] - time[0]):.3f},"
                f"{top + plot_height * (high - value) / (high - low):.3f}"
                for t, value in zip(time, array, strict=True)
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{COLORS[number]}" '
                'stroke-width="1.5"/>'
            )
            text(left + number * 280, top + plot_height + 49, names[number])
            parts.append(
                f'<line x1="{left - 18 + number * 280}" y1="{top + plot_height + 44}" '
                f'x2="{left - 3 + number * 280}" y2="{top + plot_height + 44}" '
                f'stroke="{COLORS[number]}" stroke-width="3"/>'
            )
        text(765, top + plot_height + 49, "Elapsed time [s]")
    text(
        72,
        1128,
        "All CSV samples shown. Common interval only; full cutoff/coverage are in the JSON report.",
    )
    text(
        72,
        1151,
        "Surface/volume-average mismatch and temperature extrapolations remain limitations.",
    )
    text(72, 1180, "Data: Brosa Planella et al. (2021), doi:10.5281/zenodo.4864437; BSD-3-Clause.")
    parts.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results/thermal-final"))
    parser.add_argument("--out", type=Path, default=Path("docs/benchmarks/thermal-figures"))
    args = parser.parse_args()
    report = json.loads((args.results / "report.json").read_text())
    for case in report["cases"]:
        if case.get("cell") != "790" or "error" in case:
            continue
        name = f"cell790_{case['nominal_temperature_c']}C_5A"
        render(case, args.results / f"{name}-residuals.csv", args.out / f"{name}.svg")


if __name__ == "__main__":
    main()
