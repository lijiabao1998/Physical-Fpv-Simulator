"""Uncertainty propagation and sensitivity analysis.

* Monte Carlo (GUM Supplement 1 approach): every uncertain input is drawn
  from its distribution, the full analysis runs on each sample, and the
  output distribution gives percentiles and the probability of meeting each
  requirement. Inputs are treated as independent. Draws are keyed by the
  physical item a parameter belongs to (ParamSet.sample, docs/iteration.md),
  so sample i of two builds shares the values of every item both contain
  (paired comparison, see compare.py).
* One-at-a-time sensitivity (tornado): each input is moved by +/- one
  standard uncertainty with all others nominal. It shows which measurement
  would reduce output uncertainty the most.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .design import Aircraft, Build, Requirement
from .performance import evaluate

Analysis = Callable[[Aircraft], dict[str, float]]


@dataclass(frozen=True)
class MonteCarloResult:
    n: int
    seed: int
    inputs: dict[str, np.ndarray]
    outputs: dict[str, np.ndarray]

    def finite(self, key: str) -> np.ndarray:
        values = self.outputs[key]
        return values[np.isfinite(values)]

    def percentiles(self, key: str, q: tuple[float, ...] = (5.0, 50.0, 95.0)) -> np.ndarray:
        values = self.finite(key)
        if len(values) == 0:
            return np.full(len(q), math.nan)
        return np.percentile(values, q)

    def std(self, key: str) -> float:
        values = self.finite(key)
        return float(np.std(values, ddof=1)) if len(values) > 1 else math.nan

    def infeasible_fraction(self, key: str) -> float:
        return 1.0 - len(self.finite(key)) / self.n

    def probability_of_compliance(self, req: Requirement) -> float:
        """Fraction of samples meeting the requirement; infeasible samples fail."""
        return float(np.mean([req.passes(v) for v in self.outputs[req.metric]]))

    def probability_stderr(self, p: float) -> float:
        """Binomial standard error of a Monte Carlo probability estimate."""
        return math.sqrt(max(p * (1.0 - p), 0.0) / self.n)


def monte_carlo(build: Build, n: int = 1000, seed: int = 1, analysis: Analysis = evaluate,
                overrides: dict[str, float] | None = None) -> MonteCarloResult:
    """``overrides`` fix some inputs in every sample (a design point: air
    temperature, altitude, battery age); the others are sampled as usual."""
    inputs = build.params.sample(seed, n)
    for key, value in (overrides or {}).items():
        inputs[key] = np.full(n, float(value))
    collected: dict[str, list[float]] = {}
    for i in range(n):
        out = analysis(build.realize({k: v[i] for k, v in inputs.items()}))
        for key, value in out.items():
            collected.setdefault(key, []).append(value)
    return MonteCarloResult(n, seed, inputs, {k: np.asarray(v) for k, v in collected.items()})


@dataclass(frozen=True)
class TornadoBar:
    key: str
    low: float  # output with input at nominal - u
    high: float  # output with input at nominal + u

    @property
    def span(self) -> float:
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            return math.inf
        return abs(self.high - self.low)


def tornado(build: Build, metrics: list[str], analysis: Analysis = evaluate) -> tuple[dict[str, float], dict[str, list[TornadoBar]]]:
    """Return nominal outputs and, per metric, bars sorted by span (largest first)."""
    nominal = analysis(build.realize())
    bars: dict[str, list[TornadoBar]] = {m: [] for m in metrics}
    for p in sorted(build.params.uncertain(), key=lambda p: p.key):
        lo = analysis(build.realize({p.key: p.value - p.u}))
        hi = analysis(build.realize({p.key: p.value + p.u}))
        for m in metrics:
            bars[m].append(TornadoBar(p.key, lo[m], hi[m]))
    for m in metrics:
        bars[m].sort(key=lambda b: b.span, reverse=True)
    return nominal, bars
