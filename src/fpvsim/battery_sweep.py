"""Battery selection: the build's pack series scaled over capacity.

Choosing a pack is a trade between endurance and everything the extra mass
costs (thrust-to-weight, all-up weight, full-throttle burst, where the pack
sits). Real selection compares packs of one series (same cells, same
chemistry and build) in several capacities. Without brand data the series
is described by scaling laws from the build's own pack (capacity ratio r =
C / C0):

    capacity      C = C0 r                     (the pack's capacity error scales with it)
    mass          m = m_o + (m0 - m_o) r       m_o: wires, connector, wrap (``overhead_mass``)
    resistance    R0, R1 = R(C0) r^-n          n: ``resistance_exponent`` (1 when plate area ~ capacity)
    size          each side times r^(1/3)      (volume ~ capacity)
    convection    hA = hA0 r^(2/3)             (surface area)
    heat capacity follows the mass, the C-rating label stays per capacity

The two family parameters live in the battery file's ``[family]`` table,
with their uncertainty. The pack's bottom face (the face nearer the frame)
stays put, so a bigger pack rises; parts mounted on it (``mounted_on``, e.g.
the strap) move with its top face.

Every capacity is evaluated with the same Monte Carlo draws (the scaled
battery values are computed from each sample's base values and family
parameters), so the differences between capacities are paired, as in
compare.py; at r = 1 the result is exactly the design report's.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, replace
from typing import Mapping

import numpy as np

from .design import Build, DesignError, PartTemplate
from .mass import BoxShape
from .params import ParamSet, component_stream, parse_param
from .performance import evaluate
from .uncertainty import MonteCarloResult

FAMILY_KEYS = ("overhead_mass", "resistance_exponent")
DEFAULT_CAPACITIES = (850.0, 1050.0, 1300.0, 1550.0, 1800.0, 2200.0)  # mAh, common sizes


def _battery_part(build: Build) -> PartTemplate:
    parts = [p for p in build.parts if p.mass_key == "battery.mass"]
    if len(parts) != 1:
        raise DesignError("the build must place exactly one battery")
    return parts[0]


def family_params(build: Build) -> ParamSet:
    """The build's parameters plus the battery family's (``battery_family.*``)."""
    path = build.component_files["battery"]
    with path.open("rb") as f:
        data = tomllib.load(f)
    family = data.get("family")
    if not isinstance(family, dict):
        raise DesignError(f"{path}: needs a [family] table with {', '.join(FAMILY_KEYS)} for a capacity sweep")
    part = _battery_part(build)
    out = ParamSet(dict(build.params.params))
    for key in FAMILY_KEYS:
        if key not in family:
            raise DesignError(f"{path}: [family] needs {key}")
        stream = component_stream(part.component_id or path.stem, f"family.{key}")
        out.add(parse_param(f"battery_family.{key}", family[key], stream))
    return out


def scaled_battery(values: Mapping[str, float], ratio: float) -> dict[str, float]:
    """Battery parameter overrides at capacity ratio ``ratio`` from base values."""
    m0 = values["battery.mass"]
    overhead = min(max(values["battery_family.overhead_mass"], 0.0), m0)
    n = values["battery_family.resistance_exponent"]
    return {
        "battery.capacity": values["battery.capacity"] * ratio,
        "battery.mass": overhead + (m0 - overhead) * ratio,
        "battery.r0_cell": values["battery.r0_cell"] * ratio ** (-n),
        "battery.r1_cell": values["battery.r1_cell"] * ratio ** (-n),
        "battery.ha_hover": values["battery.ha_hover"] * ratio ** (2.0 / 3.0),
        "battery.ha_ref": values["battery.ha_ref"] * ratio ** (2.0 / 3.0),
    }


def variant_build(build: Build, ratio: float, params: ParamSet) -> Build:
    """The build with the pack resized (bottom face fixed, mounted parts following its top)."""
    part = _battery_part(build)
    shape = part.shape
    if not isinstance(shape, BoxShape):
        raise DesignError("battery sweep needs a box-shaped battery")
    s = ratio ** (1.0 / 3.0)
    new_shape = BoxShape(shape.lx * s, shape.ly * s, shape.lz * s)
    grow = new_shape.lz - shape.lz
    up = -1.0 if part.position[2] < 0.0 else 1.0  # above the frame (z < 0) the pack grows upward
    shift = np.array([0.0, 0.0, up * grow])
    parts = []
    for p in build.parts:
        if p is part:
            parts.append(replace(p, shape=new_shape, position=p.position + 0.5 * shift))
        elif p.mounted_on == part.name:
            parts.append(replace(p, position=p.position + shift))
        else:
            parts.append(p)
    return replace(build, params=params, parts=parts)


@dataclass
class SweepPoint:
    capacity: float  # C, nominal
    ratio: float
    build: Build
    nominal: dict[str, float]
    mc: MonteCarloResult
    compliance: dict[str, float]  # requirement id -> probability
    p_all: float  # probability of meeting every requirement
    size: tuple[float, float, float]  # m, pack box

    @property
    def capacity_mah(self) -> float:
        return self.capacity / 3.6


def run_sweep(build: Build, capacities_mah=DEFAULT_CAPACITIES, samples: int = 500, seed: int = 1) -> list[SweepPoint]:
    params = family_params(build)
    base_capacity = params["battery.capacity"].value
    nominal_values = params.nominal()
    inputs = params.sample(seed, samples)
    reqs = build.spec.requirements
    points = []
    for cap in capacities_mah:
        ratio = cap * 3.6 / base_capacity
        vb = variant_build(build, ratio, params)
        nominal = evaluate(vb.realize(scaled_battery(nominal_values, ratio)))
        collected: dict[str, list[float]] = {}
        for i in range(samples):
            vals = {k: float(v[i]) for k, v in inputs.items()}
            full = {**nominal_values, **vals}
            out = evaluate(vb.realize({**vals, **scaled_battery(full, ratio)}))
            for key, value in out.items():
                collected.setdefault(key, []).append(value)
        outputs = {k: np.asarray(v) for k, v in collected.items()}
        mc = MonteCarloResult(samples, seed, inputs, outputs)
        compliance = {r.id: mc.probability_of_compliance(r) for r in reqs}
        ok = np.ones(samples, dtype=bool)
        for r in reqs:
            ok &= np.array([r.passes(x) for x in outputs[r.metric]])
        part = _battery_part(vb)
        points.append(SweepPoint(cap * 3.6, ratio, vb, nominal, mc, compliance, float(ok.mean()),
                                 (part.shape.lx, part.shape.ly, part.shape.lz)))
    return points


def recommend(points: list[SweepPoint], tolerance: float = 0.02) -> SweepPoint:
    """Highest probability of meeting every requirement; among capacities within
    ``tolerance`` of it, the one with the longest median hover endurance."""
    best = max(p.p_all for p in points)
    near = [p for p in points if p.p_all >= best - tolerance]
    return max(near, key=lambda p: float(np.median(p.mc.finite("endurance"))) if len(p.mc.finite("endurance")) else -math.inf)


def binding(points: list[SweepPoint], reqs) -> dict[str, list[str]]:
    """Per capacity, the requirements with compliance below 95 %."""
    return {f"{p.capacity_mah:.0f}": [r.id for r in reqs if p.compliance[r.id] < 0.95] for p in points}

