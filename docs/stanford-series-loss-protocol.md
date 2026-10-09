# Frozen shared series-like voltage-term compatibility screen

Frozen2026-10-09 before evaluating real-data quadratic coefficients or feasible
intervals. This follows the negative cooling-transfer result at03c2e576. Existing
residuals, rest endpoints and specimen conditions have already been inspected;
there is no blind-validation claim.

## Narrow hypothesis and predeclared decision

For each archived prediction, define e(t)=V_model(t)−V_measured(t), with observed
positive discharge current I(t). Ask whether **one constant R≥0**, shared across
k1 and k2, can make the algebraic residual e(t)−I(t)R have time-weighted RMSE≤0.050 V
on each cell's existing complete common measurement/model interval.

Return every individual feasible set and their intersection. The primary outcome
is empty/nonempty/numerically unresolved shared intersection. Do not choose an R,
fit a second parameter, alter current/time/initial state, select a more convenient
interval, change the50 mV gate or turn a feasible interval into a measured resistor.
For context only, also calculate coefficients/sets over four equal fractions of
each complete measured duration, clipping the last to available model coverage.
These descriptive regions are not additional acceptance requirements.

The assumption of shared R is a hypothesis, not evidence of a shared fixture,
channel or resistance. k1/k2 are distinct specimens. A nonempty set would show only
algebraic compatibility with this particular RMSE requirement, not physical
validation. An empty set would rule out this shared term as sufficient on these
frozen trajectories; it would not rule out real contact resistance, variable
resistance or combinations of state, instrumentation and electrochemical errors.

**This is not a closed-loop DFN or circuit experiment.** A real added resistance
could change heat generation, voltage cutoff and the valid discharge interval.
All current/state/temperature curves and existing event times stay frozen here.
No corrected curve is promoted as an accepted simulation, no event is recomputed,
and no claim is made about capacity/energy/max-error/full-trajectory acceptance.
The unobserved initial intervals and measured tails beyond model cutoff stay
explicit. A common-window calculation cannot erase those separate failures.

## Inputs, identity and timing audit

Use only existing authenticated artifacts:

- k1 current-source replay37887926852 at744794b02d44bcbfc702ad8e5c403782128d11b0.
  OutputZIP SHA256`6c6e0c101e24266fe39b367b294751e06c0676fc59043303dbadfef8f0406ae8`;
  mesh120 voltage CSV SHA256`84e181cd1c04180be660791abb42790862d35d4b5f2bd99b38fa5332b03d326d`,
  byte-identical to the preserved historical k1 fine curve. Original workbook
  SHA256`b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6`.
- k2 recovery37871885149 at50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84.
  Committed ZIP SHA256`2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d`.
  Original workbook SHA256`20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086`.
  This remains historical evidence for its original implementation; the new
  analysis does not certify a new k2 solve or relabel it as current-source science.

Verify archive/member identities, original measured current/voltage arrays,
recorded forcing at source knots and preserved model voltage. Align by the
original commanded discharge-step clock, never by shifted timestamps or fitted
capacity. On the union of model, measurement and current knots inside each original
common interval, reconstruct e and I with piecewise-linear interpolation.
Require positive discharge current, finite/strict clocks, correct current sign
and reproduction of the published zero-correction RMSE within1e−12 V.

Preserve source cell names, dates, measured current/charge, initial concentrations,
initial temperature, pre-rest voltage and initialization assumptions. Both use
DFN/ORegan2022 and nominal298.15 K ambient, but measured skin initialization differs.
Published initial electrode concentrations are not SOC inferred from these cells'
rest voltages. A similar full-cell OCV does not identify equal electrode inventories.
Observed discharge Ah is not a measured equilibrium capacity or SOH. k1/k2 source
step starts near1 s leave switching dynamics unobserved. No claim of identical
manufacturing lot, calibrated wiring or known sense locations is introduced.

Persist a lossless normalized input artifact with member/raw-source hashes,
original conditioning metadata, per-cell times/residual/current arrays and coverage.
Normalized input is`benchmarks/stanford-series-loss-inputs.json.gz`,123235 bytes,
SHA256`5ea98848b8759550fb92f21cac74a1edf8ddbc8b284285c3a42cfcd862cd4d8c`;
uncompressed JSON SHA256`dc673cd345c38ae67248d18eb5a81f2c10ede6e2c435cd0d7908d7062e758653`.
It retains3988 k1 knots and3992 k2 knots with source/current/clock checks.
Default reproduction must use committed files, without a new download. Optional
original-archive verification must retain the original inputs unchanged.

## Exact integral and numerical checks

On a segment of duration dt, linear endpoint values e0,e1 and i0,i1 give:

- integral(e²)=dt(e0²+e0e1+e1²)/3
- integral(I²)=dt(i0²+i0i1+i1²)/3
- integral(eI)=dt(2e0i0+e0i1+e1i0+2e1i1)/6

After summing and dividing by duration, set C=<e²>, B=<eI>, A=<I²>.
Then E(R)=AR²−2BR+C. Solve E(R)≤0.050² analytically, intersect with R≥0,
then intersect across cells. No resistor grid search or optimizer is used.
Report coefficients with units and the discriminant. A discriminant within a
64×machine-epsilon×(B²+|AC|+A×gate²) roundoff error bound is numerically unresolved rather than widened into
a passing interval. Exact floating-point D=0 retains its candidate singleton but
is still classified unresolved without exact-arithmetic proof; intersections
formally retain closed endpoints. Root clipping near R=0 and shared-root
contact use propagated root-roundoff guards, not just relative endpoint precision.
For resolved D, each guard includes bound_D/[A(sqrt(D)+sqrt(D−bound_D))]
plus64×machine-epsilon×(|B/A|+max|roots|). Compare shared endpoints with the sum
of the maximum lower-root guard across all sets and maximum upper-root guard
across finite-upper sets, plus64×machine-epsilon×(|lo|+|hi|). This retains
ambiguity when roundoff can change which set supplies a limiting endpoint. Near-contact
cases are unresolved rather than declared empty/nonempty. These are numerical
roundoff guards, not physical or calibration uncertainty intervals. Exact floating
contact retains a candidate singleton for an optional exact proof; no such
ambiguous case is promoted. Physical gates are unchanged. Coefficients, interval roots
and signs are tested against independent exact-rational synthetic examples;
three-point Gauss integration checks actual coefficients to1e−12 in their units.
Verify endpoint/midpoint inequalities as numerical consistency, not extra physics.

## Source grounding, resources and stop

The [authors' primary paper](https://pangea.stanford.edu/ERE/pdf/OnoriPDF/Journals/60.pdf)
uses pulse-front voltage/current changes and reports an SOC-/sample-averaged NMC
resistance. That different observable does not identify an extra fixture term in
these constant-current records. The [LG-authored tentative specification](https://www.dnkpower.com/wp-content/uploads/2019/02/LG-INR21700-M50-Datasheet.pdf)
uses a30-second0.5C test at50% SOC for DC resistance, distinct from1kHz impedance
and these approximately1-second switching observations. Neither value is a prior
bound or an acceptance target for this algebraic R.

One normalized-data evaluation,60 s/1 GB, single BLAS thread. No new source,
DFN solve, parameter sweep, corrected experiment or threshold change. Independently
review the protocol/algebra before evaluating real sets; publish the complete
sets including failures, input hashes, code/tests and limitations through draftPR
and verified CI. Decide further work from the result, not by adding free parameters
until the same two records pass.

Measurements/derived inputs: Catenaro and Onori,
[10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), CC BY4.0.
