"""Explicit, immutable piecewise-linear discharge current in seconds and amperes."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike

_HASH_HEADER = b"physical_fpv.CurrentProfile\0version=1\0time=s\0current=A\0interpolation=linear\0"


def _real_array(values: ArrayLike, name: str) -> np.ndarray:
    """Copy real numeric inputs without discarding complex parts or parsing strings."""
    try:
        raw = np.asarray(values)
        if raw.dtype.kind not in "iuf":
            raise ValueError(f"{name} must contain real numbers")
        result = np.array(raw, dtype="<f8", copy=True)
    except (TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must contain real numbers") from exc
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True, init=False)
class CurrentProfile:
    """A positive discharge current on the closed interval [0, end_time_s].

    Supply at least two strictly increasing time knots, starting exactly at zero,
    and their currents. The final supplied knot defines coverage; queries never
    extrapolate. The caller must supply and separately document any assumption
    before its first observation or beyond its last observation. This class
    neither shifts recorded timestamps nor inserts or deduplicates knots.

    ``time_s`` and ``current_a`` return immutable, independent array views backed
    by bytes. Neither changes to constructor inputs nor NumPy write-flag or shape
    changes to a returned view can change the profile or its fingerprint.

    ``min_current_a`` and ``max_current_a`` describe the entire linear profile so
    a caller can enforce its own supported range; no model limits are inferred.
    The SHA256 covers a versioned units/interpolation header, a little-endian
    uint64 knot count, then all times and all currents as little-endian float64.
    Negative zero at the first time knot is canonicalized to positive zero.
    """

    _time_bytes: bytes = field(repr=False)
    _current_bytes: bytes = field(repr=False)
    _charge_bytes: bytes = field(repr=False)
    end_time_s: float
    min_current_a: float
    max_current_a: float
    fingerprint_sha256: str

    def __init__(self, time_s: ArrayLike, current_a: ArrayLike) -> None:
        times = _real_array(time_s, "time_s")
        currents = _real_array(current_a, "current_a")
        if times.ndim != 1 or currents.ndim != 1:
            raise ValueError("time_s and current_a must be one-dimensional")
        if len(times) < 2 or times.shape != currents.shape:
            raise ValueError("Provide at least two matching time and current knots")
        if times[0] != 0:
            raise ValueError("time_s must begin at zero; provide initial coverage explicitly")
        if np.any(np.diff(times) <= 0):
            raise ValueError("time_s must be strictly increasing; duplicate clocks are invalid")
        if np.any(currents <= 0):
            raise ValueError("current_a must be positive discharge current")
        times[0] = 0.0
        # Analytic trapezoid areas at knots, in Ah. Halving first avoids overflow
        # when the sum of two otherwise representable currents would overflow.
        with np.errstate(over="ignore", invalid="ignore"):
            segment_charge = (np.diff(times) / 3600) * (currents[:-1] / 2 + currents[1:] / 2)
            cumulative_charge = np.concatenate(([0.0], np.cumsum(segment_charge)))
        if not np.isfinite(cumulative_charge).all():
            raise ValueError("Integrated charge must be representable as finite float64")
        time_bytes = times.tobytes()
        current_bytes = currents.tobytes()
        fingerprint = hashlib.sha256(
            _HASH_HEADER + struct.pack("<Q", len(times)) + time_bytes + current_bytes
        ).hexdigest()
        object.__setattr__(self, "_time_bytes", time_bytes)
        object.__setattr__(self, "_current_bytes", current_bytes)
        object.__setattr__(self, "_charge_bytes", cumulative_charge.astype("<f8").tobytes())
        object.__setattr__(self, "end_time_s", float(times[-1]))
        object.__setattr__(self, "min_current_a", float(currents.min()))
        object.__setattr__(self, "max_current_a", float(currents.max()))
        object.__setattr__(self, "fingerprint_sha256", fingerprint)

    @property
    def time_s(self) -> np.ndarray:
        return np.frombuffer(self._time_bytes, dtype="<f8")

    @property
    def current_a(self) -> np.ndarray:
        return np.frombuffer(self._current_bytes, dtype="<f8")

    def require_coverage(self, end_time_s: float) -> None:
        """Reject a requested interval [0, end_time_s] outside supplied coverage."""
        end = _real_array(end_time_s, "end_time_s")
        if end.ndim != 0:
            raise ValueError("end_time_s must be a scalar")
        self._check_coverage(end)

    def _check_coverage(self, time_s: np.ndarray) -> None:
        if np.any((time_s < 0) | (time_s > self.end_time_s)):
            raise ValueError(f"Time outside provided coverage [0, {self.end_time_s}] s")

    def _segment(self, time_s: ArrayLike) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        query = _real_array(time_s, "Query time_s")
        self._check_coverage(query)
        times = self.time_s
        index = np.minimum(np.searchsorted(times, query, side="right") - 1, len(times) - 2)
        elapsed = query - times[index]
        fraction = elapsed / (times[index + 1] - times[index])
        return index, elapsed, fraction

    def value_at(self, time_s: ArrayLike) -> float | np.ndarray:
        """Evaluate linear current in A; array queries preserve their shape."""
        index, _, fraction = self._segment(time_s)
        times = self.time_s
        query = _real_array(time_s, "Query time_s")
        # Compute each endpoint distance directly: 1-fraction loses relative
        # precision just before a knot when the left current is much larger.
        left_weight = (times[index + 1] - query) / (times[index + 1] - times[index])
        currents = self.current_a
        left, right = currents[index], currents[index + 1]
        near_left = fraction <= 0.5
        # Anchor at the nearest endpoint. This avoids cancellation in a tiny
        # endpoint weight and overflow from two rounded weights summing above 1.
        base = np.where(near_left, left, right)
        distance = np.where(near_left, fraction, left_weight)
        delta = np.where(near_left, right - left, left - right)
        result = base + distance * delta
        return float(result) if result.ndim == 0 else result

    def charge_integral_ah(self, time_s: ArrayLike) -> float | np.ndarray:
        """Analytically integrate current from zero to each time, returning Ah.

        Each partial segment is integrated as a quadratic in local elapsed time,
        rather than interpolating the cumulative charge between its end knots.
        """
        index, elapsed, fraction = self._segment(time_s)
        currents = self.current_a
        cumulative_charge = np.frombuffer(self._charge_bytes, dtype="<f8")
        mean_current = (1 - fraction / 2) * currents[index] + fraction / 2 * currents[index + 1]
        result = cumulative_charge[index] + (elapsed / 3600) * mean_current
        return float(result) if result.ndim == 0 else result
