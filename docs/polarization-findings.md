# Cell790: what the frozen model does at cutoff

The new internal-state diagnostic completed in780.04 wall seconds on existing cloud CPU, under the predeclared1200-second/4GB budget. Its [protocol](polarization-protocol.md) and implementation were committed as [02b16172](https://github.com/lijiabao1998/Physical-Fpv-Simulator/commit/02b16172d4e9a88b8923aef779d0f02df766d56c) before execution. No physical parameter, initial state, boundary, empirical target or solver tolerance was changed.

## Numerical and accounting findings

The largest voltage reconstruction error was9.934e−10V against the1e−6V target. Directly exported electrode-average stoichiometries agree with charge conservation within2.51e−14 against the1e−6 target. Physical concentration, lithium, charge and heat audits passed. The old grid120 curve is reproduced within5.637e−8V,8.701e−8K and4.844e−11 relative capacity error. Both cutoff times are retained in the [machine-readable evidence](benchmarks/polarization-grid120-summary.json).

These are numerical consistency checks. They are not new laboratory measurements, independent validation, or improvements to the experimental error. The original cohort remains30/36 empirical FAIL; the cell790 voltage failure remains.

## Model-internal voltage balance at3333.391s

| Contribution | Signed voltage contribution |
|---|---:|
| Bulk positive minus negative OCP | +3.096727V |
| Negative particle concentration polarization | −0.338651V |
| Positive particle concentration polarization | −0.059106V |
| Negative reaction overpotential | −0.073121V |
| Positive reaction overpotential | −0.072810V |
| Electrolyte concentration overpotential | −0.033088V |
| Electrolyte ohmic contribution | −0.018604V |
| Negative solid ohmic contribution | −0.000006V |
| Positive solid ohmic contribution | −0.001340V |
| Contact contribution | 0V |
| Terminal voltage | 2.500000V |

The largest modeled loss is negative-particle concentration polarization. At cutoff, negative electrode average stoichiometry is0.085985 versus x-averaged particle-surface0.041265; positive values are0.916286 and0.989680. The largest positive-particle surface stoichiometry is0.995577. These direct model outputs confirm substantial within-particle gradients while average lithium remains available. They also independently confirm the earlier charge-based mean-state calculation.

This explains how this parameterized model reaches cutoff. It does not prove the true cell has the same gradient or that a diffusivity error uniquely causes the experimental mismatch. Initial inventory, effective capacities, OCP applicability, transport and other model assumptions remain distinguishable hypotheses. No parameter is fitted from this decomposition.

## Observable definitions and reproducibility

The dynamic lumped temperature is309.626K at cutoff. The default model's “surface temperature” field is the imposed298.15K ambient boundary, not a simulated casing thermocouple. Particle surface, cell surface, electrode average and measured surface proxy are distinct observables throughout the exports.

Run `python scripts/diagnose_polarization.py --timeout 1200 --out results/new-polarization-run` for a new bounded calculation, then `python scripts/summarize_polarization.py --input results/new-polarization-run` to package it. The full output includes native-time scalar and physical-node profile CSVs, five spatial snapshots, source hashes, versions, signed variable mappings, progress, outcome and portable source notices. The committed compact summary preserves all scalar trajectories' extrema, five state summaries and checksums of every full output; the roughly5MB native-profile CSV is reproducible rather than vendored.
