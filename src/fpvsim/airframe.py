"""Parameter groups used only by the flight simulation (stages 5 and 6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AirframeExtras:
    cda: tuple[float, float, float]  # m^2, frame drag area along body x, y, z, acting at cda_center
    # parts with their own drag: (position in the body frame / mount origin, drag areas x, y, z),
    # each acting at its own position so a camera high above the CG adds a pitching moment
    drag_points: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]
    rotor_drag_factor: float  # multiplier on momentum-theory rotor drag
    brake_current_limit: float  # A, ESC limit on reverse (braking) phase current
    drive_current_limit: float  # A, ESC limit on forward phase current (ramp-up / current protection)
    contacts: tuple[tuple[float, float, float], ...]  # m, body frame, mount origin
    contact_stiffness: float  # N/m per contact point
    contact_damping: float  # N s/m per contact point
    ground_friction: float  # Coulomb coefficient
    # where the frame's drag acts (mount origin frame, m): a fixed point of the airframe,
    # so moving the CG (a payload) changes the frame drag's moment arm; None = at the CG
    cda_center: tuple[float, float, float] | None = None


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
