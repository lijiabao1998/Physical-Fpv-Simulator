# k2 internal-state result: late mechanism resolved inside the model, empirical failure retained

The single frozen diagnostic completed in **960.127 seconds**, peak RSS
2,162,460 KiB, within1200seconds/4GB. It exactly reproduces all eight previous
grid120 native arrays. Voltage, temperature and capacity differences are zero.
The empirical RMSE remains **55.003054 mV, FAIL against50mV**.

[Source run37881497526](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37881497526),
commit `6d74c8d4a75ece4a1b8b3efafbfb127740f0b661`, October9
03:56:34–04:12:34 UTC. Exactly one scientific solve; original inputs were reused
from a saved artifact, with no new source acquisition or k6 downloads.

## Accounting checks and frozen state

Across3993 native output times, maximum voltage-identity error is9.94e−10V
(target1µV). Maximum mean-stoichiometry/charge error is1.76e−14
(target1e−6). Native concentration, lithium, charge and heat-balance audits pass.
These validate the recorded calculation's internal consistency, not the cell model.

At cutoff, bulk OCV is3.096740V and signed polarization sums to−596.740mV,
yielding2.5V. Dominant negative contributions are:

| Model contribution at cutoff | Signed contribution |
|---|---:|
| Negative-particle concentration | −338.642mV |
| Negative and positive reaction, combined | −145.945mV |
| Positive-particle concentration | −59.110mV |
| Electrolyte concentration and ohmic, combined | −51.697mV |
| Solid-phase ohmic, combined | −1.346mV |
| Contact term | 0mV |

From3000s to cutoff, terminal voltage falls612.541mV. Bulk OCV decreases280.880mV
and the negative-particle contribution decreases277.789mV. These are major
contributors to the **model's late collapse**, not proof of the real error's cause.
The negative electrode's mean/surface-x-average stoichiometries at cutoff are
0.085989/0.041267; positive values are0.916284/0.989683. They are model lithium
fractions, not independently measured cell SOC.

## The broad positive residual remains a distinct question

The earlier residual audit placed86.1% of squared error before the late sign
change. The largest endpoint loss cannot explain that broad error by itself.
The following native-time averages use the same four measured-duration quarters;
the fourth stops at the model event. Values are signed model contributions,
**not measured or uniquely attributable contributions to empirical error**.

| Quarter | Negative particle | Positive particle | Reaction sum | Electrolyte sum | Solid sum |
|---|---:|---:|---:|---:|---:|
| 1 | −18.279mV | −57.319mV | −40.751mV | −59.747mV | −1.463mV |
| 2 | −31.655mV | −60.363mV | −42.166mV | −58.972mV | −1.425mV |
| 3 | −38.254mV | −60.922mV | −49.187mV | −58.351mV | −1.416mV |
| 4 | −72.793mV | −69.683mV | −78.712mV | −56.542mV | −1.393mV |

The contact term is zero because this model disables it; that does not establish
zero real contact resistance. An omitted positive fixed series resistance could
contribute to a positive residual, but alone cannot explain its later negative
sign under positive discharge current. No resistance was inferred or fitted.
Similarly, small modeled solid-ohmic loss is not proof the real loss is small.
The saved model does not independently determine whether its bulk OCV is too
high, its net losses too small, or both in the early/middle regime.

## Additional zero-solve test: direct OCP temperature dependence

With the saved electrode-average states held fixed, evaluate the pinned ORegan
OCP functions at actual saved temperature and at298.15K. The actual-temperature
evaluation reconstructs exported bulk OCV within2.31e−14V. The direct difference
lies between **−4.729 and+0.191mV** across the trajectory; quarter means are
+0.110,+0.167,−0.143,−1.628mV.

Therefore this *explicit, state-held OCP temperature term* alone is too small
to account for the broad+50–60mV discrepancy. This is pure algebra on saved
states, not a new solve, refit or resimulated isothermal counterfactual. It does
**not** remove temperature's indirect influence on kinetics, diffusion or state
history, and does not establish thermal validation. No retrospective gate changed.

## Constitutive-support timing is now observed

All physical surface nodes were retained as native profiles. The first saved
outside-support observations and preceding brackets are:

- Positive exchange-current sampled envelope0.2598–0.8499:
  first outside at2436.0011s, preceding sample2435.0s.
- Negative sampled envelope0.1585–1.0000:
  first outside at2536.0010s, preceding sample2535.0006s.
- Saved-temperature25°C crossing is bracketed by97.0005–98.0007s;
  positive-coating-conductivity nominal35°C by3163.0002–3164.0003s.

These are sampled brackets, not exact continuous crossing times. The
stoichiometry envelopes are released exchange-current measurement support,
not OCP validity bounds. Conductivity was measured near positive x≈0.9, with
concentration dependence unestablished. Support exits occur after substantial
positive error already exists, so their timing alone cannot explain its onset.
Lumped bulk temperature versus skin remains a proxy under unmeasured fixture h=15.

## What this evidence does and does not justify

The diagnostic resolves voltage accounting and surface-state timing inside the
frozen model. It rules out attributing the entire discrepancy to the small direct
OCP thermal term or to an endpoint term without considering the earlier regime.
It does not identify a unique real-cell mechanism, calibrate an improved model,
or validate FPV, aging, abuse, safety or new materials. Initial inventory, OCP
transferability, transport/kinetics and measurement/thermal boundaries remain
candidate uncertainties. Existing k1, Chen and ORegan failures remain unchanged;
the original lost execution remains unknown.

No further scientific solve or source acquisition is implied by this result.
Future work needs a separately frozen discriminating comparison and explicit
resource bounds; parameter fitting to erase the failure is not supported here.

## Durable evidence and reproduction

- [Full JSON summary and original member hashes](benchmarks/stanford-k2-state-summary.json)
- [All47 exported scalar trajectories](benchmarks/stanford-k2-state-scalars.csv.gz)
- [Machine-readable saved-state analysis](benchmarks/stanford-k2-state-analysis.json)
- Full native/reduced profile CSV, snapshots and receipts are in source artifact
  11595008313, ZIP SHA256
  `450307f4b2669b46edb7a3a0a2e3d53619a12bb4f87e7e74e71ce47c117236c9`.
  Complete input/output ZIPs are also saved in the owner's Library independently
  of the Actions artifact retention period.

Run `python scripts/analyze_stanford_k2_states.py` in the pinned environment.
It checks compressed/CSV hashes, voltage signs and closure, mean-charge identities,
installed constituent functions and the direct OCP temperature comparison without
time integration, a data download or fitting. The reduced scalar archive does
not contain the entire r×x solver state; complete exported native profiles remain
in the full evidence ZIP. Original source attribution and licensing are preserved.
