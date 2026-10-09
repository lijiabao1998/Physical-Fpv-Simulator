"""Render fixed-query scaling without suggesting a fitted physical resistance."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def render():
    directory = ROOT / "docs/benchmarks"
    c = json.loads((directory / "stanford-cross-rate-onset.json").read_text())["comparison"]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650">',
        '<rect width="1200" height="650" fill="white"/>',
        '<g font-family="Arial,sans-serif" fill="#14213d">',
    ]

    def text(x, y, label, size=16, color="#14213d"):
        svg.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{escape(label)}</text>'
        )

    text(55, 38, "Two-rate check: early specimen contrast scales closely with current", 24)
    text(
        55,
        68,
        "Previously viewed records; fixed nominal-clock queries; "
        "no physical resistance identified.",
        16,
    )

    def panel(left, lo, hi, ticks, title, series):
        top, height, width = 140, 285, 470

        def x(t):
            return left + t / 10 * width

        def y(value):
            return top + height - (value - lo) / (hi - lo) * height

        text(left - 10, 112, title, 18)
        for tick in ticks:
            svg.append(f'<path d="M{left},{y(tick):.2f}h{width}" stroke="#dce3eb"/>')
            text(left - 40, y(tick) + 5, f"{tick:g}", 13)
        for tick in (0, 2, 5, 10):
            xx = x(tick)
            svg.append(f'<path d="M{xx:.2f},{top}v{height}" stroke="#edf0f4"/>')
            text(xx - 5, top + height + 23, str(tick), 13)
        text(left + 140, top + height + 48, "Nominal step time (s)", 14)
        for index, (label, values, color, dashed) in enumerate(series):
            points = " ".join(
                f"{x(t):.2f},{y(v):.2f}" for t, v in zip(c["query_times_s"], values, strict=True)
            )
            dash = ' stroke-dasharray="6 4"' if dashed else ""
            svg.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"{dash}/>'
            )
            for t, v in zip(c["query_times_s"], values, strict=True):
                svg.append(f'<circle cx="{x(t):.2f}" cy="{y(v):.2f}" r="3" fill="{color}"/>')
            text(left + (index % 2) * 235, top + height + 75 + (index // 2) * 23, label, 14, color)

    series = []
    for cell, color in (("k1", "#007f80"), ("k2", "#bb4e32")):
        for rate, label, dash in (("1c", "1C", False), ("005c", "0.05C", True)):
            values = [
                v * 1000 for v in c["cases"][cell + "_" + rate]["finite_time_apparent_response_ohm"]
            ]
            series.append((cell + " " + label, values, color, dash))
    panel(90, 25, 75, [30, 40, 50, 60, 70], "Finite-time response / current (mOhm)", series)
    panel(
        675,
        7.2,
        7.8,
        [7.2, 7.4, 7.6, 7.8],
        "Low-rate k1 minus k2 voltage fall (mV)",
        [
            (
                "Observed",
                [
                    v * 1000
                    for v in c["cell_contrasts_k1_minus_k2"]["005c"]["observed_fall_difference_v"]
                ],
                "#6146a4",
                False,
            ),
            (
                "Predicted from 1C",
                [v * 1000 for v in c["predicted_low_rate_cell_fall_difference_v"]],
                "#586779",
                True,
            ),
        ],
    )
    text(
        55,
        558,
        "Observed minus predicted low-rate contrast: -0.042, +0.212, +0.010, -0.117 mV.",
        18,
    )
    text(
        55,
        586,
        "Lines join four correlated queries. "
        "Temperature, rest/history and acquisition latency remain confounders.",
        15,
    )
    text(
        55,
        612,
        "No statistical or physical PASS. "
        "Existing whole-record model failures and the 50 mV gate are unchanged.",
        15,
    )
    text(
        55,
        637,
        "Catenaro and Onori, DOI 10.17632/kxsbr4x3j2.2, CC BY4.0. "
        "Source data and reproduction code in this repo.",
        13,
    )
    svg.append("</g></svg>")
    (directory / "stanford-cross-rate-onset.svg").write_text("\n".join(svg) + "\n")


if __name__ == "__main__":
    render()
