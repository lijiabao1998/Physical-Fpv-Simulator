# ORegan2022 thermal-electrochemical reproduction protocol v1

Frozen 2026-10-07 before any new model-to-data result is computed. This is a second public reconstruction benchmark; the original authors adjusted parameters using these experiments. No independent blind-validation claim.

## Sources and cohort

PyBaMM 26.9.0.0 ORegan2022; source paper https://doi.org/10.1016/j.electacta.2022.140700 . Parameter data https://doi.org/10.5281/zenodo.5171874 (CC-BY-4.0). Validation data https://doi.org/10.5281/zenodo.4864437, repository v1.0 BSD-3-Clause (copyright Ferran Brosa Planella, 2020), associated paper https://doi.org/10.1016/j.electacta.2021.138524 . Archive MD5 f9306803d4a2e2a5e27ad9b43596fa12, SHA256 3848d0eb1d70e4fc86cc77c272433053760b0bdfe25825ef652135edc43275b8.

Use every first complete `Status=DCH` discharge in the 36 files for 0.5C, 1C, 2C at nominal 0°C, 10°C, 25°C, four cells per condition. The 0.1C files are outside this protocol because the ORegan thermal validation protocol uses 0.5/1/2C. Subsequent repeated cycles are outside this initial protocol for all cells, consistently. Do not choose cycles based on error. Cell791 was excluded by the older source comparison code; retain it here with a provenance note and explicit quality flags instead of silently deleting it.

There are 12 physical cell IDs across these conditions, reused across temperatures. Per rate: first cell (785,789,793) is development/inspection; second (786,790,794) is implementation check; remaining (787,788,791,792,795,796) are reserved reproduction checks. No fitting or parameter selection is permitted on any of them in v1. Every cell's result is reported; aggregate success requires every specified case. Raw invalid data/solver failures stay visible as failed cases.

## Fixed model, initialization and boundaries

DFN with lumped thermal submodel. Use published ORegan2022 initial concentrations: negative 28866 mol/m³, positive 13975 mol/m³; do not call initial_soc and do not align initial voltage. The PyBaMM functions already contain diffusion correction factors 3.0321 (negative) and 2.7 (positive); do not apply them again. Use a single heat-transfer coefficient 15 W/m²/K, disclosed from the paper, across all conditions, replacing the package default 10. This is reproducing a published fitted boundary parameter, not a new independent estimate.

Use nominal ambient temperature from the experimental condition. Set initial cell temperature to the final zero-current pre-discharge cell-temperature reading (an observed initial condition, not an optimized parameter). Document missing ambient sensors. For raw cells with multiple surface sensors use LogTempMid, otherwise use the source's cell-temperature column. Lumped model temperature is volume-average, compared with surface measurement as an explicit approximation. Do not identify these observables as identical. Use measured Step Time without stretching; nominal current is 2.5/5/10 A. Stop at model 2.5 V or research temperature guard 333.15 K; the latter must fail complete-discharge agreement.

Primary model grid40, independent grid80 check, solver tolerance1e-7 and tolerance1e-8 check; single thread, at most80 meshpoints and fixed finite discharge duration. Each case has numerical comparison with the same initial condition. No adaptive fit, no arbitrary threshold changes.

## Fixed acceptance targets

For each case, use exact piecewise-linear error integration on the union of model and data time knots inside the common interval. No extrapolation, curve cropping, alignment or time rescaling.

- Voltage time-weighted RMSE <=0.050 V and maximum absolute error <=0.300 V
- Full delivered capacity and energy relative error <=5%
- Measured-time overlap coverage >=95%, expected voltage cutoff required
- Temperature time-weighted RMSE <=2 K and peak absolute error <=5 K, compared with the declared surface proxy
- Mesh and solver refinement: maximum voltage difference<=0.005 V, capacity difference<=1%, maximum temperature difference<=0.1 K
- Lithium relative drift<=1e-6; charge integral error<=1e-6 Ah; finite outputs and physically admissible concentrations at output samples
- Sampled thermal energy residual<=1% of max(total generated heat magnitude,1 J). Integrate C(T)dT for temperature-dependent heat capacity, rather than C(T0)*deltaT.

Keep engineering checks, numerical checks, empirical targets and physical applicability separate. A passing comparison is not battery safety certification.

## Applicability and uncertainty

The measured parameter domains differ: solid diffusion5–45°C, exchange-current measurements15–45°C, heat capacity25–100°C; some supporting electrolyte/handbook laws have separate domains. Therefore 0°C and10°C runs necessarily extrapolate at least some measured laws. Flag each crossed domain and never label the entire0–25°C envelope validated merely because errors pass. Fixed Arrhenius extrapolation cannot establish low-temperature mechanisms. Thermocouple uncertainty and parameter covariance are not fully quantified in this first reconstruction; do not invent confidence intervals. Report across-cell scatter as variability, not model uncertainty.

No claims about aging, pulses, packs, high-C FPV, abuse, material discovery or safe real-cell operation. Retain all previous Chen2020 failures and evidence unchanged.

## Raw-format rules clarified before first model run

Discharge AhAccu/WhAccu carry offsets. Compare their start-minus-end differences to numerical current/power integrals, not their absolute endpoints. Duplicate Step Time records are resolved deterministically by retaining the last record at that time; log duplicate count and whether duplicate values differ. Reject time reversal. Source inspection found361 duplicate records across the36 first discharges, including five minimally changed endpoint duplicates; none are silently smoothed. Initial temperature may use a zero-current RANGE record immediately following the pre-discharge rest. A constant zero ambient channel at a nonzero nominal temperature is an uninformative placeholder, not a measured ambient boundary.

Temperature peak absolute error means max_t|T_model(t)-T_surface(t)| on the overlap interval. Also report the difference of full-discharge temperature maxima separately, without substituting one metric for the other. Domain flags inspect both measured and simulated temperature ranges, not only nominal ambient. This includes excursions above45°C at higher currents and initial temperatures slightly below25°C.
