# Synthetic pack → ESC → motor → propeller baseline

## Status and evidence boundary

`physical_fpv.fpv.powertrain` is an executable, conservation-checked **synthetic
analytical baseline**, not a calibrated product, racing-battery prediction or
validated flight powertrain. All dimensional defaults and coefficient values
below are deliberately invented software fixtures. They are not LG M50, Chen2020,
ORegan2022, UIUC measured propeller data, or manufacturer specifications. No
PyBaMM parameter or research acceptance gate is imported, changed or extrapolated.
Passing these tests establishes implementation properties within the declared
model; it does not repair the existing battery empirical failures.

The code uses NumPy, contains no stochastic sampling, performs no download and
requires no nonlinear solver dependency. Heterogeneity is specified explicitly.
There is no molecular/electrode-to-pack parameter mapping in this module.

## API and reproducible example

```python
from physical_fpv.fpv.powertrain import Powertrain, PowertrainConfig

config = PowertrainConfig()  # synthetic 4S2P, four propulsion channels
powertrain = Powertrain(config)
instant = powertrain.evaluate([0.6, 0.6, 0.6, 0.6])
for _ in range(100):
    endpoint = powertrain.step([0.6] * 4, dt_s=0.1, airspeed_m_s=0.0)
report = powertrain.telemetry()  # JSONable parameters, provenance, states and audits
```

At the initial default state and four duties of 0.6, the reference result is
approximately **15.2041045435 V**, **24.0811553437 A**, and **3.12363726 N per rotor**.
At four duties of 1, it is approximately 12.7995849194 V, 74.1753141802 A, and
5.83801860 N per rotor. These are synthetic outputs, not hardware specifications.
The latter corresponds to about 24.7 C per synthetic 1.5-Ah cell: it is expressly
**not** a validated high-C extrapolation from the electrochemical research core.

`evaluate(duties)` changes the last reported load but never time, SOC, temperature
or integral ledgers. `step` returns an endpoint `PowertrainOutput`, whose arrays
are independent read-only copies. `PowertrainOutput.as_dict()` and `telemetry()`
are JSON serializable. `cell_currents_a`, `cell_temperature_k`, and `soc` have
shape `(series, parallel)`; rotor vectors have length four. Thrust and aerodynamic
reaction-torque outputs are positive magnitudes; vehicle geometry and rotor
rotation direction determine their body-frame signs elsewhere.

A scalar is permitted for a cell property and explicitly broadcasts to every
cell. An array must have the exact `(S, P)` shape; arbitrary broadcasting is
rejected. For example:

```python
varied = Powertrain(PowertrainConfig(
    series=2, parallel=3,
    initial_soc=[[0.89, 0.80, 0.83], [0.88, 0.82, 0.91]],
    cell_capacity_ah=[[1.4, 1.5, 1.6], [1.5, 1.3, 1.7]],
    cell_resistance_ohm=[[0.02, 0.03, 0.04], [0.025, 0.02, 0.03]],
    cell_harness_resistance_ohm=[[0.001, 0.003, 0.002], [0.002, 0.004, 0.001]],
))
```

All configured parameter values, including expanded per-cell arrays and initial
states, are included in telemetry. Arrays supplied by a caller are copied at
construction; later changes to the caller's array cannot alter the model.

## Pack topology and exact instantaneous conservation

The topology is **S series groups of P parallel cell branches**, not P independent
series strings. Every group carries the same terminal current `I`. In branch
`(s,p)`, the source is

`E_sp(z) = E_empty,sp + (E_full,sp - E_empty,sp) z_sp`.

The branch resistance `R_sp` is its cell internal resistance plus its own harness
resistance. The latter's heat is outside the cell thermal node. Define

- `G_s = sum_p(1 / R_sp)`
- `R_s = 1 / G_s`
- `E_s = sum_p(E_sp / R_sp) / G_s`
- `V_s = E_s - I R_s`
- `i_sp = (E_sp - V_s) / R_sp`
- `V_bus = sum_s(V_s) - I R_shared`

Thus `sum_p(i_sp) = I` independently in every group. Unequal cell OCVs produce
**circulating currents even at zero external load**; equal-current sharing is
not assumed. A negative branch current charges that cell. No external charging,
active balancing, diode or disconnect model is included.

The identity

`sum(E_sp i_sp) = V_bus I + sum(i_sp² R_internal,sp)
                + sum(i_sp² R_branch_harness,sp) + I² R_shared`

is checked numerically, including circulating-current cases. No loss is silently
folded into an efficiency factor. Internal cell resistance is constant, so this
baseline predicts heat but does not feed temperature back into electrical
resistance, OCV or capacity. It has no relaxation, hysteresis, diffusion,
electrochemical polarization, ageing, entropy/reversible heat, inter-cell thermal
conduction, abuse, protection electronics or safety certification.

## ESC, motor and static propeller

Each ESC is a passive, averaged ideal buck converter with a lumped conduction
resistance `R_ESC`. Duty is constrained to `[0, 1]`. The motor is a **quasi-steady
DC equivalent**, with winding resistance `R_m`, viscous drag `b`, and one coherent
SI constant `k = k_t = k_e`:

- `d V_bus = (R_m + R_ESC) i_m + k omega`
- `k i_m = Q_prop + b omega`
- `I_ESC,in = d i_m`

No motor inertia, winding inductance, commutation, switching ripple, ESC latency,
startup/stall transient, iron loss, cogging, regenerative braking, motor/ESC
thermal state, or current-limiter dynamics are predicted. A duty step causes an
instantaneous quasi-steady speed change; it is not a claimed motor step response.

For rotation frequency `n = omega / (2 pi)` and diameter `D`, the static laws are

- `T = C_T rho n² D⁴`
- `Q_prop = C_Q rho n² D⁵`
- `P_rotor = Q_prop omega`; therefore `C_P = 2 pi C_Q`

Eliminating current produces a positive quadratic in `omega`. The implementation
uses its cancellation-resistant nonnegative root. The total bus current is the
sum of the four ESC input currents. Bus voltage solves the monotone passive-load
equation `V + R_pack I_load(V) - E_pack = 0` on `[0, E_pack]` with safeguarded
Newton iterations and a `1e-12 V` residual tolerance. Failure after 64 iterations
is an explicit error, not a best-effort output.

Per-channel power accounts for ESC `i_m² R_ESC`, motor copper `i_m² R_m`, viscous
`b omega²`, and rotor shaft `Q_prop omega` power. `power_balance_error_w` reports
chemical-source power minus every one of these terms and all pack losses.

The constructor also rejects static coefficients whose required shaft power is
below the ideal isolated actuator-disk lower bound:

`2 pi C_Q >= C_T^(3/2) sqrt(2/pi)`.

This necessary energetic constraint does **not** make the coefficients a measured
or aerodynamically sufficient model. The constant coefficients only describe a
synthetic static/hover surrogate. Forward flight, axial inflow, vortex-ring state,
blade-element physics, propwash interaction, ground effect, Reynolds/Mach changes
and windmilling are unsupported. The `airspeed_m_s` argument changes cooling only;
using the same static thrust in moving-flight demonstrations is an explicit model
limitation, not evidence for a dynamic propeller map.

## SOC, thermal integration and audit ledgers

Positive branch current is discharge:

`dz_sp/dt = -i_sp / (3600 capacity_Ah,sp)`.

Cell lumped thermal nodes obey

`C_thermal,sp dT_sp/dt = i_sp² R_internal,sp - h(v)(T_sp - T_ambient)`

with synthetic `h(v) = cooling_w_k + airspeed_cooling_w_k_per_m_s * v`.
The coefficient has units W/K per cell, not W/(m² K). No unreported area is used.
Branch/shared harness heat, motor/ESC losses and rotor work are recorded separately
and are not injected into cell temperature.

SOC is solved by implicit midpoint with a 32-iteration limit and `2e-14` midpoint
SOC-change tolerance. Thermal integration uses the equivalent closed-form
midpoint solution with midpoint electrical heating. A monotone-cooling condition
`dt h / (2 C_thermal) <= 1` is enforced in addition to the configured maximum step.
Every state and load at the midpoint and endpoint must stay within the declared
domain. A failed step leaves time, state, last output and all ledgers unchanged.
No SOC/current/temperature clipping masks a domain exit.

The linear source curve admits an independent stored-energy difference:

`Delta U_source = sum(capacity_C * (z_initial - z_final)
                     * [E_empty + 0.5 (E_full - E_empty)(z_initial + z_final)])`.

Using midpoint source voltage/current makes this difference agree, to solver and
floating-point tolerance, with integrated chemical-source power and the sum of
integrated pack losses, motor/ESC losses and rotor shaft work. This is energy of
the synthetic source constitutive relation, **not** a measured cell free energy.
The state-based thermal audit compares `C (T_final - T_initial)` against integrated
cell Joule heating minus cooling. Signed per-cell charge and each group's total
charge are audited independently. Endpoint power must not be multiplied by `dt`
and mistaken for the internally integrated midpoint energy.

## Defaults and bounded domains

All entries are synthetic. Bounds are conservative software operating envelopes,
not physical ratings, recommended battery limits, or validated parameter support.

| Parameter | Default | Accepted configuration range |
|---|---:|---:|
| Series groups / cells per parallel group | 4 / 2 | integer 1–12 each |
| Cell capacity, Ah | 1.5 | 0.1–20 |
| Cell internal resistance, ohm | 0.020 | 0.0001–1 |
| Per-cell harness resistance, ohm | 0.001 | 0–0.2 |
| Shared harness resistance, ohm | 0.006 | 0–1 |
| Cell thermal capacitance, J/K | 45 | 1–1000 |
| Initial SOC | 0.90 | 0.05–1 |
| Initial/ambient temperature, K | 298.15 | 273.15–333.15 |
| OCV empty/full endpoint, V | 3.1 / 4.2 | 2–4 / 2.1–4.5, full > empty |
| Base cell cooling, W/K | 0.12 | 0–10 |
| Airspeed cooling gain, W/K per m/s | 0.02 | 0–1 |
| Motor resistance, ohm | 0.060 | 0.0001–2 |
| Motor constant, N m/A = V s/rad | 0.0045 | 0.0005–0.1 |
| Motor viscous drag, N m s | 0.000001 | 0–0.01 |
| ESC conduction resistance, ohm | 0.008 | 0–0.5 |
| Propeller diameter, m | 0.127 | 0.025–0.5 |
| Static thrust coefficient | 0.11 | 0.001–1 |
| Static torque coefficient | 0.012 | 0.0001–0.2, plus disk-power check |
| Air density, kg/m³ | 1.225 | 0.8–1.5 |
| Maximum step, s | 0.1 | 0.00001–1 |

At runtime, every duty must be finite and in `[0,1]`, with exactly four entries.
Every cell SOC must be in `[0.05,1]`, temperature in `[273.15,333.15] K, and signed
current in `[-60,60] A`; motor current must not exceed 60 A and speed must not
exceed 5000 rad/s. Every series-group voltage must be positive. `dt` must lie in
`[1e-9, configured_max_step]` s and cooling airspeed in `[0,50]` m/s. NaN, infinity,
complex numbers, boolean parameters and malformed shapes are rejected. Legal
individual parameter values can still form a combination that is rejected under
load or fails midpoint convergence; there is no claim that every Cartesian
combination is usable. Decrease the step where the solver or cooling guard asks;
do not treat a rejected operating state as an invitation to extrapolate it.

## Verification and next physical evidence

Run:

```sh
.venv/bin/pytest -q tests/test_fpv_powertrain.py
.venv/bin/ruff check src/physical_fpv/fpv/powertrain.py tests/test_fpv_powertrain.py
```

The focused suite includes analytical series/parallel equivalents; heterogeneous
KCL/KVL and power; zero-load equalization and its exact exponential convergence;
capacity/resistance counterexamples to uniform sharing; ESC/motor/CT/CQ balances;
shared-bus coupling; power/charge/thermal ledgers under a changing load; analytic
thermal second-order convergence; atomic rejection; immutable output-state
separation; determinism; and parameter/domain counterexamples. No test substitutes
for measured pulse-voltage, individual cell current/temperature, or measured
motor/ESC/propeller data. Qualified dynamic propeller maps, motor step/current
measurements, pack topology/fixture characterization, cooling boundaries,
parameter uncertainty and independent held-out tests remain necessary before
hardware prediction.

## Equation references (not parameter provenance)

- University control tutorial, [DC Motor Speed Modeling](https://www2.ensc.sfu.ca/people/faculty/saif/ctm/examples/motor/motor.html): torque/current and back-EMF/speed relationships. The implemented motor is its zero-inertia/zero-inductance equilibrium specialization with an added propeller load, not a BLDC switching model.
- Dantsker, Caccamo, Deters and Selig, [Performance Testing of Aero-Naut CAM Folding Propellers](https://m-selig.ae.illinois.edu/pubs/DantskerCaccamoDetersSelig-2020-AIAA-Paper-2020-2762-CamPropsTesting.pdf), 2020, data-reduction equations: the nondimensional CT and CP conventions and `P = 2 pi n Q`; CQ here follows algebraically from CP.
- NASA Glenn, [Propeller Thrust](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/propeller-thrust/): ideal actuator-disk momentum relations. The static shaft-power lower bound used here is derived from those relations at zero freestream speed.

These references support equation conventions only. Their experiments, numerical
values and validation status are not transferred to the synthetic fixture.
