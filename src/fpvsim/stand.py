"""Virtual thrust stand: one motor + prop on a bench supply.

Mirrors a real static test: a regulated supply with remote voltage sensing
(zero source resistance), throttle swept in steps, readings logged to CSV.
The CSV uses the same "name [unit]" header convention that sysid.py reads,
so real and virtual stand data go through the same analysis.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .atmosphere import Environment
from .powertrain import Powertrain
from .units import G0, RADS_TO_RPM

if TYPE_CHECKING:
    from .design import Aircraft


@dataclass(frozen=True)
class StandRow:
    duty: float
    omega: float
    thrust: float  # N
    torque: float  # N m
    voltage: float  # V
    current: float  # A
    p_elec: float  # W
    p_shaft: float  # W
    tip_mach: float

    @property
    def drive_efficiency(self) -> float:
        return self.p_shaft / self.p_elec if self.p_elec > 0 else 0.0

    @property
    def specific_thrust(self) -> float:
        """N/W."""
        return self.thrust / self.p_elec if self.p_elec > 0 else 0.0


COLUMNS = (
    ("duty [%]", lambda r: 100.0 * r.duty),
    ("rpm [rpm]", lambda r: r.omega * RADS_TO_RPM),
    ("thrust [gf]", lambda r: r.thrust / (G0 * 1e-3)),
    ("torque [N*m]", lambda r: r.torque),
    ("voltage [V]", lambda r: r.voltage),
    ("current [A]", lambda r: r.current),
    ("power_elec [W]", lambda r: r.p_elec),
    ("power_shaft [W]", lambda r: r.p_shaft),
    ("efficiency_drive [%]", lambda r: 100.0 * r.drive_efficiency),
    ("specific_thrust [gf/W]", lambda r: r.specific_thrust / (G0 * 1e-3)),
    ("tip_mach [1]", lambda r: r.tip_mach),
)


def run_stand(ac: "Aircraft", voltage: float, duties: np.ndarray | None = None) -> list[StandRow]:
    """Sweep duty on a single rotor of ``ac`` at a fixed supply voltage."""
    if duties is None:
        duties = np.linspace(0.0, 1.0, 21)
    pt = ac.powertrain
    single = Powertrain(pt.motor, pt.prop, pt.esc, n_rotors=1, p_aux=0.0)
    env: Environment = ac.env
    rows = []
    for duty in duties:
        op = single.at_duty(float(duty), voltage, 0.0, env.rho)
        rows.append(
            StandRow(
                duty=op.duty,
                omega=op.omega,
                thrust=op.thrust,
                torque=op.torque,
                voltage=op.v_bus,
                current=op.i_bus,
                p_elec=op.p_bus,
                p_shaft=op.p_shaft,
                tip_mach=pt.prop.tip_mach(op.omega, env.speed_of_sound),
            )
        )
    return rows


def write_csv(rows: list[StandRow], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([name for name, _ in COLUMNS])
        for row in rows:
            writer.writerow([f"{fn(row):.6g}" for _, fn in COLUMNS])
