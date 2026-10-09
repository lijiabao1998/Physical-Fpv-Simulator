"""Render all feasible sets without selecting a resistance or recomputing evidence."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render():
    directory = ROOT / "docs/benchmarks"
    r = json.loads((directory / "stanford-series-loss-compatibility.json").read_text())
    sets = [(name, c["fixed_trajectory_feasible_set"]) for name, c in r["cases"].items()]
    endpoints = [s["interval_ohm"][1] * 1000 for _, s in sets if s["interval_ohm"] is not None]
    high = max(10, math.ceil(max(endpoints, default=50) / 10) * 10)

    def x(milliohm):
        return 110 + milliohm / high * 830

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="440" viewBox="0 0 1100 440">',
        '<rect width="1100" height="440" fill="white"/>',
        '<g font-family="Arial,sans-serif" fill="#14213d">',
        '<text x="55" y="40" font-size="25">Fixed-trajectory shared-term compatibility</text>',
        '<text x="55" y="69" font-size="16">All nonnegative R intervals meeting the '
        "unchanged 50 mV RMSE screen</text>",
    ]
    for tick in range(0, high + 1, 10):
        xx = x(tick)
        svg.append(f'<path d="M{xx:.2f},110V285" stroke="#dbe2ea"/>')
        svg.append(f'<text x="{xx:.2f}" y="310" font-size="14" text-anchor="middle">{tick}</text>')
    for index, (name, feasible) in enumerate(sets):
        yy = 155 + 90 * index
        color = ["#007f80", "#b44e29"][index]
        svg.append(f'<text x="55" y="{yy + 5}" font-size="19">{name}</text>')
        if feasible["interval_ohm"] is not None:
            lo, hi = [v * 1000 for v in feasible["interval_ohm"]]
            svg.append(
                f'<path d="M{x(lo):.2f},{yy}H{x(hi):.2f}" stroke="{color}" '
                'stroke-width="12" stroke-linecap="round"/>'
            )
            svg.append(
                f'<text x="{(x(lo) + x(hi)) / 2:.2f}" y="{yy - 24}" font-size="17" '
                f'text-anchor="middle">{lo:.3f}–{hi:.3f} mΩ</text>'
            )
        else:
            svg.append(f'<text x="120" y="{yy + 5}" font-size="17">{feasible["status"]}</text>')
    svg += [
        '<text x="410" y="340" font-size="15">Algebraic voltage-loss R (mΩ)</text>',
        f'<text x="55" y="377" font-size="20">Shared set: '
        f"{r['shared_feasible_set']['status']}</text>",
        '<text x="55" y="411" font-size="14">Post-hoc, previously viewed cells. '
        "No R selected; no DFN, cutoff, capacity or heat recomputation.</text>",
        "</g></svg>",
    ]
    (directory / "stanford-series-loss-compatibility.svg").write_text("\n".join(svg) + "\n")


if __name__ == "__main__":
    render()
