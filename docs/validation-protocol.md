# Predeclared benchmark protocol v1

Written 2026-10-07 before first model-to-measurement comparison. Thresholds are research acceptance targets, not safety or certification claims. A failed gate must remain failed in reports; do not tune thresholds after looking at results.

## Frozen model and no-fitting policy

PyBaMM 26.9.0.0, unmodified Chen2020, DFN primary. SPM and SPMe are reduced-model comparisons. Run constant current 0.5, 2.5, 5, and 7.5 A to 2.5 V at 298.15 K using Chen2020's published initial concentrations, without SOC adjustment or fitting to these traces. These initial concentrations correspond to the paper's fully charged state, not an asserted thermodynamic 100% SOC. Use no initial-voltage alignment. Raw discharge steps 7, 12, 17 and 22 only; step 2 is partial preconditioning and excluded. Current is nominal protocol, not fitted. Compare measured Step Time directly to model time.

All three published cells were used by the original authors. Cell02 is the development/audit example and cell03/04 are held out from changes in THIS implementation, not independent scientific validation. This is a fixed-parameter public benchmark reconstruction; the original paper retuned diffusivity by rate and included relaxation in its metrics. Our errors are not directly the paper's metrics.

## Before looking at results: gates

- Every trace: time-weighted voltage RMSE <= 0.050 V, maximum absolute voltage error <= 0.300 V, delivered capacity relative error <= 5%, measured-time coverage >= 95%.
- Compare only the common measured/model time interval without extrapolation. Report coverage to penalize early termination, and compare full cutoff capacities separately. Do not crop initial/final portions to improve score.
- Capacity: integrate measured current in the selected discharge; retain raw reported capacity as an additional consistency check. Model capacity at voltage cutoff, not at last common point.
- Mesh convergence (20 -> 40 points per electrode and particle, separator 10 -> 20): common-time voltage max difference <= 0.005 V and cutoff-capacity difference <= 1%. Solver rtol/atol 1e-7; stricter tolerance audit 1e-8.
- Lithium inventory relative drift <= 1e-6; current-integral vs model discharge-capacity difference <= 1e-6 Ah; finite outputs and concentrations in physical domains throughout.
- Thermal prediction is NOT validated in this version. Lumped Chen2020 thermal values and zero entropy coefficients have not been established as a complete LG M50 thermal characterization. Show the temperature error and input assumptions if requested, but never count this as a passed gate or certify safe temperature. Isothermal runs must not label constant temperature as a prediction.

All rates/cells count. Aggregate pass requires ALL empirical gates AND numerical/physical gates, and does not establish high-current FPV, aging, abuse or materials generalization. Error-target changes require a new protocol version, a documented rationale and a new untouched dataset.
