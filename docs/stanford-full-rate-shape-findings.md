# Complete measured curves constrain capacity and rate-shape comparisons

The four cached records end near the same nominal 2.5 V cutoff but deliver
different observed charge. The frozen onset offsets largely remove the specimen
voltage contrast, while a substantial low-versus-high-rate voltage difference
remains in both specimens. This separates two useful descriptive features; it
does not identify their physical causes or validate a revised battery model.

The [protocol](stanford-full-rate-shape-protocol.md) was independently reviewed
before calculation. All four records were previously viewed. No parameters were
fitted, no data downloaded and no DFN simulations run. Historical k1/k2 DFN RMSE
remains 191.474/55.003 mV, failing the unchanged 50 mV single-cell gate.

## Complete observed discharge and cutoff

Integration begins at the first recorded loaded sample, not an invented initial
state. The omitted command-to-first-sample interval is about 1 s in each record;
its charge is unknown and not imputed. Thus these are **observed discharged Ah**,
not independently established total cell capacity or SOH.

| Specimen/rate | Rows | Observed Ah | Observed duration (s) | Last voltage (V) | Skin temperature range (K) |
|---|---:|---:|---:|---:|---:|
| k1 / 0.05C | 70,000 | 4.861208 | 69,998.7907 | 2.499969 | 298.128–300.722 |
| k2 / 0.05C | 70,370 | 4.887153 | 70,368.9178 | 2.499998 | 297.342–298.308 |
| k1 / 1C | 3,391 | 4.707801 | 3,389.3962 | 2.499981 | 298.338–304.313 |
| k2 / 1C | 3,436 | 4.770869 | 3,434.7710 | 2.499992 | 297.535–305.483 |

The final samples are 0.002–0.031 mV below the nominal cutoff; this does not
verify the exact physical crossing or measurement uncertainty. The k1-minus-k2
observed-charge differences are −25.945 mAh at low rate and −63.068 mAh at
high rate. Low-minus-high differences are +153.407 mAh for k1 and +116.284 mAh
for k2. Rate, temperature, cutoff and unknown intervening history preclude an
attribution to degradation. The low-rate records span about 19.4–19.5 hours and
are not isothermal merely because their filenames say 25°C.

## Frozen descriptive offset and voltage shape

Reuse r1 = 61.735064 mΩ and r2 = 32.283457 mΩ from the low-rate
1.001 s onset. The separate column W = V + I r uses each record's actual
positive discharge current. W is an algebraic observable, **not OCV, corrected
terminal voltage, or a physical resistance identification**. Its equality to the
low-rate rest anchor at the defining onset query is true by construction and
provides no independent validation.

Every predeclared 0.5 Ah step through 4.5 Ah is supported by all four full measured
records. Charge inversion retains each record's distinct time and temperature.
These points condition on equal discharged Ah, not equal absolute SOC or inventory.

| Q (Ah) | W k1−k2, low (mV) | W k1−k2, high (mV) | W low−high, k1 (mV) | W low−high, k2 (mV) | Rate interaction (mV) |
|---|---:|---:|---:|---:|---:|
| 0.5 | −0.101 | 0.333 | 64.792 | 65.226 | −0.434 |
| 1.0 | −0.253 | 1.961 | 77.471 | 79.685 | −2.214 |
| 1.5 | −0.418 | 2.972 | 91.433 | 94.823 | −3.390 |
| 2.0 | −0.560 | 3.207 | 89.923 | 93.691 | −3.767 |
| 2.5 | −0.854 | 4.581 | 99.989 | 105.425 | −5.435 |
| 3.0 | −0.840 | 6.113 | 115.238 | 122.191 | −6.953 |
| 3.5 | −2.402 | 7.246 | 111.048 | 120.697 | −9.649 |
| 4.0 | −2.951 | 7.177 | 115.076 | 125.204 | −10.128 |
| 4.5 | −14.388 | −2.250 | 83.671 | 95.809 | −12.138 |

The interaction is (k1−k2 at low rate) minus (k1−k2 at high rate), equivalently
the difference between the two within-specimen low-minus-high gaps. Those two
expressions are an arithmetic identity, not independent confirmation.

Before this descriptive offset, the low-rate k1−k2 voltage contrast ranges from
−7.466 to −21.751 mV over the declared points; the high-rate contrast ranges
from −140.019 to −149.516 mV. The reduction in specimen contrast after applying
frozen descriptors is useful evidence for a persistent specimen-dependent
current-proportional component. The remaining 64.8–125.2 mV low-versus-high W
gaps show that this component is not a full description of rate dependence.
These gaps compare **measurements with measurements**; they are not newly
computed DFN errors. In particular, do not subtract them from the 50 mV gate.

The larger low-rate shape difference near 4.5 Ah and unequal observed charges
limit interpreting common Ah as identical internal state. Different temperatures,
roughly 45-hour unobserved low/high histories and missing initial intervals remain
explicit. No thermal correction, inventory fit or state replay has been imposed.

## Reproducibility and next discriminant

[Result JSON](benchmarks/stanford-full-rate-shape.json) includes all raw V and W
contrasts, point times/currents/temperatures, complete-source summaries, history,
identities and unavailable-result handling. The newly persisted
[k1 low-rate source](benchmarks/stanford-k1-low-rate-discharge.csv.gz) contains
all 70,000 discharge rows; its [source receipt](benchmarks/stanford-full-rate-shape-source.json)
links them to original workbook SHA-256
`e5870c6989c94995de10e053f04efcf96951790e3c26e51d4c537261ba847ec5`.
Normalized gzip SHA-256:
`ac0587df4bd755f7aeb834f848585228e566a89dd94a5e68512ed810e19e3eff`.

Source: Catenaro and Onori, [Mendeley v2](https://doi.org/10.17632/kxsbr4x3j2.2),
CC-BY-4.0. Low-rate normalized rows retain date and step clocks; per-row test
time is absent and the pinned original receipt supplies its clock audit.
No reconstructed test time is presented as an observation.

Run `python scripts/check_stanford_full_rate_shape.py` in the pinned environment.
Cached normalization took 8.3 s under 120 s/1 GiB; analysis took under 1 s under
60 s/1 GiB. Tests cover variable-current integration, frozen descriptors,
unequal support retaining valid pairs, contrast identities, altered-input
rejection and network-free reproduction. Arithmetic checks are not measurement
uncertainty or physics acceptance thresholds.

The next model-level discriminant would compare the frozen model's low/high-rate
voltage-shape response against these measured rate gaps while keeping specimen
terms and thermal/history scenarios explicit. It needs its own predeclared,
bounded simulation protocol; the present data do not justify assigning the
remaining gap uniquely to diffusion, kinetics or electrode inventory.
