# k1/k2 transfer: the error contrast is present in the first supported seconds

At the same nominal 1.0006/2/5/10 s queries, k1's measured rest-to-load voltage
fall exceeds k2's by **147.963–148.176 mV**. Their rest endpoints differ by only
**−0.304 mV**, and the saved model terminal curves differ by **+1.894–2.274 mV**.
Consequently, k1's terminal residual exceeds k2's by **150.305–150.542 mV** already
in this early supported interval.

This associates the between-record error contrast algebraically with the measured
loaded fall rather than the measured rest-anchor contrast. It does not identify
contact resistance, kinetics, initial SOC, manufacturing variation or a unique
physical cause. The physical switching time and acquisition latency remain unknown.
Both original aggregate empirical failures remain unchanged: k1 **191.474 mV**,
k2 **55.003 mV**, against **50 mV**.

## Frozen method and evidence

The [protocol](stanford-onset-transfer-protocol.md) was independently reviewed
before calculation. It transfers the preceding k2 method to previously viewed
k1 data; this is not a blind validation. The shared first query is the latest
first supported observation/model time, 1.0006 s, followed by the already fixed
2/5/10 s. There is no extrapolation or outcome-selected time window.

The k1 workbook was recovered from its previously verified local replay-input
archive, not downloaded. Original workbook size 1,868,963 bytes and SHA256
`b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6`
match the pinned receipt. All 3,601 rest and 3,391 discharge records passed phase,
clock, date and current-sign qualification. The additional source retains all
rest rows and the 10 initial discharge rows needed to bracket the queries, with
original worksheet indices, naive dates, both clocks and measured quantities.

Catenaro and Onori,
[Mendeley DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The source report retains exact original/archive/normalized hashes and recipe.
The model inputs are the existing committed mesh120 terminal/temperature curves;
no unsaved k1 bulk OCV, concentration or polarization state is inferred.

## Observable accounting

For each cell, A is its last recorded rest voltage, H its loaded measured voltage,
M its saved model terminal voltage, D=A−H and E=M−H. Every delta below is k1−k2:

Delta E = Delta M − Delta A + Delta D.

Rest endpoints are k1 4.186448097 V and k2 4.186752319 V;
Delta A = −0.304222 mV.

| Nominal time (s) | k1 residual (mV) | k2 residual (mV) | Delta M (mV) | Delta D (mV) | Delta E (mV) |
|---|---:|---:|---:|---:|---:|
| 1.0006 | +220.418 | +70.113 | +1.894 | +148.107 | +150.305 |
| 2 | +219.225 | +68.795 | +1.951 | +148.176 | +150.430 |
| 5 | +215.582 | +65.082 | +2.089 | +148.107 | +150.500 |
| 10 | +210.483 | +59.941 | +2.274 | +147.963 | +150.542 |

The arithmetic identity closes exactly at stored binary64 evaluation. It is an
observable accounting identity, not a causal decomposition or statistical test.
The first observation occurs roughly one nominal second after command origin;
this analysis does not measure an instantaneous voltage jump.

## Finite-time response and comparability

Positive discharge current is minus the original negative source current.
Both measured currents are about 5 A, and their exact values are in the JSON.

| Nominal time (s) | k1 observed D/I (mΩ) | k2 observed D/I (mΩ) | Difference (mΩ) |
|---|---:|---:|---:|
| 1.0006 | 61.299 | 31.678 | 29.621 |
| 2 | 62.402 | 32.768 | 29.634 |
| 5 | 64.614 | 34.993 | 29.621 |
| 10 | 67.118 | 37.526 | 29.592 |

These are finite-time apparent voltage responses per ampere, not identified
series resistances. Ohmic, kinetic, transport, relaxation, inventory/OCP and
measurement effects remain mixed. The roughly stable early difference is a
constraint for a future characterization test, not grounds to add a fitted
29.6 mΩ component. It also does not overturn the earlier absence of a shared
whole-trajectory algebraic R interval meeting both 50 mV screens.

Measured k1 skin is 0.795–0.831 K warmer at the queries; saved k1 model bulk is
0.771–0.782 K warmer. Rest-tail drift and source interpolation/clock brackets are
retained for both cells. Similar rest voltage and nominal ambient do not establish
matched absolute SOC, electrode inventory, aging, fixture contact or internal
temperature. Sampling/filter latency and true switching synchronization are
unmeasured, so recorded sample brackets are not physical-switch bounds.

Both archived models use DFN, lumped thermal, ORegan2022, nominal ambient 298.15 K
and the h=15 W/m²/K prior. Initial temperatures differ: k1 298.337940598 K and
k2 297.554567719 K, each based on that record's final rest skin temperature under
an initially uniform-temperature assumption. They use their own measured current
profiles and explicit unobserved-start current hypotheses. Thus Delta M includes
these model-input differences, not just a hypothetical cell-identity effect.

The saved curves are both mesh120. The k1 replay's starting configuration records
mesh80 before its verified fine-grid run; that base field does not relabel the
compared fine curve. The archived runs also retain different implementation
commits/current-profile source hashes. Their exact evidence identities are
preserved; this analysis does not claim a new solver validation under today's
source or reconstruct missing latent states.

## Reproduce and use the result

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/check_stanford_onset_transfer.py --out results/onset-transfer-check
pytest -q tests/test_onset_transfer.py
```

All inputs are committed. The bounded comparison took about 0.32 s within
60 s/1 GB. No new acquisition, DFN solve, parameter fit or physical update occurred.
Historical reports and acceptance thresholds remain unchanged.

A useful next discriminator is a synchronized current-step/relaxation comparison
across current levels for each specimen, with fixture/contact and inventory/thermal
state constrained independently. Existing public records can support a descriptive
rate comparison if source provenance and comparable starting conditions are
qualified first. Current evidence warrants testing a specimen/record-dependent
early loaded-response difference; it does not establish whether the source is
cell physics, contacts, history or measurement configuration. No corrective
parameter is promoted from this screen.

The source report separately preserves full-phase clock audits for all k1
3,601 rest and 3,391 discharge rows. Their maximum relative naive-date/test-clock
discrepancies are 0.0010 s and 0.0009 s respectively. Result-level k1 discharge
audits describe the retained 10-row support slice and do not replace the full audit.

Validation before publication: 591 local tests passed, 7 skipped; lint and format
checks passed. Six added tests cover independent anchor/fall/model contrasts,
shared support, extrapolation rejection, immutable inputs and cached reproduction.
