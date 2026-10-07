"""Sensor models: gyro with white noise and rpm-locked vibration.

The gyro reads the true body rate plus
* white noise with the specified density (one-sided), so the standard
  deviation per sample is density * sqrt(fs / 2);
* vibration lines locked to each rotor's angle at harmonics 1, 2 and the blade
  count, with amplitude growing as (omega / omega_ref)^p (see GyroSpec).

Vibration enters only the sensor; the small rigid-body motion it causes is
neglected. Gyro bias is assumed removed by calibration at arming.
"""

from __future__ import annotations

import math

import numpy as np

from .airframe import GyroSpec


class Gyro:
    BLOCK = 8192

    def __init__(self, spec: GyroSpec, n_motors: int, fs: float, rng: np.random.Generator):
        self.spec = spec
        self.n = n_motors
        self.sigma = spec.noise_density * math.sqrt(fs / 2.0)
        self.rng = rng
        self._noise = rng.standard_normal((self.BLOCK, 3)).tolist()
        self._k = 0
        phases = rng.uniform(0.0, 2.0 * math.pi, (n_motors, len(spec.vib_harmonics), 3))
        weights = (1.0, 1.0, spec.vib_yaw_ratio)
        # sin(h theta + phi) = sin(h theta) cos(phi) + cos(h theta) sin(phi)
        self._cs = [
            [[(weights[a] * math.cos(phases[i, j, a]), weights[a] * math.sin(phases[i, j, a])) for a in range(3)]
             for j in range(len(spec.vib_harmonics))]
            for i in range(n_motors)
        ]

    def sample(self, rates: list[float], thetas: list[float], omegas: list[float]) -> list[float]:
        """Measured body rates in rad/s."""
        if self._k == self.BLOCK:
            self._noise = self.rng.standard_normal((self.BLOCK, 3)).tolist()
            self._k = 0
        nz = self._noise[self._k]
        self._k += 1
        s = self.sigma
        out = [rates[0] + s * nz[0], rates[1] + s * nz[1], rates[2] + s * nz[2]]
        spec = self.spec
        for i in range(self.n):
            scale = (omegas[i] / spec.vib_ref_speed) ** spec.vib_exponent if omegas[i] > 0.0 else 0.0
            if scale == 0.0:
                continue
            for j, h in enumerate(spec.vib_harmonics):
                amp = spec.vib_amplitudes[j] * scale
                ang = h * thetas[i]
                sa, ca = amp * math.sin(ang), amp * math.cos(ang)
                for a, (c, si) in enumerate(self._cs[i][j]):
                    out[a] += sa * c + ca * si
        return out
