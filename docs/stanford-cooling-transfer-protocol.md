# Frozen k2-to-k1 cooling transfer check

Frozen2026-10-09 after k2 characterization commit0fb5624e completed all three CI
checks, before extracting or scoring the archived k1 cooling episode in this
iteration. k1 has been viewed in earlier research: this is a separate-cell
transfer check excluded from the present k2 scalar calibration, **not a blind
specimen or independent laboratory validation**.

## Inputs and no-refit contract

Use the authenticated existing archive
`current-source-k1-inputs-37887926852.zip`, SHA256
`c777b934ed13ed02aac194c045e7582b8032820e2706867517aa92911d2477a9`.
Its member `files/data/stanford/raw/NMC_k1_1C_25degC.xlsx` is1,868,963 bytes,
SHA256`b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6`.
Before scoring, normalize the two rest traces losslessly into committed
`benchmarks/stanford-k1-cooling-source.json`, SHA256
`9fc12883623a0d5fa47d4c13eed9a37edf40965f8fe0e965cc294772c32c1dc9`.
The normalization includes the full source inspection and original float-valued
step times/skin temperatures. Normalization checked the original header,
full chronology/protocol using the existing source inspector, source checksums,
finite values and exactly zero recorded current in the two selected rest phases.
Default reproduction reads the committed normalized artifact and verifies its
hash; optional `--input-zip` rechecks it against original workbook rows.
No new source is acquired and missing or changed input fails closed.

Freeze both k2 decay rates from the published JSON at0fb5624e, with a pinned JSON
hash`a240791b72e63a1ac1625fecf9cc29f45bbdef2b6f5b26ec36b6a08cc634a782`
recorded before execution. No k1-dependent rate fit, scenario selection,
amplitude optimization, ambient optimization or window search is allowed.
The nominal25°C scenario transfers tau345.2559103125735 s; the skin-proxy scenario
transfers tau402.1041495660451 s. Numerical values come from the frozen JSON, not
these rounded explanatory labels. Preserve the frozen analytic prior rate and its
published heat capacity convention unchanged.

For k1, only the conditions needed to initialize a prediction are supplied from
its own measurements: T(60 s), and (for the skin-proxy scenario) the time-weighted
mean of the pre-discharge rest's final600 s. Nominal25°C stays25°C. Applying k2's
absolute skin baseline to another episode is not this protocol. The source-state,
fixture, aging/history and ambient differences remain explicit confounders.

## Scoring and interpretation

Predict k1 post-discharge skin temperature as
B + [T_k1(60)-B] exp[-lambda_k2(t-60)].
Require T_k1(60)>B for this cooling-only screen. Check three predeclared periods:
60–600 s (unfitted early check),600–1800 s and1800–3600 s. All are checked against
same-scenario frozen analytic prior and persistence atT_k1(60). Exact boundaries
use interpolation; no boundary sample enters parameter estimation because no
parameter estimation occurs. Do not re-anchor after60 s.

Use the already reviewed exponential-versus-piecewise-linear metrics, including
within-segment residual extrema; verify8-/32-point quadrature agreement within
1e-10 K² MSE. Report every period/scenario/comparator, signed bias, RMSE, maximum
error and full coverage. Carry the inherited thermal-proxy2 K/5 K gates separately;
no new physical pass criteria. A transfer is descriptively improved only if both
comparators' RMSE decrease in **all three** periods. Failure is preserved, not
followed by refitting. Neither improvement nor broad-gate passage identifies h,
core temperature, true ambient or an electrical-error cause.

Keep source naive dates and skin temperature, mean measured discharge current,
observed discharge charge and initial/final cooling temperatures in the result to
make specimen/episode differences visible. Do not replay state across files or
claim equal SOC from matching labels. Previous voltage RMSE failures and their
50 mV gate are untouched.

## Bound and durable output

One saved-data process,60 s and1 GB address-space limit, single BLAS thread. No
DFN solve or optimizer is called. Publish the protocol, executable script, tests,
source/implementation/frozen-fit hashes, full prediction CSV, summary JSON and
reviewed plot. The committed normalized input makes reproduction independent of external
archive retention. The original raw input remains in the previously saved
immutable archive as an additional provenance check; the repository is the
authoritative source of this experiment and its results. Complete independent
review and CI, then decide the next experiment from observed transfer limits.

Data: Catenaro and Onori, [10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
CC BY4.0. Thermal equation and identifiability assumptions inherit the
[k2 protocol](stanford-k2-cooling-protocol.md). This is test-fixture/observable
characterization, not an experimentally verified manufacturing-process model.
