# Conditional k2 low-rate voltage reference screen

Protocol frozen before recovering or examining the low-rate waveform, 2026-10-09.
This is a previously selected, previously summarized public record, not a blind holdout.

## Question and limits

Can the saved fixed-inventory ORegan2022 bulk-OCV trajectory serve as an upper
voltage reference for the measured 0.05C discharge when aligned by recorded
passed charge? This is a conditional joint-compatibility screen, not an OCV
measurement, a parameter fit, or an independent validation of internal states.
The loaded 0.05C voltage retains polarization. Equal discharged Ah does not
establish equal absolute SOC, lithium inventory, capacity, degradation state,
temperature, hysteresis state, or preceding relaxation history.

The low-rate record ends at naive timestamp 2019-08-31T21:41:12.806; the 1C
record starts at 2019-09-02T19:11:01.133. The 163788.327 s (45.4967575 h)
unobserved gap cannot be replayed as a continuous state history. The worksheet
timestamps have no recorded timezone. No missing history will be synthesized.

## Bounded source recovery

Recover only `NMC_k2_0_05C_25degC.xlsx` from its existing committed official
manifest entry in `data/stanford-k2-k6-history-manifest.json`:

- DOI: 10.17632/kxsbr4x3j2.2; Catenaro and Onori; CC BY 4.0.
- URL: https://data.mendeley.com/public-files/datasets/kxsbr4x3j2/files/33a17546-8a30-4151-a65e-d2ec6451ca28/file_downloaded
- Exact size: 6029678 bytes.
- SHA256: `6bfaeb45fe90b76b6bd5973f0cb481b5d42db81cd2729e9be44121b44296d174`.
- One attempt, 120 s wall limit, 1 GB address-space limit, at most expected size
  plus one byte read. Retain the existing workbook safety limit of 50 MB inflated
  contents. A size, hash, format, permission or HTTP 403 failure stops recovery;
  no alternate source/route or retry of the three blocked k6 records.
- Reuse checksum-verified cached 1C observations and archived state scalars.
  Persist source identity, exact normalization and hashes with the result.

## Frozen comparisons

Use every original row of the single canonical Step_Index=5 phase, retaining
original worksheet row indices. Require the canonical [1,2,3,4,5,6] phase sequence.
Convert strictly negative raw discharge current to positive discharge. Reject
nonfinite or missing values, wrong current sign, duplicate/reversed clocks or
nonincreasing charge. Do not filter, sort, average or bridge invalid records.
Integrate piecewise-linear observed current with trapezoids to obtain recorded
passed Ah. Do not infer true initial SOC from the discharge integral.

Report both declared alignment scenarios without selecting between them:

1. Recorded-start: independently set each measured discharge's first recorded
   sample to zero Ah; subtract the saved model charge at the 1C first-sample time.
2. Command-start hold: add each source's first current times its first step time
   divided by 3600, explicitly assuming constant current over its unobserved
   initial interval. Keep model charge on its original command-start axis.

These are conventions, not uncertainty bounds. Construct piecewise-linear voltage
curves on their respective charge knots. Compare only their common supported
charge interval; disclose each excluded beginning/end and covered charge fraction.
No extrapolation, optimized shifts, SOC/capacity scaling or selected subwindows.

On the union of charge knots evaluate low-rate measured voltage L, 1C measured
voltage H, saved model terminal voltage M and saved bulk OCV U. Report:

- S = U - L, the conditional static-reference difference;
- G = L - H, the measured rate-to-rate voltage difference;
- P = U - M, the model's bulk-to-terminal difference;
- R = M - H = S + G - P, with numerical closure checked within 1e-12 V.

U retains the archived 1C model temperature and published electrode inventory;
it is not a low-rate isothermal OCV curve. Its negative/positive active capacities
5.203221458/7.163230036 Ah are model quantities, not measured k2 electrode
capacities. The upper-reference premise remains unestablished because inventory,
temperature and history equivalence are unknown.

The identity is bookkeeping; the largest component does not identify the cause
of empirical error. Report full-common-interval and four equal charge-quarter
means, RMS, extrema and sign fractions, using exact piecewise-linear integrals, weighted by charge rather than sample count
or elapsed time. Exactness refers to the declared V(q) interpolants: over a
segment of width dq with endpoint values a,b, integrate its square as
dq*(a*a+a*b+b*b)/3. Insert common-support endpoints and quarter boundaries;
locate zero and threshold crossings analytically, including zero plateaus.
Reject empty overlap and extrapolation.
Quarters are descriptive and do not create extra acceptance gates. Report source
skin-temperature ranges, saved bulk-temperature range and their differences;
these temperatures are different observables, not interchangeable ground truth.

## Predeclared interpretation

Under matched absolute inventory/SOC, applicable equilibrium OCP functions and
thermal/history conditions, with net nonnegative discharge polarization, U should
not lie below L. Report every interval where S < -1e-10 V, its charge measure and
most negative value. The 1e-10 V guard only excludes arithmetic noise; it is not
experimental uncertainty. Violations challenge the conjunction of these
assumptions. They cannot uniquely falsify OCP, identify a kinetic coefficient or
prove missing resistance. Absence of violations is compatibility, not validation.
An unknown inventory mismatch can invalidate the alignment premise itself.

Do not label this diagnostic PASS/FAIL against the 50 mV terminal-voltage gate.
The historical 1C 55.003054 mV result remains a failure at that unchanged gate.
No fit, new DFN solve, thermal coefficient change, gate relaxation or parameter
promotion is allowed. A next causal claim needs an independently constrained
initial inventory/SOC and temperature/history, or an independently measured
near-equilibrium OCV reference with uncertainty, not an optimized alignment.

## Reproducibility and review

Independent physical review precedes data recovery/analysis. Synthetic tests must
cover current sign/units, missing-start conventions, unequal charge support,
exact voltage identity and analytic integration, finite/monotone validation,
and negative cases that reject extrapolation or altered source hashes.
Analysis is bounded to 60 s and 1 GB with one BLAS thread. Persist protocol,
normalized source arrays, hashes, reproducible script, findings and plot in the
candidate repository. Source and historical evidence remain immutable.

Independent physical review: GO after the phase, charge-weighting and archived
OCV provenance clarifications above, frozen before recovery. The 1e-12 V
arithmetic identity tolerance is separate from the archived physical accounting
closure (~9.94e-10 V). Synthetic cases also cover zero plateaus and empty overlap.
