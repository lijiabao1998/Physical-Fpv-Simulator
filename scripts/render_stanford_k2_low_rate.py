"""Plot the conditional charge comparison with no fitting or physical solve."""

import json
from pathlib import Path

import numpy as np
from check_stanford_k2_low_rate import load_inputs

from physical_fpv.low_rate_reference import compare

ROOT = Path(__file__).resolve().parents[1]


def render():
    directory = ROOT / "docs/benchmarks"
    low, high, model = load_inputs(directory)
    _, data = compare(low, high, model)
    report = json.loads((directory / "stanford-k2-low-rate-comparison.json").read_text())
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850">',
        '<rect width="1200" height="850" fill="white"/><g font-family="Arial,sans-'
        'serif" fill="#14213d">',
        '<text x="65" y="40" font-size="25">k2: a measured low-rate reference '
        "constrains the voltage gap</text>",
        '<text x="65" y="70" font-size="16">Recorded discharged Ah alignment is '
        "conditional; absolute SOC and inventory are unverified.</text>",
    ]
    colors = ["#007f80", "#bd4b34", "#6146a4"]
    qmax = float(data[-1, 0])

    def x(q):
        return 95 + q / qmax * 1030

    def panel(top, height, lo, hi, ticks, title, curves):
        def y(v):
            return top + height - (v - lo) / (hi - lo) * height

        svg.append(f'<text x="65" y="{top - 20}" font-size="18">{title}</text>')
        for tick in ticks:
            svg.append(f'<path d="M95,{y(tick):.2f}H1125" stroke="#dae1e8"/>')
            svg.append(
                f'<text x="80" y="{y(tick) + 5:.2f}" text-anchor="end" '
                f'font-size="14">{tick:g}</text>'
            )
        for tick in range(5):
            svg.append(f'<path d="M{x(tick):.2f},{top}V{top + height}" stroke="#e8edf2"/>')
            svg.append(
                f'<text x="{x(tick):.2f}" y="{top + height + 22}" text-anchor="middle" '
                f'font-size="14">{tick}</text>'
            )
        for index, (label, column, factor) in enumerate(curves):
            # Display sampling only; all metrics use every original charge knot.
            q = np.linspace(0, qmax, 1800)
            v = np.interp(q, data[:, 0], data[:, column]) * factor
            points = " ".join(f"{x(a):.2f},{y(b):.2f}" for a, b in zip(q, v, strict=True))
            svg.append(
                f'<polyline points="{points}" fill="none" stroke="{colors[index]}" '
                'stroke-width="2"/>'
            )
            xx = 95 + index * 355
            svg.append(
                f'<text x="{xx}" y="{top + height + 47}" fill="{colors[index]}" '
                f'font-size="15">{label}</text>'
            )

    panel(
        125,
        215,
        2.4,
        4.3,
        [2.5, 3, 3.5, 4],
        "Voltage (V): measured 0.05C and 1C; saved model bulk OCV",
        [("Measured 0.05C", 1, 1), ("Measured 1C", 2, 1), ("Saved bulk OCV", 4, 1)],
    )
    panel(
        440,
        205,
        -40,
        650,
        [0, 150, 300, 450, 600],
        "Voltage differences (mV): compare the measured rate gap with model loss",
        [
            ("Measured low-rate minus 1C", 6, 1000),
            ("Model bulk minus terminal", 7, 1000),
            ("Bulk OCV minus low-rate", 5, 1000),
        ],
    )
    # Full late model loss reaches596.7mV; show out-of-panel note rather than conceal clipping.
    svg += [
        '<text x="65" y="722" font-size="16">Late model loss reaches 596.7 mV. '
        "Curves display-sampled; metrics use all original charge knots.</text>",
        '<text x="65" y="750" font-size="17">Mean: measured rate gap 249.38 mV; '
        "model loss 212.87 mV; static-reference difference +7.66 mV.</text>",
        '<text x="65" y="778" font-size="16">Bulk OCV lies below low-rate voltage '
        "over 45.41% of common charge, by up to 14.96 mV.</text>",
        '<text x="65" y="807" font-size="15">Both start conventions agree closely. '
        "Unknown history and temperature differences prevent unique causal "
        "attribution.</text>",
        '<text x="65" y="833" font-size="14">Catenaro and Onori, DOI '
        "10.17632/kxsbr4x3j2.2, CC BY4.0. Historical 1C result: 55.003 mV, fails 50 "
        "mV gate.</text>",
        "</g></svg>",
    ]
    assert report["historical_1c_passed"] is False
    (directory / "stanford-k2-low-rate-comparison.svg").write_text("\n".join(svg) + "\n")


if __name__ == "__main__":
    render()
