"""6DOF flight dynamics: rigid body, motors, rotor aerodynamics, battery, ground.

Frames: world NED (x north, y east, z down, ground plane at z = 0); body FRD
(x forward, y right, z down). The attitude quaternion q = (w, x, y, z) rotates
body vectors into the world frame.

State vector (plain Python floats, for speed in the inner loop):

    [0:3]   position, world, m
    [3:6]   velocity, world, m/s
    [6:10]  attitude quaternion, body -> world
    [10:13] body angular rate, rad/s
    [13:13+n]   rotor speeds, rad/s
    [13+n]  battery state of charge
    [14+n]  battery polarisation voltage v_rc, V

Forces and moments per rotor i (hub at r_i from the CG, spin sign s_i = +1 for
CW seen from above, i.e. spin vector +z):

    thrust      T_i = Ct(J_i) rho n_i^2 D^4, along -z, times frame interference
    J_i         = axial inflow / (n_i D), axial inflow = -(v_hub . z)
    rotor drag  F_i = -k_rd omega_i v_hub,inplane     (momentum drag, low advance ratio)
    reaction    M_z = -s_i tau_motor,i                (motor torque reacts on the frame)

Body: I w' = sum(r_i x F_i) + M_reaction + M_ground - w x (I w + h_rotors),
where h_rotors = sum(J_r omega_i s_i) z is the rotors' spin angular momentum.

Rotor:  J_r omega_i' = Kt (I_i - I0(omega_i)) - Q_i,  with the averaged ESC
model of motor.py. The ESC runs complementary PWM, so current can reverse
(active braking, energy back to the bus). Phase current is limited on both
sides: the drive limit stands for the ESC firmware's ramp-up and current
protection (without it, a throttle step at low rpm would draw V/R), the
braking limit for how hard the ESC brakes when throttle is cut.

Bus: the battery Thevenin source, all motor currents and the constant-power
avionics load are solved together for the bus voltage at every evaluation.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

from .airframe import AirframeExtras
from .design import Aircraft
from .performance import hover_point


@dataclass
class Outputs:
    """Quantities computed alongside the derivative, for sensors and logs."""

    v_bus: float
    i_bus: float
    i_motor: list[float]
    thrust: list[float]
    advance_ratio: list[float]
    descent_ratio: float  # worst axial descent speed / hover induced velocity
    on_ground: bool
    max_contact_speed: float


class QuadModel:
    def __init__(self, ac: Aircraft, extras: AirframeExtras):
        pt = ac.powertrain
        mp = ac.mass_props
        self.ac = ac
        self.n = pt.n_rotors
        self.mass = mp.mass
        # nested Python floats: numpy scalar arithmetic is slow in the inner loop
        self.inertia = [[float(x) for x in row] for row in mp.inertia]
        self.inv_inertia = [[float(x) for x in row] for row in np.linalg.inv(mp.inertia)]
        cg = mp.cg
        prop_items = [i for i in ac.items if i.mass_key == "prop.mass"]
        self.hub = [tuple(float(x) for x in (item.position - cg)) for item in prop_items]
        self.spin = [1.0 if r.spin == "cw" else -1.0 for r in ac.rotors]
        self.contacts = [tuple(float(c) for c in (np.array(p) - cg)) for p in extras.contacts]

        motor = pt.motor
        self.kt = float(motor.kt)
        self.ke = motor.ke
        self.r_circuit = pt.r_circuit
        self.i0_const = motor.i0_const
        self.i0_slope = motor.i0_slope
        self.j_rotor = motor.rotor_inertia + pt.prop.spin_inertia
        self.brake_limit = extras.brake_current_limit
        self.drive_limit = extras.drive_current_limit

        prop = pt.prop
        rho = ac.env.rho
        self.rho = rho
        self.D = prop.diameter
        self.J_grid = [float(j) for j in prop.curves.J]
        self.ct_grid = [prop.ct_scale * float(c) for c in prop.curves.ct]
        self.cp_grid = [prop.cp_scale * float(c) for c in prop.curves.cp]
        self.k_thrust_static = prop.k_thrust(rho)
        # momentum drag of a rotor in edgewise flow: rho A v_i v_h with v_i = sqrt(kT / (2 rho A)) omega
        self.k_rotor_drag = extras.rotor_drag_factor * math.sqrt(rho * prop.disk_area * self.k_thrust_static / 2.0)
        self.interference = ac.thrust_interference
        hover = hover_point(ac)
        self.v_induced_hover = math.sqrt(ac.weight / (self.n * 2.0 * rho * prop.disk_area))
        self.hover_omega = hover.omega if hover else 0.0

        self.cda = extras.cda
        self.k_contact = extras.contact_stiffness
        self.c_contact = extras.contact_damping
        self.mu = extras.ground_friction
        self.g = ac.env.g

        battery = ac.battery
        self.battery = battery
        self.r_source = battery.r0 + ac.harness_resistance
        self.r1 = battery.r1
        self.tau1 = battery.tau1
        self.capacity = battery.capacity
        self.ocv_soc = [float(x) for x in battery.ocv_soc]
        self.ocv_v = [battery.series * float(x) for x in battery.ocv_cell]
        self.p_aux = pt.p_aux
        self.n_state = 15 + self.n

    # ------------------------------------------------------------------ helpers

    def initial_state(self, position=(0.0, 0.0, 0.0), omega: float = 0.0, soc: float = 1.0) -> list[float]:
        return [*position, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, *([omega] * self.n), soc, 0.0]

    def _ocv(self, soc: float) -> float:
        xs, ys = self.ocv_soc, self.ocv_v
        if soc <= xs[0]:
            return ys[0]
        if soc >= xs[-1]:
            return ys[-1]
        k = bisect_right(xs, soc) - 1
        t = (soc - xs[k]) / (xs[k + 1] - xs[k])
        return ys[k] + t * (ys[k + 1] - ys[k])

    def _coeffs(self, J: float) -> tuple[float, float]:
        xs = self.J_grid
        if J <= 0.0:
            return self.ct_grid[0], self.cp_grid[0]
        if J >= xs[-1]:
            return self.ct_grid[-1], self.cp_grid[-1]
        k = bisect_right(xs, J) - 1
        t = (J - xs[k]) / (xs[k + 1] - xs[k])
        return (
            self.ct_grid[k] + t * (self.ct_grid[k + 1] - self.ct_grid[k]),
            self.cp_grid[k] + t * (self.cp_grid[k + 1] - self.cp_grid[k]),
        )

    def _bus(self, duties: list[float], omegas: list[float], v_source: float) -> tuple[float, list[float], float]:
        """Solve bus voltage and motor currents. Returns (V_bus, I_motor, I_bus).

        A motor whose ideal current would exceed the ESC's drive or braking
        limit runs at that limit instead; its bus power is then fixed, so the
        bus is re-solved with it as a constant-power load."""
        R, ke, Rs = self.r_circuit, self.ke, self.r_source
        limit = [None] * self.n  # None, or the current the ESC holds this motor at
        for _ in range(self.n + 1):
            a = b = 0.0
            p_fixed = self.p_aux
            for i in range(self.n):
                if limit[i] is not None:
                    p_fixed += (ke * omegas[i] + limit[i] * R) * limit[i]
                else:
                    a += duties[i] * duties[i] / R
                    b += duties[i] * ke * omegas[i] / R
            A = 1.0 + Rs * a
            B = v_source + Rs * b
            disc = B * B - 4.0 * A * Rs * p_fixed
            v_bus = (B + math.sqrt(disc)) / (2.0 * A) if disc > 0.0 else B / (2.0 * A)
            currents = []
            newly = False
            for i in range(self.n):
                if limit[i] is not None:
                    currents.append(limit[i])
                    continue
                current = (duties[i] * v_bus - ke * omegas[i]) / R
                if current > self.drive_limit:
                    limit[i], current, newly = self.drive_limit, self.drive_limit, True
                elif current < -self.brake_limit:
                    limit[i], current, newly = -self.brake_limit, -self.brake_limit, True
                currents.append(current)
            if not newly:
                break
        i_bus = (v_source - v_bus) / Rs if Rs > 0.0 else sum(
            (ke * w + c * R) * c for w, c in zip(omegas, currents)
        ) / v_bus + self.p_aux / v_bus
        return v_bus, currents, i_bus

    # --------------------------------------------------------------- derivative

    def derivative(self, s: list[float], duties: list[float], wind=(0.0, 0.0, 0.0), out: Outputs | None = None) -> list[float]:
        n = self.n
        qw, qx, qy, qz = s[6], s[7], s[8], s[9]
        wx, wy, wz = s[10], s[11], s[12]
        omegas = s[13 : 13 + n]
        soc, v_rc = s[13 + n], s[14 + n]

        # rotation body -> world
        r00 = 1 - 2 * (qy * qy + qz * qz)
        r01 = 2 * (qx * qy - qw * qz)
        r02 = 2 * (qx * qz + qw * qy)
        r10 = 2 * (qx * qy + qw * qz)
        r11 = 1 - 2 * (qx * qx + qz * qz)
        r12 = 2 * (qy * qz - qw * qx)
        r20 = 2 * (qx * qz - qw * qy)
        r21 = 2 * (qy * qz + qw * qx)
        r22 = 1 - 2 * (qx * qx + qy * qy)

        ax_w, ay_w, az_w = s[3] - wind[0], s[4] - wind[1], s[5] - wind[2]
        # air-relative velocity in body axes (R^T v)
        ub = r00 * ax_w + r10 * ay_w + r20 * az_w
        vb = r01 * ax_w + r11 * ay_w + r21 * az_w
        wb = r02 * ax_w + r12 * ay_w + r22 * az_w

        v_source = self._ocv(soc) - v_rc
        v_bus, currents, i_bus = self._bus(duties, omegas, v_source)

        fx = fy = fz = 0.0
        mx = my = mz = 0.0
        domega = [0.0] * n
        rho, D, kt = self.rho, self.D, self.kt
        thrusts = [0.0] * n if out is not None else None
        js = [0.0] * n if out is not None else None
        worst_descent = 0.0
        for i in range(n):
            w = omegas[i]
            hx, hy, hz = self.hub[i]
            # hub velocity: v + w x r
            vhx = ub + wy * hz - wz * hy
            vhy = vb + wz * hx - wx * hz
            vhz = wb + wx * hy - wy * hx
            n_rev = w / (2.0 * math.pi)
            v_axial = -vhz
            if v_axial < 0.0:
                worst_descent = max(worst_descent, -v_axial)
            J = v_axial / (n_rev * D) if n_rev > 1.0 else 0.0
            ct, cp = self._coeffs(J)
            thrust = ct * rho * n_rev * n_rev * D**4
            q_aero = cp * rho * n_rev * n_rev * D**5 / (2.0 * math.pi)
            f_net = self.interference * thrust
            k = self.k_rotor_drag * w
            frx, fry, frz = -k * vhx, -k * vhy, -f_net
            fx += frx
            fy += fry
            fz += frz
            mx += hy * frz - hz * fry
            my += hz * frx - hx * frz
            mz += hx * fry - hy * frx
            tau = kt * (currents[i] - (self.i0_const + self.i0_slope * w))
            mz -= self.spin[i] * tau
            dw = (tau - q_aero) / self.j_rotor
            domega[i] = dw if (w > 0.0 or dw > 0.0) else 0.0
            if out is not None:
                thrusts[i] = thrust
                js[i] = J

        # body drag, per axis
        speed = math.sqrt(ub * ub + vb * vb + wb * wb)
        q_dyn = 0.5 * rho * speed
        fx -= q_dyn * self.cda[0] * ub
        fy -= q_dyn * self.cda[1] * vb
        fz -= q_dyn * self.cda[2] * wb

        # gyroscopic coupling of the rotors' spin momentum
        h_rot = self.j_rotor * sum(self.spin[i] * omegas[i] for i in range(n))
        mx += -wy * h_rot
        my += wx * h_rot

        # forces to world, gravity
        Fx = r00 * fx + r01 * fy + r02 * fz
        Fy = r10 * fx + r11 * fy + r12 * fz
        Fz = r20 * fx + r21 * fy + r22 * fz + self.mass * self.g

        # ground contact (penalty spring-damper with regularised Coulomb friction)
        on_ground = False
        max_contact_speed = 0.0
        pz = s[2]
        for cx, cy, cz in self.contacts:
            zc = pz + r20 * cx + r21 * cy + r22 * cz
            if zc <= 0.0:
                continue
            on_ground = True
            # contact point velocity: v + R (w x c)
            lx, ly, lz = wy * cz - wz * cy, wz * cx - wx * cz, wx * cy - wy * cx
            vcx = s[3] + r00 * lx + r01 * ly + r02 * lz
            vcy = s[4] + r10 * lx + r11 * ly + r12 * lz
            vcz = s[5] + r20 * lx + r21 * ly + r22 * lz
            max_contact_speed = max(max_contact_speed, vcz)
            fn = self.k_contact * zc + self.c_contact * vcz
            if fn <= 0.0:
                continue
            vt = math.sqrt(vcx * vcx + vcy * vcy)
            scale = self.mu * fn / max(vt, 0.05)
            gx, gy, gz = -scale * vcx, -scale * vcy, -fn
            Fx += gx
            Fy += gy
            Fz += gz
            # moment in body axes: c x (R^T g)
            bx = r00 * gx + r10 * gy + r20 * gz
            by = r01 * gx + r11 * gy + r21 * gz
            bz = r02 * gx + r12 * gy + r22 * gz
            mx += cy * bz - cz * by
            my += cz * bx - cx * bz
            mz += cx * by - cy * bx

        # Euler's equation: I w' = M - w x (I w + h)
        (I00, I01, I02), (I10, I11, I12), (I20, I21, I22) = self.inertia
        Iw0 = I00 * wx + I01 * wy + I02 * wz
        Iw1 = I10 * wx + I11 * wy + I12 * wz
        Iw2 = I20 * wx + I21 * wy + I22 * wz
        tx = mx - (wy * Iw2 - wz * Iw1)
        ty = my - (wz * Iw0 - wx * Iw2)
        tz = mz - (wx * Iw1 - wy * Iw0)
        (J00, J01, J02), (J10, J11, J12), (J20, J21, J22) = self.inv_inertia
        dwx = J00 * tx + J01 * ty + J02 * tz
        dwy = J10 * tx + J11 * ty + J12 * tz
        dwz = J20 * tx + J21 * ty + J22 * tz

        if out is not None:
            out.v_bus = v_bus
            out.i_bus = i_bus
            out.i_motor = currents
            out.thrust = thrusts
            out.advance_ratio = js
            out.descent_ratio = worst_descent / self.v_induced_hover
            out.on_ground = on_ground
            out.max_contact_speed = max_contact_speed

        m = self.mass
        return [
            s[3],
            s[4],
            s[5],
            Fx / m,
            Fy / m,
            Fz / m,
            0.5 * (-qx * wx - qy * wy - qz * wz),
            0.5 * (qw * wx + qy * wz - qz * wy),
            0.5 * (qw * wy - qx * wz + qz * wx),
            0.5 * (qw * wz + qx * wy - qy * wx),
            dwx,
            dwy,
            dwz,
            *domega,
            -i_bus / self.capacity,
            (i_bus * self.r1 - v_rc) / self.tau1,
        ]

    def step(self, s: list[float], duties: list[float], dt: float, wind=(0.0, 0.0, 0.0), out: Outputs | None = None) -> list[float]:
        """Classic RK4 with duties held over the step, then quaternion renormalised."""
        k1 = self.derivative(s, duties, wind, out)
        s2 = [a + 0.5 * dt * b for a, b in zip(s, k1)]
        k2 = self.derivative(s2, duties, wind)
        s3 = [a + 0.5 * dt * b for a, b in zip(s, k2)]
        k3 = self.derivative(s3, duties, wind)
        s4 = [a + dt * b for a, b in zip(s, k3)]
        k4 = self.derivative(s4, duties, wind)
        new = [a + dt / 6.0 * (b + 2.0 * c + 2.0 * d + e) for a, b, c, d, e in zip(s, k1, k2, k3, k4)]
        norm = math.sqrt(new[6] ** 2 + new[7] ** 2 + new[8] ** 2 + new[9] ** 2)
        for k in range(6, 10):
            new[k] /= norm
        for k in range(13, 13 + self.n):
            if new[k] < 0.0:
                new[k] = 0.0
        return new


def euler_angles(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Roll, pitch, yaw (ZYX), rad."""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw
