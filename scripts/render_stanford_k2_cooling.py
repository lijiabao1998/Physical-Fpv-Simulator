"""Render the stored cooling screen without recomputing a fit."""

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render():
    directory = ROOT / "docs/benchmarks"
    rows = list(csv.DictReader((directory / "stanford-k2-cooling-predictions.csv").open()))
    result = json.loads((directory / "stanford-k2-cooling.json").read_text())
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="835" viewBox="0 0 1100 835">',
        '<rect width="1100" height="835" fill="#ffffff"/>',
        '<g font-family="Arial,sans-serif" fill="#14213d">',
        '<text x="60" y="38" font-size="25">k2: cooling calibration and later-time checks</text>',
        '<text x="60" y="64" font-size="15">Previously viewed skin-temperature record. '
        "Effective decay only; no physical h identified.</text>",
    ]
    for panel, scenario in enumerate(result["scenarios"]):
        top = 115 + panel * 325
        x0, width, height = 85, 950, 235

        def x(t, origin=x0, span=width):
            return origin + (t - 60) / 3540 * span

        def y(temp, origin=top, span=height):
            return origin + (33 - temp) / 9 * span

        parts.append(
            f'<rect x="{x(60):.2f}" y="{top}" width="{x(599.0003) - x(60):.2f}" '
            f'height="{height}" fill="#e8eef7"/>'
        )
        for temp in (24, 26, 28, 30, 32):
            parts.append(f'<path d="M{x0},{y(temp):.2f}H{x0 + width}" stroke="#dde2e8"/>')
            parts.append(f'<text x="48" y="{y(temp) + 5:.2f}" font-size="13">{temp}</text>')
        for seconds in (60, 600, 1800, 3600):
            xx = x(seconds)
            parts.append(
                f'<path d="M{xx:.2f},{top}V{top + height}" stroke="#aab3c0" '
                'stroke-dasharray="4 4"/>'
            )
            parts.append(
                f'<text x="{xx:.2f}" y="{top + height + 23}" text-anchor="middle" '
                f'font-size="13">{seconds}</text>'
            )
        for field, color in [
            ("measured_skin_c", "#202d3a"),
            (scenario + "_fit_c", "#007f80"),
            (scenario + "_prior_c", "#bc4b26"),
        ]:
            chosen = rows[::5] + [rows[-1]]
            points = " ".join(
                f"{x(float(r['step_time_s'])):.2f},{y(float(r[field])):.2f}" for r in chosen
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
            )
        parts.append(
            f'<text x="20" y="{top + height / 2}" font-size="13" '
            f'transform="rotate(-90 20 {top + height / 2})" text-anchor="middle">'
            "Skin temperature (°C)</text>"
        )
        fit = result["scenarios"][scenario]["fit"]
        title = (
            f"{scenario.replace('_', ' ')}: baseline {fit['baseline_c']:.3f} °C; "
            f"fitted effective tau {fit['tau_s']:.1f} s"
        )
        parts.append(f'<text x="85" y="{top - 16}" font-size="17">{html.escape(title)}</text>')
        parts.append(
            f'<text x="515" y="{top + height + 45}" font-size="14">Rest step time (s)</text>'
        )
    parts += [
        '<text x="60" y="750" font-size="15">Black: measured skin · Teal: fitted decay '
        "· Orange: frozen h=15 analytic prior</text>",
        '<text x="60" y="775" font-size="14">Shading: 60–599.0003 s calibration; '
        "checking starts 600.0002 s.</text>",
        '<text x="60" y="805" font-size="13">Display: every fifth source sample; '
        "full CSV retained. Later windows excluded from fitting; not blind validation.</text>",
        "</g></svg>",
    ]
    (directory / "stanford-k2-cooling.svg").write_text("\n".join(parts) + "\n")


if __name__ == "__main__":
    render()
