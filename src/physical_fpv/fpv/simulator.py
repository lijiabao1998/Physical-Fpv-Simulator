"""Bounded deterministic integration of controller, synthetic powertrain and flight."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict

import numpy as np

from physical_fpv.fpv.flight import Controller, FlightConfig, FlightModel

# The same metre-coordinate boxes are used by contact and rendering.
SCENE_BOXES = [
    {"low": [8, -3, 0], "high": [8.25, -2.75, 4], "color": "#f4a340"},
    {"low": [8, 2.75, 0], "high": [8.25, 3, 4], "color": "#f4a340"},
    {"low": [8, -3, 3.75], "high": [8.25, 3, 4], "color": "#f4a340"},
    {"low": [18, 3, 0], "high": [18.25, 3.25, 5], "color": "#54b8ca"},
    {"low": [18, 8.75, 0], "high": [18.25, 9, 5], "color": "#54b8ca"},
    {"low": [18, 3, 4.75], "high": [18.25, 9, 5], "color": "#54b8ca"},
    {"low": [30, -8, 0], "high": [35, -3, 6], "color": "#4c6675"},
    {"low": [-12, 10, 0], "high": [-4, 16, 3], "color": "#64787b"},
]


class Simulator:
    def __init__(self, *, frame_density_kg_m3=None, substep_s=0.005):
        from physical_fpv.fpv.powertrain import Powertrain

        if not np.isfinite(substep_s) or not 0.0005 <= substep_s <= 0.02:
            raise ValueError("Substep must be 0.0005..0.02 seconds")
        self.substep_s = float(substep_s)
        self.powertrain = Powertrain()
        self.frame_density_kg_m3 = frame_density_kg_m3
        mass = 0.72
        self.material_source = "synthetic 0.72 kg total airframe fixture"
        if frame_density_kg_m3 is not None:
            if not np.isfinite(frame_density_kg_m3) or not 1000 < frame_density_kg_m3 < 10000:
                raise ValueError("Frame material density outside demonstration domain")
            # 50 cm3 hypothetical solid frame + 0.585 kg fixed components.
            mass = 0.585 + frame_density_kg_m3 * 5e-5
            self.material_source = "supplied reference density × 50 cm3 + synthetic components"
        # Principal moments scaled with mass under an unchanged synthetic geometry.
        scale = mass / 0.72
        self.flight = FlightModel(
            FlightConfig(
                mass_kg=mass,
                inertia_kg_m2=tuple(scale * np.array([0.005, 0.005, 0.009])),
                obstacles=tuple((x["low"], x["high"]) for x in SCENE_BOXES),
            )
        )
        self.controller = Controller()
        self.controls = {"armed": False, "throttle": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self.record = []
        self.last_duties = [0.0, 0.0, 0.0, 0.0]
        low, high = 0.0, 1.0
        for _ in range(28):
            mid = (low + high) / 2
            if np.sum(self.powertrain.evaluate([mid] * 4).thrust_n) < mass * 9.80665:
                low = mid
            else:
                high = mid
        self.hover_duty = (low + high) / 2
        self.powertrain.evaluate([0.0] * 4)

    def advance(self, controls, duration_s=0.05):
        if len(self.record) >= 20000:
            raise ValueError("Replay bound reached; export and reset before continuing")
        if not isinstance(controls, dict) or set(controls) - set(self.controls):
            raise ValueError("Unknown control fields")
        merged = self.controls | controls
        if type(merged["armed"]) is not bool:
            raise ValueError("armed must be a boolean")
        vals = np.array([merged[k] for k in ["throttle", "roll", "pitch", "yaw"]], dtype=float)
        if not np.isfinite(vals).all() or not 0 <= vals[0] <= 1 or max(abs(vals[1:])) > 1:
            raise ValueError("Controls outside normalized input domain")
        if not np.isfinite(duration_s) or not 0 <= duration_s <= 0.1:
            raise ValueError("Request duration must be 0..0.1 seconds; zero updates commands only")
        # Transactional advancement: an invalid endpoint must not leave half-updated state.
        backup = copy.deepcopy((self.powertrain, self.flight, self.controls, self.last_duties))
        try:
            self.controls = merged
            n = int(np.ceil(duration_s / self.substep_s))
            dt = duration_s / n if n else self.substep_s
            if n == 0:
                duties = (
                    self.controller.duties(self.flight.state, *vals, dt)
                    if merged["armed"]
                    else np.zeros(4)
                )
                self.powertrain.evaluate(duties)
                self.last_duties = np.asarray(duties).tolist()
            for _ in range(n):
                duties = (
                    self.controller.duties(self.flight.state, *vals, dt)
                    if merged["armed"]
                    else np.zeros(4)
                )
                power = self.powertrain.step(
                    duties, dt, airspeed_m_s=float(np.linalg.norm(self.flight.state.velocity_m_s))
                )
                self.flight.step(power.thrust_n, power.rotor_torque_nm, dt)
                self.last_duties = np.asarray(duties).tolist()
        except Exception:
            self.powertrain, self.flight, self.controls, self.last_duties = backup
            raise
        result = self.telemetry()
        if len(self.record) < 20000:
            self.record.append({"duration_s": duration_s, "controls": dict(merged)})
        return result

    def telemetry(self):
        return {
            "schema": "fpv-synthetic-chain-v1",
            "flight": self.flight.telemetry(),
            "powertrain": self.powertrain.telemetry(),
            "controls": copy.deepcopy(self.controls),
            "duties": self.last_duties.copy(),
            "scene": copy.deepcopy(SCENE_BOXES),
            "hover_duty": self.hover_duty,
            "material_source": self.material_source,
            "qualification": "Synthetic engineering baseline. No measured FPV validation.",
            "original_failures": (
                "Chen 6/12 and ORegan 30/36 FAIL; Stanford high-rate FAIL retained."
            ),
            "coordinate_frame": "world/body x forward, y left, z up; quaternion wxyz",
        }

    def replay_bundle(self):
        payload = {
            "schema": "fpv-control-replay-v1",
            "inputs": copy.deepcopy(self.record),
            "frame_density_kg_m3": self.frame_density_kg_m3,
            "substep_s": self.substep_s,
            "final_state": self.telemetry(),
            "flight_config": asdict(self.flight.config),
            "powertrain_config": asdict(self.powertrain.config),
        }
        payload["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return payload
