# FPV executable candidate: what is actually completed

This isolated candidate builds on research head `1990e23`. **No main merge,
remote publication, deployment, new battery experiment or qualified aircraft
claim is part of this result.** Every old scientific failure is retained.

## Run from source (Python 3.12, Linux CPU)

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-lock.txt
pip install --no-deps -e .
# optional empirical atomistic reference (exact tested add-on versions)
pip install -r requirements-fpv-runtime-lock.txt
python -m physical_fpv.fpv.server
# optional actual EMT reference density -> hypothetical frame mass -> flight
python -m physical_fpv.fpv.server --emt-frame
# bounded deterministic simulation and exact local replay
python -m physical_fpv.fpv demo --out results/fpv-demo-replay.json
python -m physical_fpv.fpv replay --input results/fpv-demo-replay.json --out results/replay.json
python -m physical_fpv.fpv material --out results/material-mesh-evidence.json
python -m physical_fpv.fpv atom --out results/atomistic-emt-reference.json
pytest -q tests/test_fpv_*.py
```

Open the printed localhost URL. The desktop input is sliders or keyboard;
Gamepad API is implemented but hardware validation is **NOT RUN**. The server
uses only local CPU and binds only 127.0.0.1. It is a local candidate, not a
publicly hosted site. A wheel includes the HTML asset through MANIFEST.in.

## Architecture gaps now covered

| Original figure block | Added executable implementation | Remaining evidence boundary |
|---|---|---|
| B: material → solver interface | Fresh SPM material bridge, source/phase/SI/domain guards, actual solves | Supplied sources are not independently qualified |
| D: atomic/material solver | ASE EMT fcc-Al EOS, raw arrays/hash, geometry→frame mass | No DFT/NEB/Li transport or battery-material validation |
| D: multiscale | Explicit porosity/tortuosity/active volume and conversion contracts | Theoretical mapping only; independent factors and electrode data needed |
| D: cell→pack | Heterogeneous S×P circuit, current redistribution, cell heat/SOC, harness loss | Synthetic constitutive values; no real racing pack |
| D: load/propulsion | Coupled bus voltage, ESC buck, DC equivalent, static CT/CQ propeller | No measured motor map, rotor inertia or forward-flight inflow map |
| D: flight/controller | Newton–Euler RK4, quaternion, angle/rate control, wind/body drag | Synthetic mass/inertia/drag/controller; no held-out flight data |
| D: environment/FPV/GUI | Deterministic scene/contact, perspective FPV/chase, live inputs/replay | Geometric contact and camera; no optical/device calibration |
| Thermal/physical validation | Separate analytical, conservation, convergence, retained empirical re-gating | Existing 30/36 ORegan failures are unresolved; all-36 raw traces unavailable locally |

See [powertrain equations and domains](fpv-powertrain.md), [flight and input
models](fpv-flight.md), [materials and numerical failure](fpv-materials.md), and
[thermal audit](fpv-thermal-validation-audit.md). The homogeneous electrochemical
pack-load adapter is separately documented; it does not overwrite the interactive
synthetic heterogeneous model or promote its validation level.

## Important limitations

- A synthetic module can be implemented and conservation-tested while empirical
  qualification is still absent. These labels are separate in every output.
- The original core current limits stay Chen 0.5–7.5 A and ORegan 0.5–10 A.
  Synthetic high-current pack examples do not change or validate that domain.
- Isothermal temperature is imposed. A synthetic lumped cell mean is not a skin
  thermocouple prediction. Reversible electrochemical heat, thermal gradients,
  motor/ESC temperatures and inter-cell conduction are not silently invented.
- The whole flight coupling uses time splitting; isolated RK4 does not make the
  whole chain fourth-order. Static propeller physics limits forward-flight claims.
- Replay is same-environment deterministic reconstruction; exported state/inputs
  include a checksum, but no one should call replay an independent experiment.

## Experimental data needed next

A qualified next step needs the actual intended cell/pack topology and dimensions,
independent synchronized pulse current/voltage with initial inventory and thermal
history, interior/surface temperature sensors and uncertainty, known airflow and
fixture cooling, calibrated motor/ESC/propeller maps, frame mass/inertia, and
held-out synchronized control/IMU/pose logs. Parameter identification must use a
development partition separate from the held-out verification cases. No fitting
has been done merely to turn existing failures green.

## Checked evidence

[Actual GUI screenshot](fpv-evidence/fpv-gui-final.png), [browser checks](fpv-evidence/browser-verification.json), [actual GUI replay](fpv-evidence/fpv-gui-replay-verification.json), [thermal audit](fpv-evidence/fpv-thermal-audit.json), [electrochemical pack solve](fpv-evidence/fpv-electrochemical-pack.json), and [source-hashed audit receipt](fpv-evidence/candidate-audit.json).
