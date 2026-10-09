# Frozen near-start rest-to-loaded voltage comparison

Frozen 2026-10-09 after the charge-aligned low-rate comparison, before calculating
this onset screen. This is a post-hoc characterization of previously viewed data.
It is not a blind validation or a parameter calibration.

## Question

Can the model's initial bulk-OCV offset from the measured pre-discharge rest
endpoint account for the early terminal-voltage residual? Compare that offset
with the measured and saved-model voltage changes at four predeclared near-start
times. This uses a local observed rest anchor within each original record,
without reconstructing history between records or fitting a voltage shift.

Inputs are the checksum-pinned cached k2 0.05C/25C workbook, committed k2 1C
records, and saved k2 DFN state scalars. No download or new physical solve.
All gates and model parameters remain unchanged. Preserve the 55.003054 mV
historical 1C failure against 50 mV.

## Source and timing qualification

Use all original rows of the canonical pre-discharge rest (Step_Index=4) and
following discharge (Step_Index=5). No filtering, sorting, averaging or smoothing
of source rows. Require finite values, strictly increasing phase clocks and naive
dates, zero recorded rest current, strictly negative raw discharge current and
consistent command origin (Test_Time minus Step_Time) within 1e-6 s. Use existing
1 s naive-date/test-clock qualification and report observed discrepancies.
Retain row numbers, dates, currents, temperatures and both clocks.

For each record disclose the last rest and first load times, the command origin
inferred from step time, and the recorded rest-to-load sample bracket. The source's command clock is not a measured
subsample current-switch timestamp. Instrument/filter latency and synchronization
are not independently known. The sample bracket is not a verified bound on physical switching time.
Do not call this an instantaneous ohmic pulse test.

Use T0=max(first observed 0.05C discharge Step_Time, first observed 1C discharge
Step_Time, first supported model time). Evaluate at [T0, 2, 5, 10] s, requiring
T0<2 and complete support. Interpolate linearly only between actual adjacent
samples; never extrapolate into the unobserved first interval. Report exact times,
neighboring measurement timestamps and interval widths around each query.
These compare nominal command/model clocks, not independently synchronized
elapsed time since physical current onset.

## Rest anchors and observations

The anchor for each record is its last observed rest voltage, without fitting.
Also report both the last 10 s and last 60 s rest tails: actual support, time-
weighted mean voltage, extrema, endpoint change and endpoint-change/time slope.
These summaries describe residual drift, not equilibrium certification or
experimental confidence intervals. No selection of whichever tail looks better.

At every fixed query report measured voltage, current and skin temperature for
both records. Report the archived model's terminal voltage, bulk OCV and bulk
temperature. Its initial bulk OCV at model time zero is a published-inventory
reference, not a simulated rest relaxation or measured OCV. Report skin-to-skin
and model-bulk-to-skin temperature differences without substituting observables.

## Algebra and interpretation

Let B be the saved model initial bulk OCV, A the 1C measured rest endpoint, H(t)
the measured 1C voltage and M(t) the saved model terminal voltage. Define:

- Initial reference offset C=B-A.
- Observed rest-to-load voltage fall Dobs=A-H(t).
- Model initial-reference-to-load fall Dmodel=B-M(t).
- Terminal residual E=M(t)-H(t)=C+Dobs-Dmodel.

Require arithmetic closure within 1e-12 V. Report E-C as the residual remaining
under the descriptive constant rest-anchor offset correction; do not apply or
promote that correction to a model. The offset-only hypothesis requires E-C=0
at these fixed queries. Report magnitude/sign and whether zero is incompatible
with arithmetic tolerance 1e-10 V, conditional on the rest anchor and saved
trajectory. This is an algebraic compatibility statement without measurement
uncertainty, not a statistical rejection of initial SOC/inventory errors.
Changing true initial inventory can alter the whole trajectory and is not
represented by a constant voltage offset.

For each measured record also report (Vrest-Vloaded)/Ipositive at each fixed time,
labelled **finite-time apparent voltage response per ampere**. For the model use
(B-M)/the saved applied current. These ratios mix ohmic, kinetic, diffusion,
relaxation, thermal/history and sampling effects. Do not call them identified
series resistance or compare them as equivalent to 30 s DCIR or 1 kHz ACIR.
Do not select or fit an R, infer equal absolute SOC, or compare instantaneous
values against the historical aggregate 50 mV RMSE acceptance gate.

## Bounds, tests and deliverables

One cached-data analysis, 60 s wall / 1 GB address space / one BLAS thread.
Independent protocol review before analysis; independent implementation and
interpretation review before publication. Tests cover exact decomposition,
current sign/units, constant-offset synthetic compatibility and incompatibility,
invalid clocks, unsupported queries, source hashes and no-download/no-solve
reproduction. Persist normalized source slices with complete row provenance,
reproducible code, fixed-query results and scientific limitations in the draft
candidate repository. No GUI, deployment or parameter change.

Independent protocol review: GO, with the recorded sample bracket and nominal
clock wording clarified before actual-data computation. Full original phase4/5
rows are inspected and qualified; the additional persisted low-rate support slice
contains every rest row and discharge start through the first sample at/after10s.
The complete low-rate discharge remains in the preceding committed dataset.
