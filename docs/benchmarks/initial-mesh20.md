# Battery benchmark report

Protocol: fixed-chen2020-v1
Model: DFN / Chen2020 / isothermal
Empirical gate: FAIL
Numerical gate: FAIL / NOT RUN
Thermal validity: NOT ESTABLISHED

No fitting. These are original-study benchmark data, not independent validation.
Failed thresholds are retained. Isothermal temperature is imposed, not predicted.

| Cell | C-rate | RMSE (mV) | Max error (mV) | Capacity error | Coverage | Gate |
|---|---:|---:|---:|---:|---:|---|
| 02 | 0.1 | 60.91 | 295.03 | 1.66% | 100.00% | FAIL |
| 02 | 0.5 | 62.23 | 272.59 | 1.86% | 100.00% | FAIL |
| 02 | 1 | 44.25 | 71.25 | 0.17% | 100.00% | PASS |
| 02 | 1.5 | 39.46 | 153.78 | 1.43% | 98.56% | PASS |
| 03 | 0.1 | 60.04 | 283.95 | 1.57% | 100.00% | FAIL |
| 03 | 0.5 | 60.21 | 272.85 | 1.86% | 100.00% | FAIL |
| 03 | 1 | 38.26 | 64.59 | 0.07% | 100.00% | PASS |
| 03 | 1.5 | 35.34 | 171.83 | 1.62% | 98.38% | PASS |
| 04 | 0.1 | 62.35 | 306.93 | 1.75% | 100.00% | FAIL |
| 04 | 0.5 | 58.75 | 263.48 | 1.77% | 100.00% | FAIL |
| 04 | 1 | 36.58 | 62.27 | 0.14% | 100.00% | PASS |
| 04 | 1.5 | 33.71 | 163.22 | 1.44% | 98.56% | PASS |

## Limits

- Chen thermal properties contain generic defaults; no validated thermal claim.
- The original study retuned diffusivity by rate; this benchmark does not.
- Not validated for pulses, high-C FPV loads, packs, aging, abuse or safety.
- Full provenance, termination, coverage and physical audits are in report.json.
- Do not interpret a solver or software-test pass as experimental agreement.
