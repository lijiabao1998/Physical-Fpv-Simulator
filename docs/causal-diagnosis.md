# First low-cost causal diagnosis, without calibration

This analysis reuses the completed grid120 CI solution. It does not fit parameters or run all36 cases on a larger mesh. The original grid40 results remain6 passes and30 failures; the representative80→120 numerical pass does not erase them.

## Frozen-cohort failure map

| Nominal temperature | Rate | Failing cells | Main failing targets |
|---|---:|---|---|
| 0°C | 0.5C | 785,786,787,788 | Voltage RMSE/peak, capacity, energy |
| 0°C | 1C | 789,791 | Temperature RMSE/peak |
| 0°C | 2C | 793,794,795,796 | Voltage, capacity, energy, coverage |
| 10°C | 0.5C | 785,786,787,788 | Voltage RMSE/peak |
| 10°C | 1C | 789,791 | Temperature RMSE;791 also peak |
| 10°C | 2C | 793,794,795,796 | Voltage, capacity, energy, coverage; some temperature |
| 25°C | 0.5C | 785,786 | Voltage peak |
| 25°C | 1C | 789,790,791,792 | Voltage peak; three RMSE;791 temperature |
| 25°C | 2C | 793,794,795,796 | Voltage, capacity, energy, coverage and temperature |

Every cell is retained. Cell791's temperature anomaly is flagged; its sensor/cell cause is unverified. Cold conditions and hot endpoints cross measured parameter domains.

## Representative failure selected before new fitting

Cell790 at1C and nominal25°C has no source exclusion flag, an actual initial temperature of297.75K, and an existing checksum-verified80/120 numerical comparison. Reusing the120-point curve gives:

- Voltage RMSE54.81mV and maximum error383.35mV: both FAIL.
- Temperature RMSE1.17K and maximum error1.63K: pass the declared surface-proxy targets.
- Delivered capacity error4.51%, energy error3.30%, measured-time coverage95.48%.
- Predicted2.5V cutoff3333.391s versus measured3491.048s:157.657s early.
- Reference25°C initial OCV4.18103V versus measured pre-discharge rest4.17934V:1.69mV difference. This is not a fit. Small rest-voltage agreement does not uniquely determine both electrode stoichiometries or lithium inventory.

The mesh correction did not remove the experimental failure. A simple constant initial-voltage shift is insufficient to explain the late voltage drop. Temperature agreement alone also does not establish correct electrode transport or inventory.

Exact evidence: [CI-derived comparison](benchmarks/thermal-grid80-to120.json), [case790 diagnostics](benchmarks/cell790-grid120-diagnosis.json), and [completed run](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37681264082), at commit f746e0e1483f9f5d616fdfd95c7a1cb03ffa2aea. The original20-minute/4GB run completed in880.06 wall seconds.

## Reference implementation ledger: do not mix parameterizations

The [TEC v1.0 parameter helper](https://github.com/brosaplanella/TEC-reduced-model/blob/v1.0/tec_reduced_model/set_parameters.py) and [comparison script](https://github.com/brosaplanella/TEC-reduced-model/blob/v1.0/scripts/compare_TSPMe_data.py) were inspected, not executed.

| Item | This frozen ORegan reconstruction | Original TEC v1.0 comparison |
|---|---|---|
| Parameter family | ORegan2022 | Chen2020 with experiment-specific adjustments |
| Negative diffusion | Published stoichiometry/temperature law, embedded3.0321 correction | At1C/25°C, constant2e-14m²/s; retuned by rate and temperature |
| Positive initial concentration |13975mol/m³ |17150mol/m³ at25°C |
| Heat-transfer coefficient | Published15W/m²/K |16W/m²/K |
| Heat capacity | Published temperature-dependent component functions | Components scaled to effective2.32e6J/m³/K |
| Ambient temperature | Nominal condition; observed pre-rest cell temperature sets initial cell temperature | Estimated from mean post-discharge/rest temperature |
| Trace window | First constant-current discharge only | First discharge plus two-hour relaxation |
| Metric | Per-cell exact time-weighted error over common domain, explicit coverage | Unweighted concatenated-sample metrics; extrapolated NaNs removed |
| Cell791 | Retained and flagged | Excluded from plotted comparison |

The TEC code accompanies a different2021 paper. It is useful for auditing raw data/protocol and for a separately labelled reference reconstruction, but is not an identical implementation of the ORegan2022 model. Its fitted diffusivities, global heat capacity and ambient inference must not be silently imported to make our frozen baseline pass.

## Next bounded discriminating checks

1. Keep grid120 cell790 as the unchanged-parameter baseline. Partition residuals into early/middle/tail intervals, retaining the cutoff/coverage errors. Compare raw protocol boundaries with the author loader so time-origin or current-sign differences cannot masquerade as physics.
2. Audit the published ORegan parameter functions and initial-state definitions against the paper/table and parameter-data source. Check whether a discrepancy is implementation, parameterization or model-form error before changing values.
3. If a new diagnostic solve is needed, use one factor on this same case with a declared CPU budget: for example, prescribed measured surface-temperature history tests sensitivity to an imposed temperature trajectory. It jointly bypasses heat generation, heat capacity and cooling while assuming surface temperature approximates the volume average; it cannot isolate the boundary coefficient alone or count as forward temperature validation. Alternatively, a pre-rest-temperature ambient proxy must be labelled as a boundary assumption, not a fitted measurement.
4. Initial-state/lithium-inventory changes need independent conditioning/capacity evidence. Matching one OCV is underdetermined. Do not optimize cell790 or pooled36-case outcomes to select a new initial state.
5. Before any calibration, freeze a new versioned development/check plan. Cell789 is the designated1C development cell;790 is an implementation check;791/792 remain reserved same-study checks. Previously inspected data are not newly blind or independent. Generalization requires a genuinely new cohort/source.

No physical battery experiment, hardware safety claim, new material claim, full-cohort optimization, or threshold relaxation is proposed here.
