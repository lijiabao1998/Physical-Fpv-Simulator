# Frozen early-response contrast persistence protocol

Status: proposed before persistence calculations; independent review required.

## Question and estimand

Does the specimen-dependent early voltage/current descriptor remain an adequate
summary of the between-record voltage-fall contrast later in discharge? This is
a development characterization of previously viewed records, not blind validation
or identification of contact resistance, initial SOC, kinetics, or diffusion.

Freeze each specimen's descriptor r_j = (A_j,low - V_j,low(1.001 s)) /
I_j,low(1.001 s) from the committed cross-rate report. A is the immediately
preceding recorded rest endpoint; I is positive discharge current. Do not average,
refit, tune the query, or substitute a later descriptor after seeing outcomes.

At a common elapsed time t in the archived 1C records, define D_j(t) =
A_j,high - V_j,high(t). The prediction is P(t) = I_1(t) r_1 - I_2(t) r_2.
The discrepancy is Z(t) = D_1(t) - D_2(t) - P(t), in volts. Retain each
individual D_j - I_j r_j as well: cancellation in the contrast must be visible.

Also retain the archived DFN residuals E_j = M_j - V_j and verify the identity
E_1 - E_2 = M_1 - M_2 - (A_1 - A_2) + D_1 - D_2. This identity does not
turn a descriptive offset into a valid replacement DFN trajectory.

## Frozen evaluation support and summaries

Use the intersection of both measured and both archived model supports. No
extrapolation or unobserved load-onset reconstruction. The initial 1.001–10 s
interval is an already examined reference, not a new evaluation partition.
Evaluate later windows 10–60, 60–300, 300–900, 900–1800 s, then 1800 s to
common end, clipping only against support and marking any empty window explicitly.
Compute signed mean, RMS, maximum absolute discrepancy and endpoint values using
the union of all native voltage/current/model knots and window boundaries.
Piecewise-linear signals permit exact trapezoidal signed integrals and analytic
quadratic squared integrals; maximum absolute value occurs at a knot.
Report the same summaries for individual errors, original E_1/E_2, their
contrast, measured skin-temperature contrast, and archived bulk-temperature
contrast. Temperature observations and model bulk temperature remain different
observables.

A secondary conditional alignment evaluates Q = 0.5, 1, 2, 3, 4 Ah from each
record's first observed loaded sample. Define Q_j(t) = integral from the first observed loaded sample to t of
I_j(s) ds / 3600, in Ah. Reject nonpositive recorded discharge current. Integrate
the current piecewise linearly; invert each interval's monotone quadratic integral
with a stable constant-current branch and without extrapolation. A charge query
must lie in that specimen's measured AND archived-model support; otherwise retain
it as unavailable with a reason, without clamping the query or re-zeroing Q.
Verify the inverse by forward integration within 1e-12 Ah; this is a numerical
reproduction bound, not charge-measurement uncertainty. Interpolate voltage/current/model/skin at each resulting time.
Report these five point comparisons individually, with timing and temperature;
no claim of matched absolute SOC, inventory or history. Preserve the first-sample
omitted interval explicitly. Do not pool time-aligned and charge-aligned results.

## Interpretation, falsifiability and limits

An exactly time-invariant current-proportional descriptor predicts Z = 0.
Freeze 1e-12 V as the arithmetic identity/reproduction tolerance, never as a
physical-equivalence threshold. Report departures in their actual units;
without experimental uncertainty, do not attach a physical/statistical PASS or
claim a unique falsified mechanism. Growth or sign change of Z constrains the
adequacy of this simple descriptive continuation. Small Z supports only this
conditional observable prediction. Report absolute magnitudes, not a gate tuned
to the outcomes. The historical 50 mV single-cell terminal-voltage gate stays
unchanged and failed, regardless of the contrast result.

Unknown prior histories, different rest/charge records, temperature and acquisition
latency remain confounders. The low/high-rate records have roughly 45-hour
unobserved gaps; no continuous state replay is allowed. Full-record evidence
and source hashes must be retained, including the archived model implementation
identities. No correction is applied to internal states, heat, cutoff or capacity.

## Inputs and bounded execution

Reuse the exact committed cross-rate report/source hashes, committed k2 measured
records, committed archived mesh-120 k1/k2 model curves, and the cached verified
k1 1C source workbook already used for the prior onset and series-term packages.
Normalize and persist the full relevant k1 rest/discharge source rows with the
original workbook hash, row indices, clocks and CC-BY-4.0 attribution. No network
request, new DFN solve, fit, new source or paid resource is permitted in this
increment. Analysis budget: 60 seconds, 1 GiB. Test synthetic constant contrast,
time-varying contrast, unequal currents, exact charge inversion, unsupported
queries and perturbed/hash-mismatched inputs. Independently review algebra,
coordinate transformations, units, source support and interpretation before run.
