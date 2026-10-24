# G08 candidate evidence, not release acceptance

Base: G07 7b0170f7e1b4848b6405abd21e0c6fd526e72fef. Research PRs #1–3 untouched.

## Implemented
Synthetic motor inertia 1.2e-6 kg m² plus a thin-rod prop approximation m D²/12.
One-quadrant ESC, synthetic 60 A per-motor current ceiling, no regenerative braking.
Midpoint motor speed and midpoint SOC solve close electrical energy with rotor kinetic storage.
Maximum electrical substep 1/1920 s; game remains 240 Hz.
Average substep thrust/reaction torque drives the single Rapier body.
Displayed rpm is endpoint speed, forces are interval means; instantaneous last substep powers are not interval means.
Rotor angular momentum supplies gyroscopic moment. Rotor relative-motion energy accounting is not a proof of fully coupled airframe/rotor absolute kinetic-energy conservation.
G07 solver remains byte-identical; original Python fixture hashes unchanged.
Replay includes physics version; missing version routes to legacy G07.
Physics menu offers explicit G07 rollback, restarting the flight; best times use separate versioned keys.

## First failures retained
1. Initial build caught an unused INITIAL_SOC import. Removed unused import, without changing tests.
2. Follow-up UI build caught unused G07_MODEL import; removed.
3. Own-cloud Vite startup denied OS interface enumeration (uv_interface_addresses).
   This did not execute browser tests. Official existing Player workflow will run actual Chromium.

## Verified locally
59 tests in six files, strict TypeScript/build and original five Python trajectories.
New tests include 10 s variable duty energy/charge/thermal ledger, startup/current ceiling/coast,
atomic rejected steps, independent fine RK4 motor ODE convergence, 120/240/480 Hz flight comparisons,
deterministic same-runtime replay, legacy routing and pause/disarm semantics.
Machine-readable new numerical output is produced by npm test at web/numerical-results/g08-transients.json.
Old test sources and numerical fixture files are unchanged.

## Pending / explicitly not validated
Official Chromium screenshots and desktop/mobile viewport performance.
Xbox USB/Bluetooth and DualSense USB/Bluetooth: no physical devices, NOT RUN.
Physical desktop-controller flight and actual phone thermal/performance: NOT RUN.
No aerodynamic blade-stall or jammed-rotor contact model is claimed; startup zero-speed/current-limited tests are not a sustained locked-rotor experiment.
Hardware battery measurement comparison remains unresolved research, not this candidate's success.
No merge, release, public deployment or new empirical discovery is claimed.
