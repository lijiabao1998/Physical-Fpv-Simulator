# Frozen FPV completion protocol, 2026-10-11

Base: 1990e23ce35b16d73d2d65b0d9a586064963dd6a. Isolated candidate only.
Existing Chen, thermal and Stanford data, parameters, failures and core current
limits are unchanged. No data fitting, actual aircraft, paid compute, deployment
or independent physical-validity claim is authorized by this implementation.

Acceptance is divided into executable software, physical accounting, numerical
agreement, and empirical validity. The last gate is **NOT ESTABLISHED** for every
new FPV component. Default cell, pack, motor, propeller, frame, controller and
contact parameters are explicitly synthetic engineering test fixtures.

Required new executable path: controls -> controller -> pack/ESC/motor/propeller
circuit -> rigid body -> camera and GUI. Coupling must solve terminal voltage and
load together, report cell currents/heat/SOC and support series/parallel variation.
Checks: Kirchhoff current/voltage, power and charge/thermal accounting, analytical
hover/free fall, torque directions, dt refinement, invalid inputs and replay.
No silent high-current use of the prior electrochemical core is allowed.

Materials: an explicit provenance-aware parameter-to-PyBaMM boundary and bounded
SPM identity-reconstruction example. An optional ASE EMT fcc-Al EOS calculation
is a real interatomic empirical-potential calculation, not DFT, Li transport or
battery material qualification. Export cannot become a battery diffusivity.
A geometry/porosity mapping is theoretical and must retain assumptions.

Compute limits: normal unit tests < 10 minutes; one SPM bridge demonstration
< 60 simulated seconds; optional EMT EOS <= 11 strain points, <= 108 atoms.
No expensive DFN cohort reruns. Existing data-gated tests may be skipped if exact
raw data are absent. UI test uses the assistant's own cloud browser; physical
joystick hardware is not present, so browser Gamepad API can be exercised with
synthetic events only and cannot be labelled real-device validation.
