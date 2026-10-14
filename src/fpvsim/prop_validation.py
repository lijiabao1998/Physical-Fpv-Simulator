"""Prop calibration and validation against cited public test data.

A validation file (data/validation/*.toml, schema ``fpvsim.validation/1``)
lists individually cited static thrust-stand points of one class of props
(e.g. 5-inch tri-blades of 4.3 inch pitch), each with its source and its
place in that source. This module

* converts every point to Ct, Cp, the figure of merit FM and the blade
  Reynolds number Re75 = Omega (0.75 R) c75 / nu, with the file's c75 for the
  whole class (so Re is a rescaled rotor speed, comparable across props);
* fits each series' trend with Re, y = level (Re / Re_ref)^exponent, by least
  squares in log-log for y = Ct and y = FM;
* combines the series of one group (the same product on the same rig) with
  equal weight, then the groups into the class: the trend exponents from all
  groups, the levels at Re_ref from the groups flagged ``level``. Each comes
  with the standard uncertainty of a new member of the class, the prediction
  standard deviation s sqrt(1 + 1/n) of n groups with sample spread s, and,
  for the levels, the file's rig-to-rig term added in quadrature;
* takes the shape of Ct and Cp over the advance ratio J from wind-tunnel
  data of similar props (``[[shape]]``), each normalised by its own static
  value and plotted over x = J / (P/D), and averages them;
* builds the class's axial curves Ct(J) = Ct_ref g_T(J / (P/D)),
  Cp(J) = Cp_ref g_P(J / (P/D)).

The result is what a generic prop of the class gets: these curves at Re_ref,
``prop.ReynoldsCorrection`` for the trend, and ``ct_scale`` and ``fm_scale``
for the spread of the class. BEMT on the (estimated) blade geometry is kept
only for how the loads change in oblique flow (rotor_ff.py, anchored to these
curves): with a single polar it cannot match the static level and the J shape
together (``calibrate_airfoil`` shows how far it gets). A measurement of the
actual prop (``fpvsim fit-prop``) replaces all of it.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

from . import units
from .atmosphere import viscosity
from .bemt import Airfoil, BladeGeometry, coefficient_curves
from .prop import PropCurves

SCHEMA = "fpvsim.validation/1"


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Point:
    series: str
    group: str
    omega: float  # rad/s
    thrust: float  # N
    torque: float | None  # N m, None when not measured or not used
    rho: float
    nu: float  # m^2/s
    diameter: float  # m
    re: float  # blade Reynolds number at 75 % radius
    at: str  # place in the source

    @property
    def n(self) -> float:
        return self.omega / (2.0 * math.pi)

    @property
    def ct(self) -> float:
        return self.thrust / (self.rho * self.n**2 * self.diameter**4)

    @property
    def cp(self) -> float | None:
        if self.torque is None:
            return None
        return 2.0 * math.pi * self.torque / (self.rho * self.n**2 * self.diameter**5)

    @property
    def fm(self) -> float | None:
        cp = self.cp
        return None if cp is None else self.ct**1.5 * math.sqrt(2.0 / math.pi) / cp


@dataclass(frozen=True)
class Series:
    id: str
    group: str
    level: bool  # used for the class level (the class's own geometry)
    tested: str
    diameter: float
    pitch: float | None
    rig: str
    source: str
    url: str
    locator: str
    density_note: str
    torque_note: str
    note: str
    points: tuple[Point, ...]
    torque_points_dropped: int  # torque readings below the series' torque_min_speed

    @property
    def has_torque(self) -> bool:
        return any(p.torque is not None for p in self.points)


@dataclass(frozen=True)
class Shape:
    """Ct and Cp over J of one prop, each divided by its static value at the same rpm."""

    id: str
    tested: str
    pitch_over_diameter: float
    source: str
    url: str
    locator: str
    static_url: str
    static_locator: str
    rpm: float
    J: np.ndarray  # with J = 0 (the static value) first
    ct_ratio: np.ndarray
    cp_ratio: np.ndarray

    @property
    def x(self) -> np.ndarray:
        return self.J / self.pitch_over_diameter


@dataclass(frozen=True)
class ValidationSet:
    path: Path
    id: str
    name: str
    description: str
    retrieved: str  # when the sources were read
    re_ref: float
    chord75: float  # m
    rig_u_rel: float
    rig_note: str
    series: tuple[Series, ...]
    shapes: tuple[Shape, ...]
    excluded: tuple[dict, ...]

    @property
    def points(self) -> list[Point]:
        return [p for s in self.series for p in s.points]

    def group_level(self, group: str) -> bool:
        flags = {s.level for s in self.series if s.group == group}
        if len(flags) != 1:
            raise ValidationError(f"{self.path}: group {group} mixes level = true and false")
        return flags.pop()


def _quantity(where: str, entry) -> float:
    if not isinstance(entry, dict) or "value" not in entry or "unit" not in entry:
        raise ValidationError(f"{where}: needs {{ value, unit }}")
    return units.to_si(float(entry["value"]), entry["unit"])


def load_validation(path: str | Path) -> ValidationSet:
    path = Path(path).resolve()
    with path.open("rb") as f:
        data = tomllib.load(f)
    if data.get("schema") != SCHEMA:
        raise ValidationError(f"{path}: schema must be {SCHEMA!r}")
    meta = data.get("meta", {})
    for key in ("id", "name", "re_ref", "chord75", "rig_u_rel"):
        if key not in meta:
            raise ValidationError(f"{path}: [meta] needs {key}")
    chord75 = _quantity(f"{path}: meta.chord75", meta["chord75"])
    series = []
    seen = set()
    for i, s in enumerate(data.get("series", [])):
        where = f"{path}: series[{i}]"
        for key in ("id", "group", "level", "tested", "diameter", "blades", "rig", "density", "temperature",
                    "source", "url", "locator", "speed_unit", "thrust_unit", "points"):
            if key not in s:
                raise ValidationError(f"{where} needs {key}")
        if s["id"] in seen:
            raise ValidationError(f"{where}: duplicate id {s['id']}")
        seen.add(s["id"])
        diameter = _quantity(f"{where}.diameter", s["diameter"])
        rho = _quantity(f"{where}.density", s["density"])
        nu = viscosity(_quantity(f"{where}.temperature", s["temperature"])) / rho
        min_speed = units.to_si(float(s.get("torque_min_speed", 0.0)), s["speed_unit"])
        points = []
        dropped = 0
        for j, p in enumerate(s["points"]):
            for key in ("speed", "thrust", "at"):
                if key not in p:
                    raise ValidationError(f"{where}.points[{j}] needs {key}")
            omega = units.to_si(float(p["speed"]), s["speed_unit"])
            torque = None
            if "torque" in p:
                if "torque_unit" not in s:
                    raise ValidationError(f"{where} needs torque_unit")
                if omega >= min_speed:
                    torque = units.to_si(float(p["torque"]), s["torque_unit"])
                else:
                    dropped += 1
            points.append(Point(
                series=s["id"], group=s["group"], omega=omega, thrust=units.to_si(float(p["thrust"]), s["thrust_unit"]),
                torque=torque, rho=rho, nu=nu, diameter=diameter,
                re=omega * 0.75 * 0.5 * diameter * chord75 / nu, at=str(p["at"])))
        if len(points) < 2:
            raise ValidationError(f"{where}: needs at least two points for a trend")
        series.append(Series(
            id=s["id"], group=s["group"], level=bool(s["level"]), tested=s["tested"], diameter=diameter,
            pitch=_quantity(f"{where}.pitch", s["pitch"]) if "pitch" in s else None, rig=s["rig"], source=s["source"],
            url=s["url"], locator=s["locator"], density_note=str(s["density"].get("note", "")),
            torque_note=str(s.get("torque_note", "")), note=str(s.get("note", "")), points=tuple(points),
            torque_points_dropped=dropped))
    if not series:
        raise ValidationError(f"{path}: no [[series]]")
    shapes = []
    for i, sh in enumerate(data.get("shape", [])):
        where = f"{path}: shape[{i}]"
        for key in ("id", "tested", "diameter", "pitch", "source", "url", "locator", "static_url", "static_locator",
                    "rpm", "static", "points"):
            if key not in sh:
                raise ValidationError(f"{where} needs {key}")
        rows = sorted(sh["static"], key=lambda r: r["rpm"])
        rpm = float(sh["rpm"])
        if not rows[0]["rpm"] <= rpm <= rows[-1]["rpm"]:
            raise ValidationError(f"{where}: the static rows must bracket rpm {rpm}")
        ct0 = float(np.interp(rpm, [r["rpm"] for r in rows], [r["ct"] for r in rows]))
        cp0 = float(np.interp(rpm, [r["rpm"] for r in rows], [r["cp"] for r in rows]))
        pts = sorted(sh["points"], key=lambda r: r["J"])
        shapes.append(Shape(
            id=sh["id"], tested=sh["tested"],
            pitch_over_diameter=_quantity(f"{where}.pitch", sh["pitch"]) / _quantity(f"{where}.diameter", sh["diameter"]),
            source=sh["source"], url=sh["url"], locator=sh["locator"], static_url=sh["static_url"],
            static_locator=sh["static_locator"], rpm=rpm,
            J=np.array([0.0] + [float(r["J"]) for r in pts]),
            ct_ratio=np.array([1.0] + [float(r["ct"]) / ct0 for r in pts]),
            cp_ratio=np.array([1.0] + [float(r["cp"]) / cp0 for r in pts])))
    vset = ValidationSet(path=path, id=str(meta["id"]), name=str(meta["name"]), description=str(meta.get("description", "")),
                         retrieved=str(meta.get("retrieved", "")), re_ref=float(meta["re_ref"]), chord75=chord75, rig_u_rel=float(meta["rig_u_rel"]),
                         rig_note=str(meta.get("rig_note", "")), series=tuple(series), shapes=tuple(shapes),
                         excluded=tuple(data.get("excluded", [])))
    for g in {s.group for s in series}:
        vset.group_level(g)
    return vset


# ---------------------------------------------------------------------- fits


@dataclass(frozen=True)
class Trend:
    """y = level (Re / Re_ref)^exponent."""

    level: float
    exponent: float
    n: int  # points (series) or series (group)
    re_min: float
    re_max: float

    def at(self, re: float, re_ref: float) -> float:
        return self.level * (re / re_ref) ** self.exponent


def series_trend(points: list[Point], key: str, re_ref: float) -> Trend:
    """Least squares of log y on log(Re / Re_ref) over one series' points."""
    pts = [p for p in points if getattr(p, key) is not None]
    if len(pts) < 2:
        raise ValidationError(f"{key}: a trend needs at least two points")
    x = np.log([p.re / re_ref for p in pts])
    y = np.log([getattr(p, key) for p in pts])
    slope, intercept = np.polyfit(x, y, 1)
    return Trend(float(math.exp(intercept)), float(slope), len(pts), min(p.re for p in pts), max(p.re for p in pts))


def group_trends(vset: ValidationSet, key: str) -> dict[str, Trend]:
    """Per group (the same product on the same rig): the mean of its series' log
    levels and exponents, each series weighted equally."""
    out = {}
    for group in dict.fromkeys(s.group for s in vset.series):
        trends = [series_trend(list(s.points), key, vset.re_ref) for s in vset.series
                  if s.group == group and sum(1 for p in s.points if getattr(p, key) is not None) >= 2]
        if not trends:
            continue
        out[group] = Trend(float(math.exp(np.mean([math.log(t.level) for t in trends]))),
                           float(np.mean([t.exponent for t in trends])), len(trends),
                           min(t.re_min for t in trends), max(t.re_max for t in trends))
    return out


def _predictive_sd(values) -> float:
    """Standard uncertainty of a new member of a class seen through n samples: s sqrt(1 + 1/n)."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        raise ValidationError("the class spread needs at least two groups")
    return float(np.std(v, ddof=1) * math.sqrt(1.0 + 1.0 / len(v)))


@dataclass(frozen=True)
class ClassFit:
    re_ref: float
    re_min: float  # range of the data behind the Ct trend (thrust readings)
    re_max: float
    fm_re_min: float  # range of the data behind the FM trend (thrust and torque readings)
    fm_re_max: float
    ct_level: float
    ct_level_u_rel: float
    fm_level: float
    fm_level_u_rel: float
    ct_exponent: float
    ct_exponent_u: float
    fm_exponent: float
    fm_exponent_u: float
    ct_groups: dict
    fm_groups: dict
    level_groups: tuple[str, ...]

    @property
    def cp_level(self) -> float:
        return self.ct_level**1.5 * math.sqrt(2.0 / math.pi) / self.fm_level

    def band(self, key: str, re: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Nominal and +-1 sigma of the class value of ``key`` (ct, fm or cp) at
        ``re`` (each power law clipped to its data range): level and exponent
        errors combined in log space, taken as independent (they nearly are,
        because Re_ref is at the centre of the data, and Ct and FM are sampled
        independently); log Cp = 1.5 log Ct - log FM + const."""
        x_t = np.log(np.clip(re, self.re_min, self.re_max) / self.re_ref)
        x_f = np.log(np.clip(re, self.fm_re_min, self.fm_re_max) / self.re_ref)
        var_t = self.ct_level_u_rel**2 + (self.ct_exponent_u * x_t) ** 2
        var_f = self.fm_level_u_rel**2 + (self.fm_exponent_u * x_f) ** 2
        if key == "ct":
            nominal, u = self.ct_level * np.exp(self.ct_exponent * x_t), np.sqrt(var_t)
        elif key == "fm":
            nominal, u = self.fm_level * np.exp(self.fm_exponent * x_f), np.sqrt(var_f)
        elif key == "cp":
            nominal = self.cp_level * np.exp(1.5 * self.ct_exponent * x_t - self.fm_exponent * x_f)
            u = np.sqrt(2.25 * var_t + var_f)
        else:
            raise KeyError(key)
        return nominal, nominal * np.exp(-u), nominal * np.exp(u)


def fit_class(vset: ValidationSet) -> ClassFit:
    ct_groups = group_trends(vset, "ct")
    fm_groups = group_trends(vset, "fm")
    level_ct = {g: t for g, t in ct_groups.items() if vset.group_level(g)}
    level_fm = {g: t for g, t in fm_groups.items() if vset.group_level(g)}
    ct_logs = [math.log(t.level) for t in level_ct.values()]
    fm_logs = [math.log(t.level) for t in level_fm.values()]
    rig = vset.rig_u_rel
    pts = vset.points
    torque = [p for p in pts if p.torque is not None]
    return ClassFit(
        re_ref=vset.re_ref,
        re_min=min(p.re for p in pts),
        re_max=max(p.re for p in pts),
        fm_re_min=min(p.re for p in torque),
        fm_re_max=max(p.re for p in torque),
        ct_level=float(math.exp(np.mean(ct_logs))),
        ct_level_u_rel=math.hypot(_predictive_sd(ct_logs), rig),
        fm_level=float(math.exp(np.mean(fm_logs))),
        fm_level_u_rel=math.hypot(_predictive_sd(fm_logs), rig),
        ct_exponent=float(np.mean([t.exponent for t in ct_groups.values()])),
        ct_exponent_u=_predictive_sd([t.exponent for t in ct_groups.values()]),
        fm_exponent=float(np.mean([t.exponent for t in fm_groups.values()])),
        fm_exponent_u=_predictive_sd([t.exponent for t in fm_groups.values()]),
        ct_groups=ct_groups,
        fm_groups=fm_groups,
        level_groups=tuple(level_ct),
    )


# ------------------------------------------------------------ J shape


def class_shape(vset: ValidationSet, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Mean normalised Ct and Cp over x = J / (P/D) of the [[shape]] props, and
    half their spread (max - min) / 2. Defined up to the smallest of their
    largest x."""
    if not vset.shapes:
        raise ValidationError(f"{vset.path}: no [[shape]] data for the J dependence")
    x = np.asarray(x, dtype=float)
    x_max = min(float(s.x[-1]) for s in vset.shapes)
    if x[-1] > x_max + 1e-9:
        raise ValidationError(f"J / (P/D) = {x[-1]:.3f} is beyond the shape data ({x_max:.3f})")
    ct = np.array([np.interp(x, s.x, s.ct_ratio) for s in vset.shapes])
    cp = np.array([np.interp(x, s.x, s.cp_ratio) for s in vset.shapes])
    return ct.mean(axis=0), cp.mean(axis=0), 0.5 * np.ptp(ct, axis=0), 0.5 * np.ptp(cp, axis=0)


def class_curves(fit: "ClassFit", vset: ValidationSet, pitch_over_diameter: float, J: np.ndarray) -> PropCurves:
    """The class's axial curves at Re_ref: static level times the J shape."""
    g_t, g_p, _, _ = class_shape(vset, np.asarray(J, dtype=float) / pitch_over_diameter)
    return PropCurves(np.asarray(J, dtype=float), fit.ct_level * g_t, fit.cp_level * g_p)


# ------------------------------------------------------------- calibration


def static_coefficients(geom: BladeGeometry, foil: Airfoil) -> tuple[float, float]:
    """BEMT static Ct and Cp."""
    curves = coefficient_curves(geom, foil, np.array([0.0]))
    return float(curves.ct[0]), float(curves.cp[0])


def calibrate_airfoil(geom: BladeGeometry, foil: Airfoil, ct0: float, fm0: float) -> Airfoil:
    """Effective lift slope and minimum drag coefficient with which BEMT gives the
    static Ct ``ct0`` and figure of merit ``fm0``. The other polar parameters
    (zero-lift angle, stall limits, drag-polar curvature) stay as given. Used in
    the validation report to show what BEMT would need: the J shape it then
    gives is compared with the data."""
    cp_target = ct0**1.5 * math.sqrt(2.0 / math.pi) / fm0

    def residual(x):  # in logs, so both stay positive
        trial = replace(foil, cl_alpha=math.exp(x[0]), cd_min=math.exp(x[1]))
        ct, cp = static_coefficients(geom, trial)
        return [math.log(ct / ct0), math.log(cp / cp_target)]

    x, info, ier, msg = fsolve(residual, [math.log(foil.cl_alpha), math.log(foil.cd_min)], full_output=True, xtol=1e-12)
    if ier != 1 or max(abs(r) for r in residual(x)) > 1e-8:
        raise ValidationError(f"polar calibration did not converge: {msg}")
    return replace(foil, cl_alpha=math.exp(x[0]), cd_min=math.exp(x[1]))


# ------------------------------------------------------------ model vs data


def model_values(prop, re: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The prop model's static Ct, Cp and FM at blade Reynolds numbers ``re``
    (defined with the prop's own chord, so this is the model as it would be
    evaluated at those Reynolds numbers)."""
    ct = np.empty(len(re))
    cp = np.empty(len(re))
    rc = prop.reynolds
    for i, r in enumerate(re):
        f_t, f_p = (1.0, 1.0) if rc is None else rc.factors(float(r))
        ct[i], cp[i] = prop.ct0 * f_t, prop.cp0 * f_p
    return ct, cp, ct**1.5 * math.sqrt(2.0 / math.pi) / cp


def residuals(vset: ValidationSet, prop) -> dict[str, dict[str, float]]:
    """Per group: mean log ratio data / model for Ct and FM (``nan`` without torque)."""
    out = {}
    for group in dict.fromkeys(s.group for s in vset.series):
        pts = [p for p in vset.points if p.group == group]
        re = np.array([p.re for p in pts])
        ct_m, _, fm_m = model_values(prop, re)
        ct_r = [math.log(p.ct / m) for p, m in zip(pts, ct_m)]
        fm_r = [math.log(p.fm / m) for p, m in zip(pts, fm_m) if p.fm is not None]
        out[group] = {"ct": float(np.mean(ct_r)), "fm": float(np.mean(fm_r)) if fm_r else float("nan"),
                      "n_ct": len(ct_r), "n_fm": len(fm_r)}
    return out


# ------------------------------------------------- the prop file against the fit


@dataclass(frozen=True)
class Check:
    name: str
    fitted: float
    in_file: float
    tolerance: float
    relative: bool

    @property
    def ok(self) -> bool:
        if self.relative:
            return abs(self.in_file / self.fitted - 1.0) <= self.tolerance
        return abs(self.in_file - self.fitted) <= self.tolerance


def consistency(build, fit: ClassFit, vset: ValidationSet) -> list[Check]:
    """Does the prop component file carry what the fit gives (to its rounding)?
    ``build`` is a design.Build whose prop is a generic prop of this class."""
    params = build.params
    curves = build.prop_curves
    pd = params["prop.pitch"].value / params["prop.diameter"].value
    expected = class_curves(fit, vset, pd, curves.J)
    ct0, cp0 = float(curves.ct[0]), float(curves.cp[0])
    checks = [
        Check("Ct(J = 0)", fit.ct_level, ct0, 0.002, True),
        Check("FM(J = 0)", fit.fm_level, ct0**1.5 * math.sqrt(2.0 / math.pi) / cp0, 0.002, True),
        Check("max |ΔCt(J)|", 0.0, float(np.max(np.abs(curves.ct - expected.ct))), 1e-4, False),
        Check("max |ΔCp(J)|", 0.0, float(np.max(np.abs(curves.cp - expected.cp))), 1e-4, False),
        Check("Ct 不確定度", fit.ct_level_u_rel, params["prop.ct_scale"].u, 0.001, False),
        Check("FM 不確定度", fit.fm_level_u_rel, params["prop.fm_scale"].u, 0.001, False),
    ]
    if build.prop_reynolds is not None:
        chord, re_ref, re_min, re_max, fm_re_min, fm_re_max = build.prop_reynolds
        checks += [
            Check("Re 的弦長 c75", vset.chord75, chord, 1e-9, False),
            Check("Re_ref", vset.re_ref, re_ref, 1e-9, True),
            Check("Ct 的 Re 下限", fit.re_min, re_min, 0.005, True),
            Check("Ct 的 Re 上限", fit.re_max, re_max, 0.005, True),
            Check("FM 的 Re 下限", fit.fm_re_min, fm_re_min, 0.005, True),
            Check("FM 的 Re 上限", fit.fm_re_max, fm_re_max, 0.005, True),
            Check("Ct 指數", fit.ct_exponent, params["prop.re_ct_exponent"].value, 0.001, False),
            Check("Ct 指數不確定度", fit.ct_exponent_u, params["prop.re_ct_exponent"].u, 0.001, False),
            Check("FM 指數", fit.fm_exponent, params["prop.re_fm_exponent"].value, 0.001, False),
            Check("FM 指數不確定度", fit.fm_exponent_u, params["prop.re_fm_exponent"].u, 0.001, False),
        ]
    return checks
