# Thermal-electrochemical public reconstruction

Model: PyBaMM26.9.0.0 / ORegan2022 / DFN / lumped / paper h=15 W/m²/K.
No new fitting or voltage/SOC alignment. Published diffusivity corrections retained once.
Empirical targets: 6/36 cases pass.
Numerical targets: NOT RUN in this report; no convergence claim.
Independent validation: NOT ESTABLISHED. Temperature is a surface-proxy comparison.
Parameter-temperature extrapolations and raw quality flags remain visible.

| Cell | Ambient°C | C-rate | V RMSE mV | T RMSE K | Energy err | Empirical | Numerical |
|---|---:|---:|---:|---:|---:|---|---|
| 785 | 0 | 0.5 | 69.91 | 1.78 | 7.26% | FAIL | NOT_RUN |
| 786 | 0 | 0.5 | 71.95 | 1.18 | 7.46% | FAIL | NOT_RUN |
| 787 | 0 | 0.5 | 74.07 | 1.11 | 7.86% | FAIL | NOT_RUN |
| 788 | 0 | 0.5 | 74.62 | 1.10 | 8.32% | FAIL | NOT_RUN |
| 789 | 0 | 1 | 46.06 | 3.86 | 2.87% | FAIL | NOT_RUN |
| 790 | 0 | 1 | 32.33 | 1.20 | 0.56% | PASS | NOT_RUN |
| 791 | 0 | 1 | 32.39 | 13.93 | 0.46% | FAIL | NOT_RUN |
| 792 | 0 | 1 | 32.77 | 1.93 | 0.26% | PASS | NOT_RUN |
| 793 | 0 | 2 | 88.00 | 0.64 | 12.92% | FAIL | NOT_RUN |
| 794 | 0 | 2 | 86.88 | 1.42 | 12.89% | FAIL | NOT_RUN |
| 795 | 0 | 2 | 82.46 | 1.58 | 12.23% | FAIL | NOT_RUN |
| 796 | 0 | 2 | 74.64 | 0.67 | 10.92% | FAIL | NOT_RUN |
| 785 | 10 | 0.5 | 53.48 | 1.20 | 3.04% | FAIL | NOT_RUN |
| 786 | 10 | 0.5 | 54.48 | 0.81 | 3.18% | FAIL | NOT_RUN |
| 787 | 10 | 0.5 | 57.94 | 0.82 | 3.65% | FAIL | NOT_RUN |
| 788 | 10 | 0.5 | 60.60 | 0.79 | 4.20% | FAIL | NOT_RUN |
| 789 | 10 | 1 | 27.22 | 2.49 | 0.67% | FAIL | NOT_RUN |
| 790 | 10 | 1 | 28.69 | 0.35 | 0.95% | PASS | NOT_RUN |
| 791 | 10 | 1 | 28.47 | 14.37 | 0.78% | FAIL | NOT_RUN |
| 792 | 10 | 1 | 32.37 | 0.76 | 1.17% | PASS | NOT_RUN |
| 793 | 10 | 2 | 82.20 | 2.72 | 11.18% | FAIL | NOT_RUN |
| 794 | 10 | 2 | 82.49 | 1.36 | 11.22% | FAIL | NOT_RUN |
| 795 | 10 | 2 | 81.16 | 1.46 | 11.08% | FAIL | NOT_RUN |
| 796 | 10 | 2 | 74.35 | 2.02 | 10.11% | FAIL | NOT_RUN |
| 785 | 25 | 0.5 | 38.77 | 0.81 | 1.98% | FAIL | NOT_RUN |
| 786 | 25 | 0.5 | 36.18 | 0.72 | 1.82% | FAIL | NOT_RUN |
| 787 | 25 | 0.5 | 30.29 | 0.76 | 1.36% | PASS | NOT_RUN |
| 788 | 25 | 0.5 | 24.51 | 0.79 | 0.82% | PASS | NOT_RUN |
| 789 | 25 | 1 | 44.88 | 1.46 | 2.19% | FAIL | NOT_RUN |
| 790 | 25 | 1 | 53.56 | 1.07 | 3.47% | FAIL | NOT_RUN |
| 791 | 25 | 1 | 51.54 | 14.68 | 3.13% | FAIL | NOT_RUN |
| 792 | 25 | 1 | 54.12 | 1.11 | 3.46% | FAIL | NOT_RUN |
| 793 | 25 | 2 | 76.09 | 5.60 | 8.23% | FAIL | NOT_RUN |
| 794 | 25 | 2 | 77.29 | 5.35 | 8.28% | FAIL | NOT_RUN |
| 795 | 25 | 2 | 76.00 | 5.26 | 8.09% | FAIL | NOT_RUN |
| 796 | 25 | 2 | 73.47 | 5.03 | 7.47% | FAIL | NOT_RUN |

## Inspect the evidence

The JSON includes cutoff/coverage, physical audits, domain breaches, raw quality flags,
initial temperatures, source hashes and mesh/tolerance checks. Each case has model
time-series and common-interval residual CSVs. Failed cases are never removed.

The 36 files represent12 cells reused across temperatures. Cell791 is retained with
the source's exclusion/sensor-anomaly warning. Cold runs and high-current heating
cross measured property domains. No claim of core-temperature accuracy or safety.

Chen2020 baseline failures remain independently preserved.
