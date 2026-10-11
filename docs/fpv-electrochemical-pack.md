# Bounded electrochemical cell → homogeneous pack → motor-load bridge

## What is now executable

`physical_fpv.fpv.electrochemical_pack` couples a real **PyBaMM Chen2020 single
particle model (SPM)** to a homogeneous series/parallel pack and the existing
synthetic ESC/DC-motor/static-propeller equations. The electrochemical current is
an **algebraic unknown solved simultaneously with the cell voltage and motor
load**. It is not a prescribed current trace, an empirical resistance battery,
or a one-step-lagged voltage/current exchange.

This is a separate bounded demonstration. It does not modify `core.py`, original
acceptance thresholds, existing empirical failures, the heterogeneous synthetic
`Powertrain`, or the flight simulator. A working connection and conservation
identities do **not** establish agreement with battery/pack/propeller measurements.
The output retains `empirical_gate = "NOT ESTABLISHED"` and `validity_uplift = false`.

## API

```python
from physical_fpv.fpv.electrochemical_pack import (
    ElectrochemicalPackConfig,
    solve_electrochemical_pack,
)

# Four equal synthetic motor/propeller channels, homogeneous Chen2020 4S2P.
result = solve_electrochemical_pack([0.35] * 4)
assert result["physical_audit"]["passed"]

# Continuous piecewise-linear duty ramp, with independently commanded motors.
result = solve_electrochemical_pack(
    [[0.30] * 4, [0.43, 0.40, 0.38, 0.36]],
    duty_times_s=[0.0, 10.0],
    config=ElectrochemicalPackConfig(duration_s=10, mesh_points=40),
)
```

Default duration is 10 s, output interval at most 0.1 s, internal solver maximum
step 0.1 s, radial particle meshes 40 points, and relative/absolute tolerance
`1e-8`. IDAKLU uses one thread with a 10,000-internal-step bound. The supported
maximum duration is **30 simulated seconds**, with mesh size 10–80 and numerical
tolerance `1e-9`–`1e-5` inherited from the original Chen research envelope. This is
not a long-duration pack performance, endurance, or flight simulation.

Schedules have 2–61 strictly increasing knot times, start at 0, end exactly at
`duration_s`, and have four duties at every knot. All requested knot times appear
in the output. Duties interpolate **linearly**, so this interface describes
ramps, not discontinuous command steps. Constant duties are supplied as a
four-element vector. Each duty is finite and in `[0, 1]`; usable combinations
must additionally satisfy the electrochemical and motor domains.

The result is JSON-serializable and includes time, representative-cell terminal
voltage/current, pack bus voltage/current, bulk OCV, four thrust/torque/speed
traces, motor and ESC currents, cell and pack terminal charge, terminal power,
downstream loss powers, numerical audits, configuration, parameter fingerprint,
source provenance and a content SHA256. `cpu_time_s` is a diagnostic excluded
from the reproducible content hash. Arrays are detached lists.

## Electrochemical equations and provenance

The stock PyBaMM SPM solves spherical solid-phase lithium diffusion in one
representative negative and one positive electrode particle, with interfacial
flux tied to the simultaneously solved current and Butler–Volmer electrode
kinetics determining polarization. This includes nonuniform radial
concentrations and time-dependent voltage sag. It does not resolve the
electrolyte concentration gradients and electrolyte transport polarization of
SPMe/DFN. SPM agreement with its own equations is not evidence of accuracy under
large FPV current transients.

Electrode concentrations, geometry, active-material fractions, diffusion and
kinetic parameters come from PyBaMM's published **Chen2020 LG M50 reconstruction**.
The model starts from those parameter-set concentrations. There is no fitted SOC,
invented capacity increase, atom arrangement → capacity shortcut, inferred racing
LiPo parameter mapping, or internal empirical resistance added on top of the
electrochemical voltage.

The code uses PyBaMM's callable `operating mode`, implemented by the installed
`pybamm.external_circuit.FunctionControl` with algebraic control. IDAKLU computes
consistent initial conditions and advances the coupled differential–algebraic
system. The initial current value of 0.5 A is a numerical initial guess, not a
prescribed current. The unused default `Current function [A]` entry in the
parameter set likewise does not set the actual current in this operating mode.

Optional `estimates=((electrode, phase, estimate), ...)` uses the existing
`PropertyEstimate.electrode_mapping` admission checks unchanged: only chemical
diffusivity, non-analytical evidence class, a matching phase, intrinsic-particle
scope, full requested stoichiometry support, and exactly the evaluation
temperature are accepted. Duplicate electrode overrides are rejected. An
analytical jump-network/tracer example cannot silently become a Chen diffusivity.
Source/structure hashes and caller-supplied estimates are recorded. Passing these
input checks does not independently verify an experiment or atomistic calculation.

Equation/implementation references:

- Chen et al., [Development of Experimental Techniques for Parameterization of
  Multi-scale Lithium-ion Battery Models](https://doi.org/10.1149/1945-7111/ab9050),
  2020: source of the Chen2020 cell parameter reconstruction.
- Sulzer et al., [Python Battery Mathematical Modelling (PyBaMM)](https://doi.org/10.5334/jors.309),
  2021: battery-model implementation framework. The executed version is recorded
  in each result (tested here with 26.9.0.0).
- The installed PyBaMM `lithium_ion.SPM`, `external_circuit.FunctionControl`, and
  `IDAKLUSolver` source were checked directly for this implementation; no new
  dataset, fitted coefficient, or network-acquired material property is used.

## Homogeneous pack circuit

`Ns` identical series groups each contain `Np` identical parallel cells. They
share exactly the same initial state, temperature, electrochemical parameters,
branch harness resistance and current. A single representative electrochemical
cell is therefore sufficient under these **imposed symmetry assumptions**.

For positive discharge current:

```
Ipack = Np Icell
Rh = Rshared + Ns Rbranch / Np
Vbus = Ns Vcell - Rh Ipack
```

`Vcell` is the electrochemical cell terminal voltage, before its branch harness.
`Rbranch` is one cell's external harness resistance. The shared and branch
losses are recorded separately:

```
Pbranch = Ns Np Icell² Rbranch
Pshared = Ipack² Rshared
Pcell_terminals = Ns Np Vcell Icell
Pcell_terminals = Vbus Ipack + Pbranch + Pshared
```

The representative cell's integrated discharged charge is `Qcell = ∫Icell dt`.
Pack terminal charge is `Qpack = Np Qcell`, **without an Ns multiplier**. The
charge of all individual cells summed together is a different quantity.

This bridge has no manufacturing variation, circulating currents, unequal SOC,
unequal branch cooling, balancing, BMS or weakest-cell protection simulation.
The existing synthetic heterogeneous `Powertrain` remains a distinct model; its
unequal-current results cannot be relabeled as electrochemical-pack predictions.

## Motor load and simultaneous constraint

All downstream coefficients are the **same invented defaults** and equations
documented in [the synthetic powertrain specification](fpv-powertrain.md), with
the same admissible ranges and static actuator-disk power lower-bound check.
That document provides the DC motor, nondimensional propeller and momentum
theory equation sources. None of those sources supplies measured coefficients
for this bridge. Tests compare the symbolic/numerical bridge expression against
the original `Powertrain._motors` implementation.

For each rotor `j`, with `n = omega/(2 pi)`:

```
T = CT rho n² D⁴
Qprop = CQ rho n² D⁵
d_j Vbus = (Rm + Resc) im_j + k omega_j
k im_j = Qprop_j + b omega_j
Iesc_j = d_j im_j
```

Eliminating motor current gives the same cancellation-resistant positive
quadratic root used by `Powertrain`. The algebraic SPM current equation is

```
0 = Icell - sum_j(d_j im_j(Vbus)) / Np
```

Since `Vbus` itself depends on `Icell` and the electrochemical `Vcell`, voltage
sag, shared-bus loading and instantaneous cell current are solved together.
There is no hold-last-voltage or fixed-point coupling lag to tune.

The motor is a zero-inertia/zero-inductance quasi-steady DC equivalent with an
averaged buck ESC. Static constant CT/CQ has no advance-ratio, Reynolds, inflow,
propwash, ground-effect or forward-flight map. No claims are made about BLDC
commutation, motor startup, ESC switching, rotor transient response or measured
thrust accuracy. Raising one duty can lower the other motors' thrust through
electrochemical and harness bus sag, even though all propeller coefficients
remain synthetic.

## Domain guards and verification meaning

- Representative-cell current must remain **0.5–7.5 A**, preserving the Chen
  research envelope. For the published 5-Ah nominal cell this is at most 1.5 C,
  not racing-FPV high-C qualification. Zero/idle pack current and charging are
  deliberately unsupported, despite some commands being numerically admissible.
- Temperature is imposed at **298.15 K exactly**. Other temperature inputs are
  rejected. There is **no predicted cell temperature, electrochemical heat,
  pack thermal transient, cooling validation or safety claim** in this bridge.
  Harness/motor losses are bookkeeping powers, not an added cell heat source.
- PyBaMM cell voltage/concentration termination events remain in force. Additional
  events bound cell current, positive bus voltage, motor current (60 A maximum)
  and speed (5000 rad/s maximum). Invalid initial states, early event termination,
  failed solves and sampled-domain violations raise errors. A truncated trajectory
  is never returned as a completed run, and no current is clipped to appear valid.
- Ns and Np are integers 1–12. Mesh/time settings bound work; one solve is short
  and CPU-only. No cohort sweep, dataset download or remote write is performed.

The audit checks pack KCL, motor KVL and terminal electrical power closure, with
ESC, winding, viscous, propeller and harness powers separately accounted for.
It compares PyBaMM's integrated current against **both independent electrode
lithium inventory changes multiplied by Faraday's constant**, and also checks
total lithium conservation. This is not just `Q = Q` using the same integral
twice. The power balance begins at the cell terminals: it does not establish a
cell chemical/free-energy or thermal energy balance.

Numerical acceptance in `physical_audit.passed` requires KCL error below `1e-5 A`,
motor KVL error below `1e-9 V`, terminal power error below `1e-3 W`, electrode charge
error below `1e-4 C`, and total-lithium error below `1e-9 mol`. These are software
verification thresholds, not empirical accuracy or safety tolerances.

## Tests and observed refinement

```sh
.venv/bin/pytest -q tests/test_fpv_electrochemical_pack.py
.venv/bin/ruff check src/physical_fpv/fpv/electrochemical_pack.py tests/test_fpv_electrochemical_pack.py
```

The focused tests cover KCL/KVL/charge/power identities, genuine cell polarization
and time-dependent sag at constant command, changed electrochemical state under
changed duties, shared-bus cross-coupling, parallel-current sharing, linear
schedule knots, current-domain initial and in-run failures, temperature and other
invalid inputs, original motor-equation parity, provenance and content hashing.

The 10-s four-motor ramp above yields endpoint cell voltages approximately
**4.055785, 4.050690, 4.048727 V** at 20, 40 and 80 radial points, respectively.
40→80 endpoint difference is about **1.96 mV**, and integrated representative-cell
charge changes by about **0.0235 C**. Spatial error is observable and must not be
represented as negligible or as measured accuracy. Tests require the 40→80
maximum voltage difference to be below 3 mV and smaller than the 20→40 difference.
Refining the internal maximum time step from 0.5 s to 0.1 s at the same 40-point
mesh is tested separately at `2e-6 V`, `2e-5 A` and `5e-5 C` agreement. Changing
the display sampling period alone would not constitute an integration test.

The initial focused suite completed in about 8 seconds of wall time; the final
suite contains 38 tests. The bounded solves are comfortably inside the requested
four-minute computation budget. These
small bounded results close the executable connection; independent measured
pack voltage/current, motor/ESC maps, propeller performance and thermal data
remain necessary to qualify a physical FPV prediction.
