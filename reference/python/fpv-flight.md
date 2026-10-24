# Rigid-body flight, controls, scene and input

Status: executable **synthetic engineering baseline**, not measured aircraft
validation. Sources describe equations, not the provenance of default numbers.

## Coordinates, equations and units

World and body are right-handed z-up; body x forward and y left. Quaternion
`[w,x,y,z]` rotates body into world. Position m, velocity m/s, acceleration m/s²,
body rates rad/s, inertia kg m², thrust N and moment N m. Rotor centers are the
four (+x,+y), (-x,+y), (-x,-y), (+x,-y) corners at arm/sqrt(2). Positive reaction
moment signs alternate + - + - around z. Newton–Euler equations are

- m dv/dt = R(q) ([0,0,sum(T)] + body_drag) + [0,0,-mg]
- J domega/dt = rotor_moment - omega × (J omega) - b omega
- dq/dt = q ⊗ [0,omega]/2; dx/dt = v
- body_drag_i = -rho CdA_i |v_rel,i| v_rel,i / 2

The source is the [MIT VNAV quadrotor dynamics lecture](https://vnav.mit.edu/material/06-Control1-notes.pdf),
with a declared diagonal quadratic drag surrogate. RK4 advances the rigid body;
quaternions are normalized after each step. Body moments include thrust lever
arms and aerodynamic propeller reaction torque. Rotor angular momentum, motor
inertia, gyroscopic effects, flexible structure and impact deformation are absent.
This matches the powertrain's explicitly quasi-steady rotor assumption, not a
claim that transient angular momentum exchange has been resolved.

Default total mass 0.72 kg; principal moments (0.005,0.005,0.009) kg m²; arm
0.12 m; air density 1.225 kg/m³; CdA (0.025,0.025,0.040) m²; angular drag
0.001 N m s. All are synthetic fixtures. The angle-mode PD/rate controller uses
±0.5 rad roll/pitch commands and ±2 rad/s yaw. Duties are bounded and saturate;
there is no altitude controller, no integral windup and no Betaflight equivalence.
The GUI hover button computes an initial, horizontal, static thrust balance from
the actual pack/motor solver. It is only an initial trim, not altitude hold.

## Integration and contact

The coupled simulator uses <=5 ms splitting steps. Powertrain SOC/temperature
uses implicit midpoint; the resulting endpoint thrust drives RK4. Coupling is
first-order in the time-varying cross-module forcing even though the isolated
methods have higher order. Whole-chain refinement is tested independently; do
not label the entire chain fourth-order. Advancing a control request is
transactional: a failed cell, power or flight guard restores every component.

Ground/obstacles use an inelastic bounding sphere (radius 0.15 m) against plane
and axis-aligned boxes. Inward normal velocity is removed; translational kinetic
loss is ledgered. This is a geometric numerical contact model, not impulse/force
or crash prediction. Position projection, incomplete angular contact response,
and possible tunnelling at extreme speeds remain limitations. Ground resting
contact may count once even before takeoff. Rendering uses exactly the same box
coordinates as collision. World extent is not a physical geofence.

## GUI and input

Run `python -m physical_fpv.fpv.server`. The stdlib server binds only 127.0.0.1,
rejects cross-origin JSON changes, and makes no external network calls. Canvas
perspective rendering uses the calculated attitude and position; FPV and chase
cameras are distinct actual projections. Control sliders, WASD/QE/arrow keys,
arm/disarm, pause/reset and replay export operate the same Python state.
Gamepad API axes have explicit deadzone and mapping; disconnect and browser blur
clear commands and disarm. Real physical joystick hardware has not been tested.

The simulator advances fixed simulated time per request and is not tied to wall
clock. The UI is not promised real-time at any machine speed. The server is a
single-session local prototype, not multi-user authenticated hosting.

## Verification

Analytical freefall/hover, gravity energy, torque direction, quaternion norm and
orthogonality, isolated RK4 step refinement, contact energy, controller signs,
NaN/range rejection, deterministic end-to-end replay, material-density→mass→hover
coupling, disarm/reset and HTTP rejection are separate software/physics checks.
None are a measured validation of vehicle motion or control response. Required
empirical inputs: mass and inertia measurement, motor thrust/torque/current maps,
propeller coefficients over advance ratio/Reynolds number, measured ESC latency,
synchronized IMU/pose and RC input logs, drag/wind characterization and held-out
flight trajectories with instrument uncertainty.

Zero-duration control events update the algebraic duty/load snapshot without
advancing time, SOC, cell temperature or rigid-body state. They are logged for
exact replay and allow disarm while paused. Space disarm works even when a
slider is focused. Keyboard A maps to negative roll (left acceleration in the
z-up convention), D positive roll; standard gamepad axis0 positive is right.
Exported replay, controls and scene snapshots are detached from live state.

The whole-chain fixed-control 2-s comparison gives maximum position differences
2.509813 mm for 10→5 ms and 1.254057 mm for 5→2.5 ms. The ratio is approximately
2, consistent with first-order controller/forcing coupling; the fine pair meets
a declared 2-mm local comparison gate. This is neither an absolute error bound
nor experimental agreement.
