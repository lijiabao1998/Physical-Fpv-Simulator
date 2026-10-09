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
    [15+n]  battery temperature, K (lumped; R0 and R1 follow it, see battery.py)

Forces and moments per rotor i (hub at r_i from the CG, spin sign s_i = +1 for
CW seen from above, i.e. spin vector +z), with the hub's air-relative velocity
v_hub = v + w x r_i in body axes:

* props with blade geometry (rotor_ff.py): coefficients looked up at
  mu = |v_hub,inplane| / V_ref and lambda = -(v_hub . z) / V_ref, with
  V_ref = sqrt((omega R)^2 + |v_hub|^2) (so idle and stopped props are
  covered) and q = rho A V_ref^2:
      thrust      C_T q along -z, times frame interference
      rotor drag  C_H q against the in-plane motion, side force C_Y q
      hub moment  C_Mx q R about the in-plane motion, C_My q R about its normal
      shaft torque C_Q q R
  (anchored to the axial Ct(J), Cp(J) curves, so hover and axial climb are
  as before). The table lookup is done once per RK4 step, at its first
  stage; the coefficients are held over the other three stages while q
  still follows the rotor speed and air speed at every stage;
* props without geometry (legacy): T_i = Ct(J_i) rho n_i^2 D^4 with
  J_i = axial inflow / (n_i D), and momentum-theory rotor drag
  F_i = -k_rd omega_i v_hub,inplane;
* ground effect: thrust times the Cheeseman-Bennett ratio for the hub's
  distance to the ground along the rotor axis (wind.py);
* reaction    M_z = -s_i tau_motor,i      (motor torque reacts on the frame).

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
from .rotor_ff import CLASSICAL_LIMIT, anchored_rotor
from .wind import ground_effect


@dataclass
class Outputs:
    """Quantities computed alongside the derivative, for sensors and logs."""

    v_bus: float
    i_bus: float
    i_motor: list[float]
    thrust: list[float]
    advance_ratio: list[float]  # axial J of each rotor
    descent_ratio: float  # worst axial descent / hover induced velocity, rotors whose wake is not blown away
    on_ground: bool
    max_contact_speed: float
    edgewise_ratio: float = 0.0  # worst rotor advance ratio mu = V_inplane / (omega R), capped at 10
    off_design: bool = False  # a rotor beyond rotorcraft mu or |lambda| of 0.5 (low rpm, high speed)
    ground_effect: float = 1.0  # largest thrust ratio in ground effect over the rotors


class QuadModel:
    def __init__(self, ac: Aircraft, extras: AirframeExtras, ground_effect: bool = True):
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
        self.radius = prop.radius
        self.rho_area = rho * prop.disk_area
        if prop.blade is not None:  # oblique-flow tables
            self.rotor = anchored_rotor(prop, extras.flap_fraction)
            self.rotor_cells = [self.rotor.cells[0 if sp < 0 else 1] for sp in self.spin]
            self.k_rotor_drag = None
        else:  # legacy: momentum drag rho A v_i v_h with v_i = sqrt(kT / (2 rho A)) omega
            self.rotor = None
            self.k_rotor_drag = extras.rotor_drag_factor * math.sqrt(rho * prop.disk_area * self.k_thrust_static / 2.0)
        self._frozen = [None] * self.n  # coefficients held over an RK4 step
        self._off_design = False
        self.interference = ac.thrust_interference
        hover = hover_point(ac)
        self.v_induced_hover = math.sqrt(ac.weight / (self.n * 2.0 * rho * prop.disk_area))
        self.hover_omega = hover.omega if hover else 0.0

        # frame drag acts at a fixed point of the airframe (cda_center), part drag at each part:
        # all of them as drag points relative to the CG
        frame_point = cg if extras.cda_center is None else np.array(extras.cda_center)
        self.drag_points = [
            (tuple(float(x) for x in (np.array(pos) - cg)), tuple(float(a) for a in areas))
            for pos, areas in (((frame_point, extras.cda),) + tuple(extras.drag_points))
            if any(areas)
        ]
        self.k_contact = extras.contact_stiffness
        self.c_contact = extras.contact_damping
        self.mu = extras.ground_friction
        self.g = ac.env.g

        battery = ac.battery
        self.battery = battery
        self.harness = ac.harness_resistance
        self.r0_ref = battery.r0
        self.r1_ref = battery.r1
        self.r_source = battery.r0_at(ac.battery_start_temperature) + ac.harness_resistance
        self.r1 = battery.r1_at(ac.battery_start_temperature)
        self.tau1 = battery.tau1
        self.capacity = battery.capacity
        self.ocv_soc = [float(x) for x in battery.ocv_soc]
        self.ocv_v = [battery.series * float(x) for x in battery.ocv_cell]
        self.p_aux = pt.p_aux
        self.t_ambient = ac.env.temperature
        self.t_start = ac.battery_start_temperature
        self.n_state = 16 + self.n
        self.ground_effect = ground_effect
        self.ge_height = 5.0 * self.radius  # beyond this the ground effect is below 0.3 %

    # ------------------------------------------------------------------ helpers

    def initial_state(self, position=(0.0, 0.0, 0.0), omega: float = 0.0, soc: float = 1.0,
                      temperature: float | None = None) -> list[float]:
        t_batt = self.t_start if temperature is None else temperature
        return [*position, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, *([omega] * self.n), soc, 0.0, t_batt]

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

    def _bus(self, duties: list[float], omegas: list[float], v_source: float,
             r_source: float | None = None) -> tuple[float, list[float], float]:
        """Solve bus voltage and motor currents. Returns (V_bus, I_motor, I_bus).

        A motor whose ideal current would exceed the ESC's drive or braking
        limit runs at that limit instead; its bus power is then fixed, so the
        bus is re-solved with it as a constant-power load."""
        R, ke = self.r_circuit, self.ke
        Rs = self.r_source if r_source is None else r_source
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

    def rotor_drag(self, speed: float, omega: float) -> float:
        """Total in-plane rotor drag (N) of all rotors at ``omega`` in level edgewise
        flow at ``speed``, for a first-order drag budget."""
        if self.rotor is None:
            return self.n * self.k_rotor_drag * omega * speed
        rho = self.rho_area / (math.pi * self.radius**2)
        return sum(self.rotor.loads((speed, 0.0, 0.0), omega, sp, rho)["h_force"] for sp in self.spin)

    # --------------------------------------------------------------- derivative

    def derivative(self, s: list[float], duties: list[float], wind=(0.0, 0.0, 0.0), out: Outputs | None = None,
                   fresh: bool = True) -> list[float]:
        """State derivative. ``fresh=False`` reuses the rotor coefficients of the
        last fresh call (the later RK4 stages of a step)."""
        n = self.n
        qw, qx, qy, qz = s[6], s[7], s[8], s[9]
        wx, wy, wz = s[10], s[11], s[12]
        omegas = s[13 : 13 + n]
        soc, v_rc, t_batt = s[13 + n], s[14 + n], s[15 + n]
        battery = self.battery
        r_factor = battery.resistance_factor(t_batt)
        r_source = self.r0_ref * r_factor + self.harness
        r1 = self.r1_ref * r_factor

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
        v_bus, currents, i_bus = self._bus(duties, omegas, v_source, r_source)

        fx = fy = fz = 0.0
        mx = my = mz = 0.0
        domega = [0.0] * n
        rho, D, kt = self.rho, self.D, self.kt
        thrusts = [0.0] * n if out is not None else None
        js = [0.0] * n if out is not None else None
        worst_descent = 0.0
        rotor = self.rotor
        R = self.radius
        vh2 = self.v_induced_hover * self.v_induced_hover
        worst_mu = 0.0
        ground_ratio = 1.0
        if fresh:
            self._off_design = False
        for i in range(n):
            w = omegas[i]
            hx, hy, hz = self.hub[i]
            # hub velocity: v + w x r
            vhx = ub + wy * hz - wz * hy
            vhy = vb + wz * hx - wx * hz
            vhz = wb + wx * hy - wy * hx
            n_rev = w / (2.0 * math.pi)
            v_axial = -vhz
            v_e2 = vhx * vhx + vhy * vhy
            if v_axial < 0.0 and v_e2 < vh2:  # descending into its own wake, not blown away by edgewise flow
                worst_descent = max(worst_descent, -v_axial)
            J = v_axial / (n_rev * D) if n_rev > 1.0 else 0.0
            hmx = hmy = 0.0
            if rotor is not None:
                omega_r = w * R
                v_ref2 = omega_r * omega_r + v_e2 + v_axial * v_axial
                if fresh:
                    if v_ref2 > 1e-18:
                        v_ref = math.sqrt(v_ref2)
                        mu, lam = math.sqrt(v_e2) / v_ref, v_axial / v_ref
                    else:
                        mu = lam = 0.0
                    self._frozen[i] = rotor.lookup(self.rotor_cells[i], mu, lam)
                    # rotorcraft ratios, for the validity monitor
                    lim = CLASSICAL_LIMIT * omega_r
                    if v_e2 > lim * lim or v_axial * v_axial > lim * lim:
                        self._off_design = True
                    worst_mu = max(worst_mu, min(math.sqrt(v_e2) / omega_r, 10.0) if omega_r > 1e-6 else 10.0)
                ct_r, ch_r, cy_r, cq_r, cmx_r, cmy_r = self._frozen[i]
                qd = self.rho_area * v_ref2
                thrust = ct_r * qd
                q_aero = cq_r * qd * R
                if v_e2 > 1e-18:
                    v_e = math.sqrt(v_e2)
                    e1x, e1y = vhx / v_e, vhy / v_e
                else:
                    e1x, e1y = 1.0, 0.0
                # in-plane force -C_H e1 + C_Y e2, hub moment C_Mx e1 + C_My e2, with e2 = up x e1 = (e1y, -e1x)
                frx = (-ch_r * e1x + cy_r * e1y) * qd
                fry = (-ch_r * e1y - cy_r * e1x) * qd
                hmx = (cmx_r * e1x + cmy_r * e1y) * qd * R
                hmy = (cmx_r * e1y - cmy_r * e1x) * qd * R
            else:
                ct, cp = self._coeffs(J)
                thrust = ct * rho * n_rev * n_rev * D**4
                q_aero = cp * rho * n_rev * n_rev * D**5 / (2.0 * math.pi)
                k = self.k_rotor_drag * w
                frx, fry = -k * vhx, -k * vhy
            if self.ground_effect and r22 > 0.1:  # rotor axis pointing at the ground
                z_axis = -(s[2] + r20 * hx + r21 * hy + r22 * hz) / r22
                if z_axis < self.ge_height:
                    ge = ground_effect(z_axis / R)
                    thrust *= ge
                    ground_ratio = max(ground_ratio, ge)
            frz = -self.interference * thrust
            fx += frx
            fy += fry
            fz += frz
            mx += hy * frz - hz * fry + hmx
            my += hz * frx - hx * frz + hmy
            mz += hx * fry - hy * frx
            tau = kt * (currents[i] - (self.i0_const + self.i0_slope * w))
            mz -= self.spin[i] * tau
            dw = (tau - q_aero) / self.j_rotor
            domega[i] = dw if (w > 0.0 or dw > 0.0) else 0.0
            if out is not None:
                thrusts[i] = thrust
                js[i] = J

        # body drag, per axis: the frame at its drag centre, parts with their own drag at their position
        for (px, py, pz), (ax_, ay_, az_) in self.drag_points:
            lu = ub + wy * pz - wz * py
            lv = vb + wz * px - wx * pz
            lw = wb + wx * py - wy * px
            q_part = 0.5 * rho * math.sqrt(lu * lu + lv * lv + lw * lw)
            dfx, dfy, dfz = -q_part * ax_ * lu, -q_part * ay_ * lv, -q_part * az_ * lw
            fx += dfx
            fy += dfy
            fz += dfz
            mx += py * dfz - pz * dfy
            my += pz * dfx - px * dfz
            mz += px * dfy - py * dfx

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
            out.edgewise_ratio = worst_mu
            out.off_design = self._off_design
            out.ground_effect = ground_ratio
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
            (i_bus * r1 - v_rc) / self.tau1,
            self._battery_heating(i_bus, v_rc, t_batt, r_factor, ub, vb, wb),
        ]

    def _battery_heating(self, i_bus: float, v_rc: float, t_batt: float, r_factor: float,
                         ub: float, vb: float, wb: float) -> float:
        """dT/dt of the pack: Joule heat minus convection at the current air speed."""
        battery = self.battery
        if not battery.thermal:
            return 0.0
        r0 = self.r0_ref * r_factor
        r1 = self.r1_ref * r_factor
        q = i_bus * i_bus * r0 + (v_rc * v_rc / r1 if r1 > 0.0 else 0.0)
        ha = battery.conductance(math.sqrt(ub * ub + vb * vb + wb * wb))
        return (q - ha * (t_batt - self.t_ambient)) / battery.heat_capacity

    def step(self, s: list[float], duties: list[float], dt: float, wind=(0.0, 0.0, 0.0), out: Outputs | None = None) -> list[float]:
        """Classic RK4 with duties held over the step (and the rotor table
        lookup from its first stage), then quaternion renormalised."""
        k1 = self.derivative(s, duties, wind, out)
        s2 = [a + 0.5 * dt * b for a, b in zip(s, k1)]
        k2 = self.derivative(s2, duties, wind, fresh=False)
        s3 = [a + 0.5 * dt * b for a, b in zip(s, k2)]
        k3 = self.derivative(s3, duties, wind, fresh=False)
        s4 = [a + dt * b for a, b in zip(s, k3)]
        k4 = self.derivative(s4, duties, wind, fresh=False)
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
