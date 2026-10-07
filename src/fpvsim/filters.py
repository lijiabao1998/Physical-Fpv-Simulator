"""Discrete-time filters used by the flight controller, with exact frequency
responses so filter delay can be analysed alongside flight data.

* PT1: first-order low-pass, y += k (x - y). The gain k is solved from the
  discrete transfer function so the magnitude is exactly -3 dB at the
  requested cutoff. (The common approximation k = dt / (RC + dt), used in many
  flight-controller firmwares, puts the -3 dB point lower: about 7 % low at
  fc / fs = 1/40, growing with fc / fs.)
* PTn: n identical PT1 stages, each solved for 2^(-1/(2n)) gain at the cutoff,
  so the cascade is exactly -3 dB there.
* Biquad low-pass and notch: coefficients from R. Bristow-Johnson's
  "Cookbook formulae for audio EQ biquad filter coefficients", run in
  transposed direct form II.
"""

from __future__ import annotations

import math

import numpy as np


def pt1_gain(cutoff: float, fs: float, gain_at_cutoff: float = 1.0 / math.sqrt(2.0)) -> float:
    """k such that |k / (1 - (1 - k) z^-1)| = gain_at_cutoff at the cutoff.

    With a = 1 - k, g = gain_at_cutoff and w = 2 pi fc / fs:
    (1 - g^2) a^2 - 2 (1 - g^2 cos w) a + (1 - g^2) = 0, take the root in (0, 1).
    """
    w = 2.0 * math.pi * cutoff / fs
    g2 = gain_at_cutoff**2
    c = 1.0 - g2
    b = 1.0 - g2 * math.cos(w)
    a = (b - math.sqrt(b * b - c * c)) / c
    return 1.0 - a


class PT1:
    def __init__(self, cutoff: float, fs: float, gain_at_cutoff: float = 1.0 / math.sqrt(2.0)):
        self.k = pt1_gain(cutoff, fs, gain_at_cutoff)
        self.y = 0.0

    def update(self, x: float) -> float:
        self.y += self.k * (x - self.y)
        return self.y

    def reset(self, value: float = 0.0) -> None:
        self.y = value

    def response(self, f: np.ndarray, fs: float) -> np.ndarray:
        z1 = np.exp(-2j * np.pi * f / fs)
        return self.k / (1.0 - (1.0 - self.k) * z1)


class PTn:
    def __init__(self, order: int, cutoff: float, fs: float):
        stage_gain = 2.0 ** (-1.0 / (2.0 * order))
        self.stages = [PT1(cutoff, fs, stage_gain) for _ in range(order)]

    def update(self, x: float) -> float:
        for stage in self.stages:
            x = stage.update(x)
        return x

    def reset(self, value: float = 0.0) -> None:
        for stage in self.stages:
            stage.reset(value)

    def response(self, f: np.ndarray, fs: float) -> np.ndarray:
        h = np.ones_like(f, dtype=complex)
        for stage in self.stages:
            h *= stage.response(f, fs)
        return h


class Biquad:
    def __init__(self, fs: float):
        self.fs = fs
        self.b0 = 1.0
        self.b1 = self.b2 = self.a1 = self.a2 = 0.0
        self.z1 = self.z2 = 0.0

    @classmethod
    def lowpass(cls, cutoff: float, fs: float, q: float = 1.0 / math.sqrt(2.0)) -> "Biquad":
        bq = cls(fs)
        w0 = 2.0 * math.pi * cutoff / fs
        cw, alpha = math.cos(w0), math.sin(w0) / (2.0 * q)
        a0 = 1.0 + alpha
        bq.b0 = bq.b2 = (1.0 - cw) / 2.0 / a0
        bq.b1 = (1.0 - cw) / a0
        bq.a1 = -2.0 * cw / a0
        bq.a2 = (1.0 - alpha) / a0
        return bq

    @classmethod
    def notch(cls, center: float, fs: float, q: float) -> "Biquad":
        bq = cls(fs)
        bq.set_notch(center, q)
        return bq

    def set_notch(self, center: float, q: float) -> None:
        w0 = 2.0 * math.pi * center / self.fs
        cw, alpha = math.cos(w0), math.sin(w0) / (2.0 * q)
        a0 = 1.0 + alpha
        self.b0 = self.b2 = 1.0 / a0
        self.b1 = self.a1 = -2.0 * cw / a0
        self.a2 = (1.0 - alpha) / a0

    def update(self, x: float) -> float:
        y = self.b0 * x + self.z1
        self.z1 = self.b1 * x - self.a1 * y + self.z2
        self.z2 = self.b2 * x - self.a2 * y
        return y

    def reset(self, value: float = 0.0) -> None:
        # steady state for a constant input `value` (DC gain of the section)
        dc = (self.b0 + self.b1 + self.b2) / (1.0 + self.a1 + self.a2)
        y = dc * value
        self.z2 = self.b2 * value - self.a2 * y
        self.z1 = self.b1 * value - self.a1 * y + self.z2

    def response(self, f: np.ndarray, fs: float) -> np.ndarray:
        z1 = np.exp(-2j * np.pi * f / fs)
        z2 = z1 * z1
        return (self.b0 + self.b1 * z1 + self.b2 * z2) / (1.0 + self.a1 * z1 + self.a2 * z2)


def make_lowpass(kind: str, cutoff: float, fs: float):
    """Build a low-pass by name: pt1, pt2, pt3 or biquad."""
    if kind == "pt1":
        return PT1(cutoff, fs)
    if kind in ("pt2", "pt3"):
        return PTn(int(kind[2]), cutoff, fs)
    if kind == "biquad":
        return Biquad.lowpass(cutoff, fs)
    raise ValueError(f"unknown filter type {kind!r} (use pt1, pt2, pt3 or biquad)")


def chain_response(filters, f: np.ndarray, fs: float) -> np.ndarray:
    h = np.ones_like(f, dtype=complex)
    for flt in filters:
        h *= flt.response(f, fs)
    return h


def group_delay(h: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Group delay in seconds from a sampled complex response."""
    phase = np.unwrap(np.angle(h))
    return -np.gradient(phase, 2.0 * np.pi * f)


def phase_delay(h: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Phase delay in seconds: -phase / (2 pi f)."""
    return -np.unwrap(np.angle(h)) / (2.0 * np.pi * f)
