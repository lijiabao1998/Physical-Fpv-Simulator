"""Parameters with provenance and uncertainty.

A physical parameter is never a bare number. It always carries:

* its value and the unit it was written in (stored internally in SI),
* where the number came from (``Source``) and a citation or note,
* a standard uncertainty (1 sigma, GUM convention) and a distribution.

Data files must spell all of this out; a parameter without a source is a
load error. This is what lets every report say how much each result can be
trusted and which inputs it depends on.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator, Mapping

import numpy as np

from . import units


class ParamError(ValueError):
    pass


class Source(str, Enum):
    """Where a number came from, ordered from most to least trustworthy."""

    MEASURED = "measured"  # our own measurement, with a record of how
    STANDARD = "standard"  # defined constant or standard (ISA, g0)
    NOMINAL = "nominal"  # a part's defining nominal value (cell count, label rating)
    DATASHEET = "datasheet"  # manufacturer specification
    LITERATURE = "literature"  # published paper or textbook
    DERIVED = "derived"  # computed from other parameters by a model (e.g. BEMT)
    ESTIMATE = "estimate"  # engineering estimate for the part class
    SYNTHETIC = "synthetic"  # generated data, only for verification tests

    @property
    def label_zh(self) -> str:
        return _SOURCE_ZH[self]


_SOURCE_ZH = {
    Source.MEASURED: "實測",
    Source.STANDARD: "標準值",
    Source.NOMINAL: "標稱值",
    Source.DATASHEET: "規格書",
    Source.LITERATURE: "文獻",
    Source.DERIVED: "模型推導",
    Source.ESTIMATE: "工程估計",
    Source.SYNTHETIC: "合成數據",
}

DISTRIBUTIONS = ("normal", "uniform")


@dataclass(frozen=True)
class Param:
    key: str
    value: float  # SI
    unit: str  # unit used in the data file, for display
    source: Source
    u: float = 0.0  # standard uncertainty (1 sigma), SI
    dist: str = "normal"
    ref: str = ""
    note: str = ""

    @property
    def si_unit(self) -> str:
        return units.si_unit(self.unit)

    @property
    def display_value(self) -> float:
        return units.from_si(self.value, self.unit)

    @property
    def display_u(self) -> float:
        return self.u / units.scale(self.unit)

    @property
    def u_rel(self) -> float:
        return self.u / abs(self.value) if self.value else math.inf

    @property
    def uncertain(self) -> bool:
        return self.u > 0.0

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        """Draw ``n`` samples. Positive nominal values stay positive (truncated)."""
        if not self.uncertain:
            return np.full(n, self.value)
        out = self._draw(rng, n)
        if self.value > 0.0:
            for _ in range(100):
                bad = out <= 0.0
                if not bad.any():
                    break
                out[bad] = self._draw(rng, int(bad.sum()))
            else:
                raise ParamError(f"{self.key}: uncertainty too large to keep samples positive")
        return out

    def _draw(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.dist == "normal":
            return rng.normal(self.value, self.u, n)
        half_width = math.sqrt(3.0) * self.u  # uniform: u = a / sqrt(3)
        return rng.uniform(self.value - half_width, self.value + half_width, n)


_PARAM_KEYS = {"value", "unit", "source", "u", "u_rel", "dist", "ref", "note"}


def parse_param(key: str, entry: Any) -> Param:
    """Parse one data-file entry such as
    ``{ value = 1750, unit = "rpm/V", source = "estimate", u_rel = 0.03 }``.
    """
    if not isinstance(entry, Mapping):
        raise ParamError(f"{key}: a parameter must be a table with value, unit and source")
    unknown = set(entry) - _PARAM_KEYS
    if unknown:
        raise ParamError(f"{key}: unknown fields {sorted(unknown)}")
    for required in ("value", "unit", "source"):
        if required not in entry:
            raise ParamError(f"{key}: missing required field {required!r}")

    value = entry["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParamError(f"{key}: value must be a number, got {value!r}")
    unit = entry["unit"]
    if not units.is_known(unit):
        raise ParamError(f"{key}: unknown unit {unit!r}")
    try:
        source = Source(entry["source"])
    except ValueError:
        options = ", ".join(s.value for s in Source)
        raise ParamError(f"{key}: unknown source {entry['source']!r}; use one of {options}") from None

    if "u" in entry and "u_rel" in entry:
        raise ParamError(f"{key}: give either u or u_rel, not both")
    si_value = units.to_si(float(value), unit)
    if "u" in entry:
        u = float(entry["u"]) * units.scale(unit)
    elif "u_rel" in entry:
        u = float(entry["u_rel"]) * abs(si_value)
    else:
        u = 0.0
    if u < 0.0:
        raise ParamError(f"{key}: uncertainty must be non-negative")

    dist = entry.get("dist", "normal")
    if dist not in DISTRIBUTIONS:
        raise ParamError(f"{key}: dist must be one of {DISTRIBUTIONS}")

    return Param(
        key=key,
        value=si_value,
        unit=unit,
        source=source,
        u=u,
        dist=dist,
        ref=str(entry.get("ref", "")),
        note=str(entry.get("note", "")),
    )


def parse_vector(key: str, entry: Any) -> np.ndarray:
    """Parse a geometric vector ``{ value = [x, y, z], unit = "mm" }`` to SI."""
    if not isinstance(entry, Mapping) or "value" not in entry or "unit" not in entry:
        raise ParamError(f"{key}: a vector must be a table with value = [x, y, z] and unit")
    value = entry["value"]
    if not isinstance(value, list) or len(value) != 3:
        raise ParamError(f"{key}: vector value must have exactly 3 numbers")
    return np.array([units.to_si(float(v), entry["unit"]) for v in value])


@dataclass
class ParamSet:
    """Flat registry of every parameter a build depends on, keyed by dotted path."""

    params: dict[str, Param] = field(default_factory=dict)

    def add(self, param: Param) -> Param:
        if param.key in self.params:
            raise ParamError(f"duplicate parameter key {param.key!r}")
        self.params[param.key] = param
        return param

    def __getitem__(self, key: str) -> Param:
        return self.params[key]

    def __contains__(self, key: str) -> bool:
        return key in self.params

    def __iter__(self) -> Iterator[Param]:
        return iter(self.params.values())

    def __len__(self) -> int:
        return len(self.params)

    def uncertain(self) -> list[Param]:
        return [p for p in self if p.uncertain]

    def nominal(self) -> dict[str, float]:
        return {p.key: p.value for p in self}

    def sample(self, seed: int, n: int) -> dict[str, np.ndarray]:
        """Independent draws for every uncertain parameter.

        Each parameter has its own random stream derived from (seed, key), so
        its samples do not depend on which other parameters exist. Two builds
        that share a parameter therefore get identical draws for it: common
        random numbers, which make paired comparisons between design versions
        far less noisy than independent runs."""
        return {p.key: p.sample(key_rng(seed, p.key), n) for p in self.uncertain()}


def key_rng(seed: int, key: str) -> np.random.Generator:
    """Random generator for one parameter, stable across runs and builds."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    words = [int.from_bytes(digest[i : i + 4], "little") for i in range(0, 16, 4)]
    return np.random.default_rng(np.random.SeedSequence([seed, *words]))


class Values:
    """Parameter values for one realization: overrides fall back to nominal."""

    def __init__(self, params: ParamSet, overrides: Mapping[str, float] | None = None):
        self._params = params
        self._overrides = dict(overrides or {})
        unknown = set(self._overrides) - set(params.params)
        if unknown:
            raise ParamError(f"unknown parameter keys: {sorted(unknown)}")

    def __call__(self, key: str) -> float:
        if key in self._overrides:
            return float(self._overrides[key])
        return self._params[key].value
