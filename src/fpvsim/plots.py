"""Report figures (matplotlib, PNG).

Chart text is English so figures render on machines without CJK fonts; the
report prose around them is Traditional Chinese. Styling follows one fixed
system: categorical colours in a fixed order, thin lines, hairline solid
grids, one y-axis per chart, a legend whenever there is more than one series.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402
from scipy.spatial import ConvexHull  # noqa: E402

from . import units  # noqa: E402
from .mass import BoxShape, CylinderShape, MassItem  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")  # fixed order: blue, orange, aqua, yellow
GROUP_COLORS = {"propulsion": SERIES[0], "battery": SERIES[1], "avionics": SERIES[2], "frame": MUTED, "misc": INK_2}

STYLE = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.labelsize": 9,
    "axes.grid": True,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.7,
    "grid.linestyle": "-",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "text.color": INK,
    "lines.linewidth": 1.6,
    "lines.solid_capstyle": "round",
    "lines.solid_joinstyle": "round",
    "legend.frameon": False,
    "legend.fontsize": 8,
    "font.size": 9,
}


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def stand_curves(series: list[tuple[str, list]], path: Path) -> None:
    """Thrust-stand sweeps; ``series`` is [(label, [StandRow, ...]), ...]."""
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.0))
        panels = (
            (axes[0, 0], "Thrust", "Motor output [%]", "Thrust [gf]"),
            (axes[0, 1], "Supply current", "Motor output [%]", "Current [A]"),
            (axes[1, 0], "Specific thrust", "Thrust [gf]", "Specific thrust [gf/W]"),
            (axes[1, 1], "Rotor speed", "Motor output [%]", "Speed [rpm]"),
        )
        for i, (label, rows) in enumerate(series):
            duty = np.array([100 * r.duty for r in rows])
            thrust = np.array([units.from_si(r.thrust, "gf") for r in rows])
            current = np.array([r.current for r in rows])
            rpm = np.array([units.from_si(r.omega, "rpm") for r in rows])
            mask = np.array([r.p_elec > 1.0 for r in rows])
            g_per_w = np.array([units.from_si(r.specific_thrust, "gf/W") for r in rows])
            color = SERIES[i]
            axes[0, 0].plot(duty, thrust, color=color, label=label)
            axes[0, 1].plot(duty, current, color=color)
            axes[1, 0].plot(thrust[mask], g_per_w[mask], color=color)
            axes[1, 1].plot(duty, rpm, color=color)
        for ax, title, xlabel, ylabel in panels:
            ax.set_title(title)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.set_ylim(bottom=0)
        axes[0, 0].legend(title="Supply", title_fontsize=8, loc="upper left")
        fig.tight_layout()
        _save(fig, path)


def endurance(run, v_min: float, reserve: float, path: Path) -> None:
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.5), sharex=True)
        t_min = run.t / 60.0
        end = run.endurance / 60.0
        panels = (
            (axes[0], run.v_cell, "Loaded cell voltage at the ESC", "Voltage [V]", v_min, f"limit {v_min:.2f} V"),
            (axes[1], 100 * run.soc, "State of charge", "SoC [%]", 100 * reserve, f"reserve {100 * reserve:.0f} %"),
            (axes[2], run.i_bus, "Total supply current", "Current [A]", None, ""),
        )
        for ax, y, title, ylabel, ref, ref_label in panels:
            ax.plot(t_min, y, color=SERIES[0])
            ax.set_title(title)
            ax.set_ylabel(ylabel)
            if ref is not None:
                ax.axhline(ref, color=INK_2, linewidth=0.9)
                ax.annotate(ref_label, (t_min[0], ref), xytext=(2, 3), textcoords="offset points", color=INK_2, fontsize=8)
            ax.axvline(end, color=MUTED, linewidth=0.9)
        axes[0].annotate(
            f"end {end:.1f} min", (end, 1), xycoords=("data", "axes fraction"), xytext=(-3, -10),
            textcoords="offset points", ha="right", color=INK_2, fontsize=8,
        )
        axes[2].set_xlabel("Hover time [min]")
        axes[2].set_ylim(bottom=0)
        fig.tight_layout()
        _save(fig, path)


def histograms(panels: list[dict], path: Path) -> None:
    """Monte Carlo output distributions with requirement limits.

    Each panel: values, title, unit, limit, nominal."""
    cols = 3
    rows = int(np.ceil(len(panels) / cols))
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(rows, cols, figsize=(9.0, 2.6 * rows), squeeze=False)
        for ax, panel in zip(axes.flat, panels):
            values = panel["values"][np.isfinite(panel["values"])]
            ax.hist(values, bins=30, color=SERIES[0], edgecolor=SURFACE, linewidth=1.0)
            ax.axvline(panel["limit"], color=INK, linewidth=1.2)
            ax.annotate("limit", (panel["limit"], 1), xycoords=("data", "axes fraction"), xytext=(3, -10),
                        textcoords="offset points", color=INK, fontsize=8)
            ax.axvline(panel["nominal"], color=MUTED, linewidth=0.9)
            ax.set_title(panel["title"], fontsize=9)
            ax.set_xlabel(panel["unit"])
            ax.grid(axis="x", visible=False)
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
        for ax in list(axes.flat)[len(panels):]:
            ax.set_visible(False)
        fig.text(0.01, -0.01, "Black line: requirement limit. Grey line: nominal design.", color=INK_2, fontsize=8)
        fig.tight_layout()
        _save(fig, path)


def tornado(bars: list, nominal: float, title: str, unit: str, path: Path, top: int = 10) -> None:
    bars = [b for b in bars if np.isfinite(b.span) and b.span > 0][:top][::-1]
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.5, 0.34 * len(bars) + 1.2))
        y = np.arange(len(bars))
        lows = np.array([b.low for b in bars]) - nominal
        highs = np.array([b.high for b in bars]) - nominal
        ax.barh(y + 0.18, lows, height=0.34, left=nominal, color=SERIES[0], label="input at -1 sigma")
        ax.barh(y - 0.18, highs, height=0.34, left=nominal, color=SERIES[1], label="input at +1 sigma")
        ax.axvline(nominal, color=INK_2, linewidth=0.9)
        ax.set_yticks(y, [b.key for b in bars], fontsize=8)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel(unit)
        ax.set_title(title)
        ax.legend(loc="lower right")
        fig.tight_layout()
        _save(fig, path)


def _outline(item: MassItem, dims: tuple[int, int]) -> np.ndarray | None:
    """2D convex outline of a part projected onto two body axes."""
    shape = item.shape
    if isinstance(shape, BoxShape):
        half = np.array([shape.lx, shape.ly, shape.lz]) / 2
        local = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * half
    elif isinstance(shape, CylinderShape):
        a = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        ring = np.column_stack([shape.radius * np.cos(a), shape.radius * np.sin(a)])
        local = np.vstack([np.column_stack([ring, np.full(32, z)]) for z in (-shape.height / 2, shape.height / 2)])
    else:
        return None
    pts = (item.rotation @ local.T).T + item.position
    pts2 = pts[:, dims]
    hull = ConvexHull(pts2)
    return pts2[hull.vertices]


def layout(items: list[MassItem], cg: np.ndarray, thrust_centre: np.ndarray, rotor_positions, prop_radius, path: Path) -> None:
    """Top and side views. Top: y right, x forward (up the page). Side: x forward, up = -z."""
    mm = 1000.0
    with plt.rc_context(STYLE):
        fig, (top, side) = plt.subplots(1, 2, figsize=(10.0, 5.2), gridspec_kw={"width_ratios": [1.0, 1.2]})
        for pos in rotor_positions:
            top.add_patch(Circle((pos[1] * mm, pos[0] * mm), prop_radius * mm, fill=False, color=BASELINE, linewidth=0.8))
        seen = set()
        for item in sorted(items, key=lambda i: i.group != "frame"):
            color = GROUP_COLORS.get(item.group, INK_2)
            label = item.group if item.group not in seen else None
            seen.add(item.group)
            for ax, dims, sign in ((top, (1, 0), (1, 1)), (side, (0, 2), (1, -1))):
                outline = _outline(item, dims)
                if outline is None:
                    ax.plot(sign[0] * item.position[dims[0]] * mm, sign[1] * item.position[dims[1]] * mm, "o",
                            color=color, markersize=4, label=label if ax is top else None)
                else:
                    xy = outline * mm * np.array(sign)
                    ax.add_patch(Polygon(xy, closed=True, facecolor=color, alpha=0.25, edgecolor=color,
                                         linewidth=0.8, label=label if ax is top else None))
        for ax, dims, sign in ((top, (1, 0), (1, 1)), (side, (0, 2), (1, -1))):
            ax.plot(sign[0] * cg[dims[0]] * mm, sign[1] * cg[dims[1]] * mm, marker="+", color=INK, markersize=12,
                    markeredgewidth=1.6, linestyle="none", label="CG" if ax is top else None)
            ax.plot(sign[0] * thrust_centre[dims[0]] * mm, sign[1] * thrust_centre[dims[1]] * mm, marker="o",
                    markerfacecolor="none", color=INK, markersize=8, linestyle="none",
                    label="thrust centre" if ax is top else None)
            ax.set_aspect("equal")
            ax.autoscale_view()
        top.set_title("Top view")
        top.set_xlabel("y, right [mm]")
        top.set_ylabel("x, forward [mm]")
        side.set_title("Side view")
        side.set_xlabel("x, forward [mm]")
        side.set_ylabel("up (-z) [mm]")
        side.set_anchor("W")
        handles, labels = top.get_legend_handles_labels()
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        fig.legend(handles, labels, loc="lower center", ncol=len(labels), bbox_to_anchor=(0.5, 0.0))
        _save(fig, path)


def mass_breakdown(groups: list[tuple[str, float]], path: Path) -> None:
    groups = sorted(groups, key=lambda g: g[1])
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(6.5, 0.45 * len(groups) + 1.0))
        y = np.arange(len(groups))
        values = [units.from_si(m, "g") for _, m in groups]
        ax.barh(y, values, height=0.5, color=SERIES[0])
        for yi, v in zip(y, values):
            ax.annotate(f"{v:.0f} g", (v, yi), xytext=(4, 0), textcoords="offset points", va="center",
                        color=INK_2, fontsize=8)
        ax.set_yticks(y, [g for g, _ in groups])
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("Mass [g]")
        ax.set_title("Mass by group")
        ax.set_xlim(right=max(values) * 1.15)
        fig.tight_layout()
        _save(fig, path)
