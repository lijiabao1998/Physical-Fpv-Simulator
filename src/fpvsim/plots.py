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
GROUP_COLORS = {
    "propulsion": SERIES[0],
    "battery": SERIES[1],
    "avionics": SERIES[2],
    "payload": SERIES[3],
    "frame": MUTED,
    "misc": INK_2,
}

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


def burst(result, v_limit: float, t_limit_c: float, path: Path) -> None:
    """Full-throttle burst from a full pack: cell voltage, pack temperature, current."""
    tr = np.array(result.trace) if result.trace else np.zeros((0, 5))
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.0), sharex=True)
        panels = (
            (axes[0], tr[:, 1], "Loaded cell voltage at the ESC", "Voltage [V]", v_limit, f"burst limit {v_limit:.2f} V"),
            (axes[1], tr[:, 2] - 273.15, "Pack temperature", "Temperature [°C]", t_limit_c, f"limit {t_limit_c:.0f} °C"),
            (axes[2], tr[:, 4], "Total supply current", "Current [A]", None, ""),
        )
        for ax, y, title, ylabel, ref, ref_label in panels:
            ax.plot(tr[:, 0], y, color=SERIES[0])
            ax.set_title(title)
            ax.set_ylabel(ylabel)
            if ref is not None:
                ax.axhline(ref, color=INK_2, linewidth=0.9)
                ax.annotate(ref_label, (0, ref), xycoords=("axes fraction", "data"), xytext=(2, 3),
                            textcoords="offset points", color=INK_2, fontsize=8)
            ax.axvline(result.duration, color=MUTED, linewidth=0.9)
        axes[2].set_xlabel("Time at full throttle [s]")
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


# ---------------------------------------------------------------- flight logs

_SEQUENTIAL = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")


def timeseries(panels: list[dict], path: Path, width: float = 8.0, panel_height: float = 1.9, xlabel: str = "Time [s]") -> None:
    """Stacked time-series panels sharing the time axis.

    Each panel: title, ylabel, series [(label, t, y)], optional refs
    [(value, label)] drawn as reference lines and optional ylim."""
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(len(panels), 1, figsize=(width, panel_height * len(panels) + 0.4), sharex=True, squeeze=False)
        for ax, panel in zip(axes[:, 0], panels):
            series = panel["series"]
            for i, (label, t, y) in enumerate(series):
                ax.plot(t, y, color=SERIES[i % len(SERIES)] if len(series) > 1 or not panel.get("muted") else MUTED,
                        linewidth=1.2, label=label)
            for value, label in panel.get("refs", []):
                ax.axhline(value, color=INK_2, linewidth=0.9)
                ax.annotate(label, (1, value), xycoords=("axes fraction", "data"), xytext=(-3, 3),
                            textcoords="offset points", ha="right", color=INK_2, fontsize=8)
            if "ylim" in panel:
                ax.set_ylim(*panel["ylim"])
            ax.set_title(panel["title"])
            ax.set_ylabel(panel["ylabel"])
            if len(series) > 1:
                ax.legend(loc="upper right", ncol=min(len(series), 4))
        axes[-1, 0].set_xlabel(xlabel)
        fig.tight_layout()
        _save(fig, path)


def trajectory(t, north, east, alt, path: Path) -> None:
    with plt.rc_context(STYLE):
        fig, (top, side) = plt.subplots(1, 2, figsize=(9.0, 3.8), gridspec_kw={"width_ratios": [1.0, 1.4]})
        top.plot(east, north, color=SERIES[0])
        top.plot(east[0], north[0], "o", color=INK, markersize=6, label="start")
        top.plot(east[-1], north[-1], "s", color=INK, markersize=6, markerfacecolor="none", label="end")
        top.set_aspect("equal", adjustable="datalim")
        top.set_title("Ground track")
        top.set_xlabel("East [m]")
        top.set_ylabel("North [m]")
        top.legend(loc="best")
        side.plot(t, alt, color=SERIES[0])
        side.set_title("Altitude")
        side.set_xlabel("Time [s]")
        side.set_ylabel("Altitude [m]")
        fig.tight_layout()
        _save(fig, path)


# ------------------------------------------------------------------- tuning

def throttle_noise_map(tmap, path: Path, title: str, fmax: float) -> None:
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("seq", _SEQUENTIAL)
    cmap.set_bad(SURFACE)
    keep = tmap.freqs <= fmax
    rows = tmap.frames > 0
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.0, 3.8))
        data = np.ma.masked_invalid(tmap.power_db[:, keep])
        finite = data.compressed()
        vmin, vmax = (np.percentile(finite, 5), np.percentile(finite, 99.5)) if finite.size else (None, None)
        lo, hi = tmap.throttle[rows].min() - 2.5, tmap.throttle[rows].max() + 2.5
        im = ax.imshow(data, origin="lower", aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax,
                       extent=(0, tmap.freqs[keep][-1], tmap.throttle[0] - 2.5, tmap.throttle[-1] + 2.5))
        ax.set_ylim(lo, hi)
        ax.grid(False)
        ax.set_title(title)
        ax.set_xlabel("Frequency [Hz]")
        ax.set_ylabel("Throttle (motor output) [%]")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("PSD [dB re (deg/s)²/Hz]", color=INK_2)
        cb.outline.set_visible(False)
        fig.tight_layout()
        _save(fig, path)


def spectra(panels: list[dict], path: Path, fmax: float) -> None:
    """PSD panels; each: title, ylabel, series [(label, f, p, style)] with
    style 'raw' drawn muted."""
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(len(panels), 1, figsize=(8.0, 2.8 * len(panels)), squeeze=False)
        for ax, panel in zip(axes[:, 0], panels):
            k = 0
            for label, f, p, style in panel["series"]:
                keep = (f > 0) & (f <= fmax)
                db = 10 * np.log10(np.maximum(p[keep], 1e-12))
                if style == "raw":
                    ax.plot(f[keep], db, color=BASELINE, linewidth=1.0, label=label)
                else:
                    ax.plot(f[keep], db, color=SERIES[k], linewidth=1.2, label=label)
                    k += 1
            ax.set_title(panel["title"])
            ax.set_ylabel(panel["ylabel"])
            ax.set_xlabel("Frequency [Hz]")
            ax.legend(loc="upper right")
        fig.tight_layout()
        _save(fig, path)


def bode(chains: list[tuple[str, np.ndarray, np.ndarray]], f: np.ndarray, path: Path) -> None:
    """Low-pass chains: magnitude and group delay. chains = [(label, h, delay_s)]."""
    with plt.rc_context(STYLE):
        fig, (mag, dly) = plt.subplots(2, 1, figsize=(8.0, 5.4), sharex=True)
        for i, (label, h, delay) in enumerate(chains):
            mag.semilogx(f, 20 * np.log10(np.abs(h)), color=SERIES[i], label=label)
            dly.semilogx(f, 1000 * delay, color=SERIES[i], label=label)
        mag.set_title("Filter magnitude")
        mag.set_ylabel("Gain [dB]")
        mag.set_ylim(-30, 3)
        mag.legend(loc="lower left")
        dly.set_title("Filter group delay")
        dly.set_ylabel("Delay [ms]")
        dly.set_xlabel("Frequency [Hz]")
        dly.set_ylim(bottom=0)
        fig.tight_layout()
        _save(fig, path)


def pareto(points: list[dict], path: Path, xlabel: str, ylabel: str) -> None:
    """points: label, x, y, feasible, highlight ('recommended'/'baseline'/None)."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        for feasible, color, name in ((True, SERIES[0], "meets constraints"), (False, MUTED, "fails a constraint")):
            pts = [p for p in points if p["feasible"] == feasible]
            if pts:
                ax.scatter([p["x"] for p in pts], [p["y"] for p in pts], s=48,
                           facecolors=color if feasible else "none", edgecolors=color, linewidths=1.4,
                           label=name, zorder=3)
        for p in points:
            if p.get("highlight"):
                ax.scatter([p["x"]], [p["y"]], s=150, facecolors="none", edgecolors=SERIES[1] if p["highlight"] == "recommended" else INK,
                           linewidths=1.8, zorder=4)
                ax.annotate(f"{p['highlight']}: {p['label']}", (p["x"], p["y"]), xytext=(8, 6), textcoords="offset points",
                            color=INK, fontsize=8)
        ax.set_xscale("log")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title("Gain sweep: tracking error vs motor-output noise")
        ax.legend(loc="upper right")
        fig.tight_layout()
        _save(fig, path)


def step_compare(axes_data: list[dict], path: Path) -> None:
    """axes_data: title, series [(label, t, mean, std)]."""
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, len(axes_data), figsize=(10.0, 3.4), sharey=True, squeeze=False)
        for ax, panel in zip(axes[0], axes_data):
            for i, (label, t, mean, std) in enumerate(panel["series"]):
                tm = 1000 * np.asarray(t)
                ax.fill_between(tm, mean - std, mean + std, color=SERIES[i], alpha=0.10, linewidth=0)
                ax.plot(tm, mean, color=SERIES[i], label=label)
            ax.axhline(1.0, color=INK_2, linewidth=0.8)
            ax.set_title(panel["title"])
            ax.set_xlabel("Time [ms]")
        axes[0, 0].set_ylabel("Response (setpoint step = 1)")
        axes[0, 0].set_ylim(-0.25, 1.6)  # a wide early band (yaw) must not flatten the curves
        axes[0, 0].legend(loc="lower right")
        fig.tight_layout()
        _save(fig, path)


# ------------------------------------------------------------- comparisons

def delta_intervals(rows: list[dict], versions: list[str], path: Path) -> None:
    """Paired relative differences against the base.

    rows: label, and per version a (p5, p50, p95) tuple in percent."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.0, 0.55 * len(rows) * max(1, len(versions)) ** 0.5 + 1.4))
        n = len(versions)
        offsets = np.linspace(-0.18, 0.18, n) if n > 1 else [0.0]
        for i, version in enumerate(versions):
            ys, lo, mid, hi = [], [], [], []
            for k, row in enumerate(rows):
                p5, p50, p95 = row[version]
                ys.append(len(rows) - 1 - k + offsets[i])
                lo.append(p5)
                mid.append(p50)
                hi.append(p95)
            ax.hlines(ys, lo, hi, color=SERIES[i], linewidth=2.0)
            ax.plot(mid, ys, "o", color=SERIES[i], markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5,
                    label=version)
        ax.axvline(0.0, color=INK_2, linewidth=0.9)
        ax.set_yticks(range(len(rows)), [r["label"] for r in rows][::-1])
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("Change against the base design [%] (dot: median, bar: 5th-95th percentile, paired samples)")
        ax.set_title("What the change does, with its uncertainty")
        ax.legend(loc="lower right")
        fig.tight_layout()
        _save(fig, path)


def side_views(versions: list[dict], path: Path) -> None:
    """One side view per version: label, items, cg, thrust_centre, prop_z."""
    mm = 1000.0
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, len(versions), figsize=(4.2 * len(versions), 3.6), sharey=True, squeeze=False)
        for ax, v in zip(axes[0], versions):
            seen = set()
            for item in sorted(v["items"], key=lambda i: i.group != "frame"):
                color = GROUP_COLORS.get(item.group, INK_2)
                label = item.group if item.group not in seen else None
                seen.add(item.group)
                outline = _outline(item, (0, 2))
                if outline is None:
                    ax.plot(item.position[0] * mm, -item.position[2] * mm, "o", color=color, markersize=4, label=label)
                else:
                    ax.add_patch(Polygon(outline * mm * np.array((1, -1)), closed=True, facecolor=color, alpha=0.25,
                                         edgecolor=color, linewidth=0.8, label=label))
            ax.axhline(-v["prop_z"] * mm, color=BASELINE, linewidth=0.8)
            ax.annotate("prop plane", (1, -v["prop_z"] * mm), xycoords=("axes fraction", "data"), xytext=(-3, 3),
                        textcoords="offset points", ha="right", color=INK_2, fontsize=8)
            ax.plot(v["cg"][0] * mm, -v["cg"][2] * mm, marker="+", color=INK, markersize=12, markeredgewidth=1.6,
                    linestyle="none", label="CG")
            ax.plot(v["thrust_centre"][0] * mm, -v["thrust_centre"][2] * mm, marker="o", markerfacecolor="none",
                    color=INK, markersize=8, linestyle="none", label="thrust centre")
            ax.set_aspect("equal")
            ax.autoscale_view()
            ax.set_title(v["label"])
            ax.set_xlabel("x, forward [mm]")
        axes[0, 0].set_ylabel("up (-z) [mm]")
        handles, labels = [], []
        for ax in axes[0]:
            for h, l in zip(*ax.get_legend_handles_labels()):
                if l not in labels:
                    handles.append(h)
                    labels.append(l)
        fig.tight_layout(rect=(0, 0.1, 1, 1))
        fig.legend(handles, labels, loc="lower center", ncol=len(labels), bbox_to_anchor=(0.5, 0.0))
        _save(fig, path)


def xy_panels(panels: list[dict], path: Path, ncols: int = 2, panel_size: tuple[float, float] = (4.2, 3.0)) -> None:
    """Grid of x-y charts. Each panel: title, xlabel, ylabel, series [(label, x, y)] drawn as
    lines (more than four series use the sequential ramp, for an ordered parameter), optional
    points [(label, x, y)] drawn as markers (measurements), vrefs [(x, label)], refs [(y, label)]."""
    n = len(panels)
    rows = (n + ncols - 1) // ncols
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(rows, ncols, figsize=(panel_size[0] * ncols, panel_size[1] * rows), squeeze=False)
        for ax, panel in zip(axes.ravel(), panels):
            series = panel.get("series", [])
            ramp = len(series) > len(SERIES)
            for i, (label, x, y) in enumerate(series):
                color = _SEQUENTIAL[1 + int(i * (len(_SEQUENTIAL) - 2) / max(len(series) - 1, 1))] if ramp else SERIES[i % len(SERIES)]
                ax.plot(x, y, color=color, label=label)
            for i, (label, x, y) in enumerate(panel.get("points", [])):
                ax.plot(x, y, "o", color=INK if not series else SERIES[i % len(SERIES)], markersize=3.5,
                        markerfacecolor="none", label=label)
            for value, label in panel.get("vrefs", []):
                ax.axvline(value, color=INK_2, linewidth=0.9)
                ax.annotate(label, (value, 1), xycoords=("data", "axes fraction"), xytext=(3, -10),
                            textcoords="offset points", color=INK_2, fontsize=8)
            for value, label in panel.get("refs", []):
                ax.axhline(value, color=INK_2, linewidth=0.9)
                if label:
                    ax.annotate(label, (1, value), xycoords=("axes fraction", "data"), xytext=(-3, 3),
                                textcoords="offset points", ha="right", color=INK_2, fontsize=8)
            ax.set_title(panel["title"])
            ax.set_xlabel(panel.get("xlabel", ""))
            ax.set_ylabel(panel.get("ylabel", ""))
            if "ylim" in panel:
                ax.set_ylim(*panel["ylim"])
            if len(series) + len(panel.get("points", [])) > 1:
                ax.legend(loc=panel.get("legend", "best"))
        for ax in axes.ravel()[n:]:
            ax.set_visible(False)
        fig.tight_layout()
        _save(fig, path)
