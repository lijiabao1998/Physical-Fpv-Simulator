# k2 near-start response: a constant rest-anchor offset is insufficient

The saved model begins **5.792 mV below** the measured 1C rest endpoint in bulk
OCV, but its terminal voltage is **70.113 mV above** the first supported loaded
measurement. Removing that particular constant offset leaves **75.905 mV** of
residual. At the other fixed nominal times, the remaining residual is
74.587, 70.873 and 65.733 mV. Thus this rest-anchor correction does not reconcile
the saved early trajectory. This is a conditional algebraic result, not a unique
identification of resistance, SOC, inventory error or kinetics.

The unchanged historical whole-discharge result remains **55.003054 mV RMSE,
FAIL against 50 mV**. No parameter was fitted, shifted or promoted.

## Frozen comparison

The [independently reviewed protocol](stanford-k2-onset-protocol.md) declared
queries at the first common supported time, 2, 5 and 10 s, both 10/60 s rest-tail
summaries, exact source qualification and the interpretation limits before
actual calculation. The first query is 1.0003 s on the nominal discharge command
clock. These are previously viewed records, not a blind holdout.

Inputs are the existing checksum-pinned k2 0.05C/25C original workbook, committed
k2 1C records, and archived fixed-parameter DFN states/forcing. All 3,601 low-rate
rest and 70,370 low-rate discharge records were qualified. The additional compact
source slice retains every rest row plus the 10 discharge rows needed to bracket
all fixed queries, including original worksheet row numbers, naive dates, test
clock, step clock, current, voltage and skin temperature. The preceding increment
retains the complete normalized low-rate discharge. No new download or solve.

Data attribution: Catenaro and Onori,
[Mendeley DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The source report retains
original workbook and normalized-array hashes and the exact preparation recipe.

## Fixed-query accounting

B is initial model bulk OCV, A is the last measured 1C rest voltage, H is measured
loaded voltage, and M is model terminal voltage. The identity is:

E = M − H = (B − A) + (A − H) − (B − M).

B = 4.180960440 V; A = 4.186752319 V; C = B − A = −5.791880 mV.

| Nominal time (s) | Observed fall A−H (mV) | Model reference fall B−M (mV) | Residual E (mV) | E−C (mV) |
|---|---:|---:|---:|---:|
| 1.0003 | 158.401 | 82.496 | +70.113 | +75.905 |
| 2 | 163.850 | 89.263 | +68.795 | +74.587 |
| 5 | 174.980 | 104.107 | +65.082 | +70.873 |
| 10 | 187.646 | 121.913 | +59.941 | +65.733 |

The identity closes to zero at binary64 evaluation. E−C is nonzero at all four
queries against the declared 1e−10 V arithmetic guard. That guard excludes
roundoff; it is not an experimental confidence interval or a relaxed physical
acceptance criterion. A different true initial inventory can change the entire
trajectory and is not represented by this constant correction.

## Independent observed rate comparison

The low-rate rest endpoint is 4.186485767 V, only 0.266552 mV below the 1C rest
endpoint. Equal endpoint voltage does not certify equal electrode inventory or
absolute SOC. The finite-time rest-to-loaded response divided by measured current
is nevertheless directly observable under the declared timing convention:

| Nominal time (s) | 0.05C apparent response (mΩ) | 1C apparent response (mΩ) | Model initial-reference response (mΩ) |
|---|---:|---:|---:|
| 1.0003 | 32.283 | 31.678 | 16.498 |
| 2 | 32.874 | 32.768 | 17.851 |
| 5 | 35.714 | 34.993 | 20.820 |
| 10 | 38.706 | 37.526 | 24.381 |

These ratios are **not identified ohmic resistance**. They include kinetics,
diffusion, rest drift, inventory/OCP change, thermal effects and measurement
latency. The model numerator uses a published-inventory initial bulk OCV rather
than a simulated rest endpoint. No ratio was selected as a model parameter, and
these values are not interchangeable with 30 s DCIR or 1 kHz ACIR.

## Rest drift, temperature and clocks

| Record | Last 10 s endpoint change (mV) | Last 60 s endpoint change (mV) | Last 60 s voltage span (mV) |
|---|---:|---:|---:|
| 0.05C | +0.049335 | +0.041570 | 0.403404 |
| 1C | −0.046422 | −0.023556 | 0.417233 |

Both tail windows are retained. These small observed changes describe the source;
they do not certify equilibrium or quantify sensor uncertainty.

At the four queries, measured 1C skin minus low-rate skin is
+0.04813, +0.04813, +0.02174 and +0.06868 K. Model bulk minus 1C skin is
+0.01502, +0.01899, +0.03387 and +0.04640 K. The near-start temperature differences
are much smaller than the whole-discharge differences, while skin and bulk remain
distinct observables. This does not establish matched internal temperature.

The recorded last-rest/first-load brackets are:

- 0.05C: source test time 17441.070656–17442.117708 s, width 1.047052 s;
  command origin inferred at 17441.117708 s.
- 1C: source test time 20786.156096–20787.202324 s, width 1.046228 s;
  command origin inferred at 20786.202024 s.

These are recorded sample brackets, **not verified bounds on physical switching
time**. Instrument/filter latency and sub-sample synchronization are unknown.
The JSON retains exact naive dates, source rows and interpolation brackets for
every query. No sample was extrapolated into an unobserved initial interval.
The separate 45.497 h inter-record history gap is not replayed.

## Reproduction and next constraint

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/check_stanford_k2_onset.py --out results/k2-onset-check
pytest -q tests/test_onset_response.py
```

All inputs are committed. The actual calculation took 0.295 s within the frozen
60 s/1 GB budget. The source preparation script reconstructs the support slice
from the existing checksum-verified workbook; normal reproduction needs no
workbook download, optimization or physical solve.

This result rejects only the selected constant rest-anchor explanation for the
saved trajectory. It supports investigating the early loaded response with an
independently constrained current-switch clock and voltage/current acquisition
response. Higher-resolution synchronized pulse/relaxation observations, with
known thermal and inventory state, would discriminate instantaneous/contact loss
from fast kinetic/transport response. The current one-second-scale samples cannot
uniquely do so. Existing other-cell traces can test whether this response pattern
transfers before proposing a fitted physical correction; no correction is adopted
in this increment.

Validation before publication: 584 local tests passed, 7 skipped; lint and format
checks passed. The 16 added tests cover arithmetic and current units, synthetic
constant-offset compatibility, invalid clocks/currents, unsupported queries,
immutable source hashes and no-download/no-solve reproduction.

Clock-audit maxima are retained per analyzed phase in the result JSON, with
checked row counts. Naive-date/test-clock discrepancies are about 0.0008 s
for both rest phases and the retained low-rate onset slice, and 0.0010 s for
full 1C discharge. The source report separately retains the complete low-rate
workbook audit; a short retained slice does not substitute for that audit.
