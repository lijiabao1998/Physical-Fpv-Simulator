# Battery benchmark report

Protocol: fixed-chen2020-v1
Model: DFN / Chen2020 / isothermal
Empirical gate: FAIL
Numerical gate: PASS
Thermal validity: NOT ESTABLISHED

No fitting. These are original-study benchmark data, not independent validation.
Failed thresholds are retained. Isothermal temperature is imposed, not predicted.

| Cell | C-rate | RMSE (mV) | Max error (mV) | Capacity error | Coverage | Gate |
|---|---:|---:|---:|---:|---:|---|
| 02 | 0.1 | 60.87 | 294.95 | 1.66% | 100.00% | FAIL |
| 02 | 0.5 | 62.05 | 272.24 | 1.85% | 100.00% | FAIL |
| 02 | 1 | 43.86 | 70.90 | 0.17% | 100.00% | PASS |
| 02 | 1.5 | 38.92 | 154.39 | 1.44% | 98.56% | PASS |
| 03 | 0.1 | 60.01 | 283.87 | 1.57% | 100.00% | FAIL |
| 03 | 0.5 | 60.04 | 272.50 | 1.86% | 100.00% | FAIL |
| 03 | 1 | 37.90 | 64.23 | 0.06% | 100.00% | PASS |
| 03 | 1.5 | 34.98 | 172.40 | 1.63% | 98.37% | PASS |
| 04 | 0.1 | 62.32 | 306.85 | 1.75% | 100.00% | FAIL |
| 04 | 0.5 | 58.59 | 263.13 | 1.77% | 100.00% | FAIL |
| 04 | 1 | 36.22 | 61.92 | 0.14% | 100.00% | PASS |
| 04 | 1.5 | 33.36 | 163.83 | 1.45% | 98.55% | PASS |

## Limits

- Chen thermal properties contain generic defaults; no validated thermal claim.
- The original study retuned diffusivity by rate; this benchmark does not.
- Not validated for pulses, high-C FPV loads, packs, aging, abuse or safety.
- Full provenance, termination, coverage and physical audits are in report.json.
- Do not interpret a solver or software-test pass as experimental agreement.
