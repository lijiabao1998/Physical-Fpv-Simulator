# Saved-array conditional low/high-rate comparison

## Frozen question and evidence

Does the previously reported low-minus-high voltage-gap discrepancy survive replacing the physically unqualified low-rate baseline with the now verified mesh120, tolerance-1e-8 trajectory? This is a retrospective, descriptive compatibility screen. The nine charge locations were declared before the new low-rate solves: 0.5 through 4.5 Ah in 0.5 Ah steps. No new location, fitted correction, parameter selection, acceptance gate, data acquisition or solver execution is permitted in this increment.

Use the complete committed low-rate mesh120 archive, SHA-256 a3b737252dd5893c4d2039ca9b049a4818b091cf5d771aa261a356f52cb66e2e, run 37960046810, source 5655bda1527c0941f99717018dc06553a7283dea. The archive also contains the pinned, physically valid mesh80/tolerance-1e-8 baseline. Require its existing saved-evidence verification before scientific reporting. Preserve all physical, cutoff, mesh and empirical verdicts exactly.

Use the historical high-rate archive, SHA-256 2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d, run 37871885149, source 50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84. Verify the already pinned high-rate source records, forcing, input and mesh120 curve through `historical_inputs`. The full archive hash also fixes its mesh80 curve. Require historical reports to confirm both selected mesh identities and physical/numerical outcomes; do not reinterpret the input manifest's original mesh80 configuration as the mesh120 curve's actual mesh.

## Observable and arithmetic

For each record separately, integrate positive-discharge measured current from its first observed sample and invert that piecewise-linear-current charge function at the nine fixed Ah locations using the established `time_at_charge` convention. The unobserved initial interval remains explicitly excluded from the measured conditioning charge. No extrapolation is allowed in measured or model time support. Interpolate measured voltage/skin temperature and each saved model voltage/bulk temperature at the resulting record-specific time.

Report residual E = model voltage minus observed voltage, measured gap Gobs = low voltage minus high voltage, model gap Gmodel = low model voltage minus high model voltage, and D = Gmodel - Gobs = Elow - Ehigh. Require algebraic closure within 1e-12 V; this is an arithmetic check, not a scientific tolerance. Require finite, strictly increasing time axes and charge targets within measured support. Preserve the existing physical checks separately.

Primary result uses low mesh120/high mesh120. Also compute the same nine queries for all four combinations of the existing low/high meshes80/120, without rerunning any mesh. Report each pair's D and its difference from the primary pair. The minimum and maximum of these four saved values describe observed mesh-choice sensitivity only; they are not uncertainty bounds, a convergence order, a guarantee of continuum error, or a controlled tolerance comparison. Report whether each point's discrepancy sign is shared by all four saved combinations; a sign result is descriptive and creates no new empirical pass gate. Verify the previously saved low mesh80/tolerance-1e-8 trajectory and its existing physical/empirical report before deriving its new rate-point values. No earlier rate-point artifact is assumed to exist for that tolerance.

## Comparability and interpretation limits

Both records use the ORegan2022 DFN/lumped model, published initial electrode concentrations 28866/13975 mol m^-3, h=15 W m^-2 K^-1 and nominal ambient298.15 K. Their starting skin-temperature proxies differ. Low-rate solves use tolerances1e-8 with 1-second samples plus declared Ah-query times and the true endpoint; historical high-rate uses1e-7 with 5-second samples plus current-profile knots and the true endpoint. The high-rate profile implementation is historical; recorded forcing-query agreement does not certify the newer implementation by reusing old arrays. Record the actual versions, source identities and grids, and label historical evidence accordingly.

Equal discharged Ah from each record's first observation does not establish equal absolute SOC, electrode inventory, rest/history, temperature or cell state. The records have an unobserved45.4967575-hour gap; no continuous state replay is allowed. Initial current intervals are assumptions. Finite-time voltage combines equilibrium/inventory, kinetics, transport, ohmic and thermal effects. Neither a surviving discrepancy nor its sign identifies a unique physical cause or contact resistance. Predicted bulk versus measured skin remains a temperature proxy comparison; sub25°C heat-capacity extrapolation remains explicit. Both records were previously inspected; this is not blind holdout validation.

## Deliverable and stopping condition

Publish a reproducible JSON/CSV, readable plot if useful, findings and meaningful regression tests. Include source hashes, exact query times, four combinations, original verdict provenance and any unavailable support. The historical high-rate55.00305419157363mV RMSE still fails its unchanged50mV gate. The low-rate19.210536131mV result does not cancel that failure. Stop after verified publication and CI outcome; propose the next independently constraining experiment only from these results, without launching it.
