"""Parameter groups used only by the flight simulation (stages 5 and 6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AirframeExtras:
    cda: tuple[float, float, float]  # m^2, drag area along body x, y, z
    rotor_drag_factor: float  # multiplier on momentum-theory rotor drag
    brake_current_limit: float  # A, ESC limit on reverse (braking) phase current
    drive_current_limit: float  # A, ESC limit on forward phase current (ramp-up / current protection)
    contacts: tuple[tuple[float, float, float], ...]  # m, body frame, mount origin
    contact_stiffness: float  # N/m per contact point
    contact_damping: float  # N s/m per contact point
    ground_friction: float  # Coulomb coefficient


@dataclass(frozen=True)
class GyroSpec:
    """Gyro sensor and the rpm-locked vibration it picks up from the airframe.

    Vibration line of motor i, harmonic h, on an axis:
        A_h * (omega_i / omega_ref)^p * axis_weight * sin(h * theta_i + phase)
    with axis weights (1, 1, yaw_ratio). The amplitudes lump prop and motor
    imbalance together with the frame's mechanical transfer to the gyro.
    """

    noise_density: float  # rad/s/sqrt(Hz), white noise
    vib_amplitudes: tuple[float, ...]  # rad/s at omega_ref, one per harmonic
    vib_harmonics: tuple[int, ...]  # multiples of the rotor frequency
    vib_ref_speed: float  # rad/s
    vib_exponent: float
    vib_yaw_ratio: float
