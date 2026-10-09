# Six-cell boundary responses: finite-delay evidence, no resistance fit

**All 24 primary boundaries and 240 delayed observations are retained.** Each cell has different apparent ΔV/ΔI values at its four boundaries; a single constant ratio does not exactly reproduce those recorded voltage changes under the frozen internal-voltage-unchanged assumption. This is an arithmetic observation, not statistical physical falsification: measurement uncertainty is unknown, the delays differ, and relaxation/state changes contribute. A fixed resistance could still be one component of a richer electrochemical response; this inspection neither identifies it nor establishes a contact-resistance cause.

The higher k1/k6 response pattern is also visible at charging onset and at discharge termination, not only at the selected discharge onset. That broadens the recorded behavior requiring an explanation. It does not establish a manufacturing class, fixture defect, material mechanism, or model accuracy on k2–k5.

## Primary apparent ratios

Values are in mΩ, from the last pre-step sample to the first post-step sample. They are not intrinsic ohmic/contact resistance measurements.

| Cell | Charge start | CV stop (small ΔI) | Discharge start | Discharge stop | Span across the three larger-ΔI boundaries |
|---|---:|---:|---:|---:|---:|
| k1 | 75.170 | 63.440 | 61.299 | 69.653 | 13.871 |
| k2 | 47.707 | 31.877 | 31.678 | 49.936 | 18.258 |
| k3 | 47.278 | 30.790 | 32.347 | 47.813 | 15.466 |
| k4 | 43.315 | 30.704 | 28.330 | 38.652 | 14.985 |
| k5 | 43.059 | 29.155 | 28.116 | 38.973 | 14.943 |
| k6 | 75.156 | 61.371 | 60.682 | 67.522 | 14.474 |

The 13.871–18.258 mΩ spans among larger-current boundaries do not depend on discarding or trusting the small-current CV-stop ratios. They remain descriptive spans, not error bars or bounds on a resistor. The computational equal-ratio tolerance was 1e-12 Ω solely for floating-point comparison; it is not an instrument uncertainty or empirical acceptance gate.

![All six cells and four boundary responses at their recorded delays](benchmarks/stanford-six-cell-boundaries.svg)

Squares mark the primary pairs. Lines only connect the first ten actual post-step samples; no common-delay interpolation or fitted curve is used. All 60 CV-stop delayed pairs are flagged because |ΔI|<0.5 A. That denominator is approximately 0.05 A, versus approximately 1.625 A at charge start and 5 A at the discharge boundaries. The 0.5-A flag is a predeclared conditioning annotation, not a physical cutoff.

## Sampling, state and relaxation

- First observed samples occur 0.9997–1.0013 s after the inferred next commanded-step origin. Primary samples bracket gaps of 1.03870–1.141448 s. These records do not observe the zero-time voltage jump.
- Current sign is preserved: positive for charge and negative for discharge. Each ratio uses its own actual current change, not a nominal C-rate conversion.
- The approximately one-hour pre-discharge rest records zero current throughout for all six cells. Voltage still changes by roughly −10.40 to −11.73 mV from its first to last recorded samples. This does not prove equilibrium or equal electrode state.
- During the recorded final rest, voltage rises by approximately 203.81–270.10 mV after the first sampled post-discharge point. The report retains its full duration and first/last-ten trends. Relaxation makes an apparent response depend on observation time.
- Skin temperature, pre-phase charge/current/duration and both sample temperatures are retained. Skin temperature is not a cell-average model temperature; equal nominal chamber temperature does not establish equal thermal or electrochemical state.
- Voltage/current calibration, filtering, sensor uncertainty and voltage-sense/fixture geometry are not supplied by these selected records. No uncertainty interval is invented.

## All 24 primary observations

| Cell / boundary | Source Excel rows | ΔI (A) | ΔV (V) | Sample gap (s) | Post-step delay (s) | Pre / post skin (°C) | Small ΔI |
|---|---|---:|---:|---:|---:|---|---|
| k1 / charge_start | 3602 → 3603 | 1.62519836 | 0.12216592 | 1.046640 | 1.000100 | 25.1098 / 25.0993 | False |
| k1 / cv_stop | 18077 → 18078 | -0.04999144 | -0.00317144 | 1.040180 | 0.999800 | 25.1936 / 25.1948 | True |
| k1 / discharge_start | 21678 → 21679 | -5.00024033 | -0.30651021 | 1.045580 | 1.000600 | 25.1879 / 25.1879 | False |
| k1 / discharge_stop | 25069 → 25070 | 5.00035572 | 0.34828901 | 1.139080 | 1.000000 | 31.1384 / 31.1384 | False |
| k2 / charge_start | 3602 → 3603 | 1.62542152 | 0.07754326 | 1.048152 | 1.001300 | 24.3733 / 24.3733 | False |
| k2 / cv_stop | 17189 → 17190 | -0.04999220 | -0.00159359 | 1.041112 | 0.999800 | 24.4357 / 24.4357 | True |
| k2 / discharge_start | 20790 → 20791 | -5.00038195 | -0.15840149 | 1.046228 | 1.000300 | 24.4046 / 24.3934 | False |
| k2 / discharge_stop | 24226 → 24227 | 5.00040245 | 0.24969840 | 1.139968 | 0.999700 | 32.2956 / 32.3497 | False |
| k3 / charge_start | 3602 → 3603 | 1.62522221 | 0.07683730 | 1.047108 | 1.000500 | 24.7279 / 24.7391 | False |
| k3 / cv_stop | 17079 → 17080 | -0.04999082 | -0.00153923 | 1.040764 | 1.000800 | 25.0980 / 25.1054 | True |
| k3 / discharge_start | 20680 → 20681 | -5.00028038 | -0.16174555 | 1.046528 | 1.000500 | 24.5797 / 24.5797 | False |
| k3 / discharge_stop | 24099 → 24100 | 5.00035334 | 0.23908401 | 1.138904 | 1.000600 | 32.9197 / 32.9197 | False |
| k4 / charge_start | 3602 → 3603 | 1.62527370 | 0.07039905 | 1.047152 | 1.000300 | 24.4283 / 24.4283 | False |
| k4 / cv_stop | 16919 → 16920 | -0.04999157 | -0.00153494 | 1.042008 | 1.000700 | 24.5071 / 24.5286 | True |
| k4 / discharge_start | 20520 → 20521 | -5.00046968 | -0.14166212 | 1.047128 | 1.001000 | 24.4624 / 24.4624 | False |
| k4 / discharge_stop | 23967 → 23968 | 5.00024843 | 0.19326973 | 1.137904 | 0.999900 | 33.6752 / 33.6965 | False |
| k5 / charge_start | 3602 → 3603 | 1.62536335 | 0.06998682 | 1.047208 | 1.000500 | 24.7570 / 24.7570 | False |
| k5 / cv_stop | 16906 → 16907 | -0.04998197 | -0.00145721 | 1.040972 | 1.000200 | 25.1832 / 25.1832 | True |
| k5 / discharge_start | 20507 → 20508 | -5.00030041 | -0.14059067 | 1.044580 | 1.000300 | 24.6510 / 24.6180 | False |
| k5 / discharge_stop | 23956 → 23957 | 5.00016785 | 0.19487262 | 1.141448 | 1.000500 | 35.4970 / 35.4970 | False |
| k6 / charge_start | 3602 → 3603 | 1.62530327 | 0.12215114 | 1.047064 | 1.000000 | 24.4102 / 24.4102 | False |
| k6 / cv_stop | 18054 → 18055 | -0.04999839 | -0.00306845 | 1.038700 | 1.000600 | 24.5034 / 24.5034 | True |
| k6 / discharge_start | 21655 → 21656 | -5.00035381 | -0.30343056 | 1.049176 | 1.000200 | 24.4952 / 24.4952 | False |
| k6 / discharge_stop | 25063 → 25064 | 5.00037432 | 0.33763528 | 1.137660 | 1.000500 | 34.9571 / 35.0077 | False |

## Reproduction and scope

- [Frozen protocol](stanford-boundary-protocol.md) and tested implementation: [cc5192b9](https://github.com/lijiabao1998/Physical-Fpv-Simulator/commit/cc5192b9da4d3c475cc82c3a23e2c376f3a4ae72), committed before this analysis. All 349 software tests passed; that does not establish physical-model accuracy.
- Actual run: 6.976778 seconds, 66,280 KiB peak RSS, enforced 120-second / 4,000,000,000-byte address-space limits. Six exact source hashes and all 167,980 rows checked; no errors, downloads, model solves or fitting.
- [Full machine-readable report](benchmarks/stanford-six-cell-boundaries.json) retains the unchanged original report, every selected sample, actual delays, source/implementation hashes and source attribution. [Primary table as CSV](benchmarks/stanford-six-cell-boundaries.csv).
- Independent verification parsed all original worksheet XML using defusedxml without importing openpyxl or the production analysis module. All 24 primary / 240 delayed values and provenance matched exactly; hashes and all clock audits matched. The independent audit used 6.44 seconds and 38,028 KiB RSS, with no download, fit or model call.
- Source: Edoardo Catenaro and Simona Onori, [DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original XLSX bytes are unchanged; ratios, tables and plots are derived analysis. This attribution does not select a license for original project code or imply author endorsement.

```sh
PHYSICAL_FPV_BOUNDARY_COMMIT=cc5192b9da4d3c475cc82c3a23e2c376f3a4ae72 python scripts/inspect_stanford_boundaries.py --out results/stanford-boundaries-reproduction
python scripts/render_stanford_boundaries.py --source results/stanford-boundaries-reproduction/report.json --out results/stanford-boundaries-reproduction/ratios.svg
```

The source files must already be present with the frozen hashes. This runner has no network fallback. The three k6/5C history downloads remain stopped after the recorded CONNECT 403; the k2/k6 prior-exposure contrast remains unresolved. The existing k1 191.474-mV voltage error and Chen 6/12 / ORegan 30/36 empirical failures remain unchanged.

## Next required observable

Seek a public, independently documented synchronized current/voltage transient record that resolves the presently unobserved first second and supplies sampling/filter response, calibration uncertainty, temperature/state, rest/previous-load history and voltage-sense/fixture geometry. Comparing the immediate response with later relaxation at matched stated conditions would constrain the decomposition. The present data do not justify inserting a best-fit contact resistor, changing published material parameters or labeling a new material as experimentally validated. No hardware test is prescribed or initiated.
