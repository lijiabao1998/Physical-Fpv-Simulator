# Verified low-rate trajectory retains the conditional rate-gap mismatch

The now-qualified low-rate mesh120 trajectory preserves the previously observed discrepancy against the historical high-rate trajectory. At all nine predeclared charge locations, every saved80/120 mesh combination gives the same discrepancy sign. This is a conditional comparison of two previously inspected records, not matched-SOC validation or identification of a unique physical cause.

## Result

D is the modeled low-minus-high voltage gap minus the measured low-minus-high gap, equivalently the low-rate voltage residual minus the high-rate residual. Positive residual means model voltage exceeds measurement.

| Recorded discharged Ah | Primary D, mV | Four saved-combination spread, mV |
|---:|---:|---:|
|0.5|-46.150868|1.058802|
|1.0|-46.212973|0.975084|
|1.5|-62.137008|0.541939|
|2.0|-67.033621|0.456240|
|2.5|-87.753747|0.238495|
|3.0|-76.645153|0.080350|
|3.5|-54.555450|0.177806|
|4.0|-53.331023|0.485334|
|4.5|71.875965|0.354382|

Primary uses low120/high120. The four-value spread is an observed sensitivity to choosing the two saved meshes for each rate. It is not an uncertainty bound or a guarantee on continuum error. The discrepancy changes sign among the sampled locations; its exact zero crossing or behavior between them was not estimated. Neither voltage gap itself is claimed to reverse.

All queries are inside both measured supports and all four saved model supports. At4.5Ah, the record-specific times are64795.390131s and3240.760403s. Both precede the corresponding model cutoffs. Charge alignment uses measured piecewise-linear current from each first observed sample; it does not align by the solver's integrated capacity. The missing initial intervals remain excluded from this conditioning charge.

## Scientific consequence and limits

Replacing the original physically failed low-rate trajectory with the independently verified low-rate trajectory does not remove the sampled rate-gap discrepancy. The observed differences between saved mesh choices are much smaller than these discrepancies at all nine locations. This limits an explanation based solely on the particular saved80-versus120 choice. It does not establish that all numerical errors are negligible: tolerances differ between rates, no asymptotic order is established, and the high-rate computation used historical source code.

The low-rate pair passes its existing numerical and physical checks; low120 voltageRMSE is19.210536mV. Historical high120 voltageRMSE remains55.003054mV, failing the unchanged50mV gate. Its historical physical/mesh checks pass. These separate facts are preserved; there is no new rate-comparison acceptance gate.

Equal discharged Ah does not prove equal SOC, inventory, capacity/SOH or prehistory. The records are separated by an unobserved45.4967575-hour gap, with different temperatures and starting skin-temperature assumptions. Model bulk versus measured skin remains a proxy comparison. Heat-capacity support below25°C remains unestablished. Loaded voltage combines equilibrium/inventory, ohmic, kinetics, diffusion and thermal responses. These two traces cannot uniquely assign the mismatch to one component or identify a contact resistance.

A next independently discriminating electrical experiment would require an initial-inventory/capacity constraint and a matched-state rate transition or pulse/relaxation measurement with characterized timing and temperature. The existing unobserved gap prevents reconstructing that history from these two records. Such an experiment is a proposal, not launched here. Further fitting of these nine points would not supply the missing independent constraint.

## Reproduction and provenance

Run `OPENBLAS_NUM_THREADS=1 python scripts/compare_stanford_k2_qualified_rates.py --out results/qualified-rate.json` from the installed repository environment. The tool verifies the complete committed low-rate evidence, authenticates the complete historical archive and its selected sources, checks high-rate mesh/physical provenance, and reproduces the established rate-point helper for both low meshes. It performs no network request or battery solve.

[Machine-readable result](benchmarks/stanford-k2-qualified-rate-result.json), [CSV](benchmarks/stanford-k2-qualified-rate-result.csv), [frozen protocol](stanford-k2-qualified-rate-protocol.md), [low-rate qualification](stanford-k2-mesh120-findings.md), and [ordinary-CI retrieval proposal](raw-input-cache-recovery-proposal.md) preserve the inputs and interpretation. Full source/array hashes and both source commits are in the JSON. Independent review recomputed all four combinations directly from archive bytes before publication.

Validation: independent review approved the protocol and final arithmetic/provenance. The complete local suite passed702 tests with7 skipped and6 warnings in164.31s; all150 Python files passed lint/format checks. The new saved-result regression forbids network access and battery solves and rejects a materially perturbed discrepancy.
