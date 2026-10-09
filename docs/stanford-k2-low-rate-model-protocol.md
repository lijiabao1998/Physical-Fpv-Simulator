# Proposed bounded k2 low-rate model-response experiment

Status: reviewed physical implementation; first managed attempt stopped in
preflight, before either battery solve. Independent physical/software review
accepted the bounded model protocol. A separately identified replacement needs
the reviewed preflight amendment below and explicit launch coordination.

See the [implementation and resource checks](stanford-k2-low-rate-model-readiness.md).

## Falsifiable development question

With parameters and initial electrode inventories unchanged, does the model
reproduce the observed low/high-rate voltage-shape difference within k2, or does
its conditional rate response differ materially from the archived measurements?
The primary comparison is raw voltage, not the descriptive V+Ir quantity.
No resistance, SOC, inventory, transport, kinetics or thermal parameter is fitted.

At Q = 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5 Ah from each record's first observed
loaded sample, report G_observed = V_low − V_high and G_model = M_low − M_high.
Explicitly, G_model − G_observed = E_low − E_high, where E = M − V.
Verify that identity and report the full vector without a new rate-response PASS
threshold. Crossing 50 mV at low rate versus 55.003 mV at high rate is not a
decisive causal separation.
Retain the two individual errors, times and skin/bulk temperature differences.
Any point outside either measured or corresponding model support is unavailable;
no extrapolation or replacement query is allowed.

If low-rate errors are small while the same frozen model has the known high-rate
error, that constrains a solely rate-independent voltage-level explanation under
these assumptions. If low-rate errors persist, a common baseline/state/domain
mismatch remains plausible. Neither outcome uniquely identifies diffusion,
kinetics, initial inventory or thermal causes, because prior history, actual
ambient temperature and true internal initial state are not independently known.
All observations were previously viewed: this is development testing, not blind
validation or evidence of manufacturing simulation.

## Explicit experimental domain, not a change to the ordinary core

The ordinary core rejects currents below 0.5 A and remains unchanged. Implement a
separate, clearly experimental driver accepting only this hash-pinned k2 record,
with measured discharge current constrained to 0.249–0.251 A. This is an explicitly
unvalidated research-domain extension, not a silent relaxation of the ordinary
core or its source identities. Do not invoke the ordinary core with spoofed
current metadata. New driver/config/protocol identities must accompany every
result; existing cached validation cannot certify it.

Use PyBaMM and the repository's exact pinned dependency versions; DFN, lumped
thermal model, ORegan2022 parameters, initial negative/positive concentrations
28866/13975 mol/m3, ambient 298.15 K and heat-transfer coefficient 15 W/m2/K. Initial
bulk temperature is the recorded last-rest skin value 297.4955352783203 K, an
explicit skin-to-bulk proxy assumption. Initial SOC is not estimated from voltage.
The measured rest anchor 4.186485767364502 V is retained as a diagnostic only.
No new thermal calibration or specimen-specific series term is inserted.
The initial temperature is 0.6544647216797 K below the cited 25°C lower bound of
heat-capacity measurements; explicitly retain that property-domain excursion.
Freeze the minimum-voltage cutoff at 2.5 V and upper-temperature guard at 333.15 K.

Input is the already committed complete k2 low-rate CSV, SHA-256
`5c5f0969e411d2be96bcdbb02cfcb397e2fd79d8ad92a26e5466f311d70ae5ef`,
normalized CSV SHA-256
`4c551b20febfc90e59df25a3ef9321aa975a328143a84d6d5f5c427e968f64a9`,
and source-receipt SHA-256
`984b83c1f105493f14d5894441c7bcebee2474e2c3904313213e71633ac89eda`. Use positive measured current with the existing
immutable piecewise-linear CurrentProfile implementation. The unobserved
0–1s command interval uses the first recorded current as a declared modeling
assumption; its charge is never relabeled measured. Stop integration at the
last recorded step time 70369.9178 s or a physical event, whichever occurs first.
Never extend a constant-current tail beyond measured support.

## Numerical procedure and resource accounting

One free existing ubuntu-latest GitHub Actions job; no paid runner or new access.
At most two sequential battery DFN solves, meshes 80 then 120, rtol = atol = 1e−7, under one shared
1200 s scientific wall budget and 4,000,000,000-byte address-space bound per worker.
Use one thread and fresh worker processes; release coarse spatial arrays before
starting fine. A wrapper enforces remaining time, kills timed-out workers and
retains partial evidence. Stop before mesh 120 after a coarse solver or physical-audit failure. Empirical
disagreement alone does not stop the fine solve if resources remain. No automatic
retry, mesh change, parameter search or budget extension follows an incomplete solve.

Use adaptive integration with the complete measured forcing. Export at a fixed
1 s grid plus endpoints and the predeclared charge-query times, capped at 71,000
time points. This fixes the observation grid before outcomes; report its identity
and do not thin it after a memory failure. Dense spatial history is forbidden: the two particle fields alone would require
7.207/16.216 GB at meshes 80/120. Use the pinned IDAKLUSolver output_variables
mode to evaluate and retain only declared scalar observables plus final state.
The explicit list must include voltage, capacity, bulk temperature, total lithium,
total heating, signed surface cooling, effective heat capacity, global minimum
and maximum of both electrode node concentrations and surface concentrations,
and minimum electrolyte concentration at every exported query. Additionally
retain one finite-propagating full-field sum for each electrode node/surface
field and electrolyte; all five witnesses must be finite. Min/max alone are
insufficient because CasADi extrema ignore NaNs. Adversarial NaN/±Inf tests
must confirm that the witnesses restore the complete spatial finiteness check.
Symbolic audit
reductions may be added to model.variables but never alter RHS, algebraic,
boundary, initial-condition or event equations. Verify scalar shapes before solve.
Twenty-one scalar observables plus time at 71,000 samples need about 12.5 MB of numeric output;
this is not a bound on solver factorization memory, which remains capped at 4 GB.

Before launch, require a bounded analytic toy-ODE test demonstrating output-only
versus dense observable equivalence and retained final-state semantics, plus a
non-solving DFN construction audit of every scalar reduction and equation identity.
The [official PyBaMM output-variable guide](https://docs.pybamm.org/en/pybamm-v26.8.0.0/source/examples/notebooks/performance/06-output-variables.html)
and pinned 26.9.0.0 source document this storage mode. Retaining scalar extrema
preserves the specified sampled spatial-bound checks, not unobserved continuous-
time extrema. No audit may be silently dropped to meet memory. The 4 GB/1200 s
limits still apply, and any unresolved feasibility issue blocks launch.

Report the existing numerical thresholds separately: common-support maximum
mesh voltage difference ≤5 mV, endpoint capacity relative difference ≤1%, and
maximum bulk-temperature difference ≤0.1 K, with physical audits passing.
A full numerical-acceptance label additionally requires both physical voltage
cutoffs as in the existing protocol. If either curve stops at the measured-input
boundary first, retain common-support mesh diagnostics but label full endpoint
verification unavailable; do not relax the cutoff requirement.

Audit finite ordered outputs, positive electrolyte, electrode concentration
bounds, lithium conservation, charge-versus-forcing closure and sampled thermal
energy balance using the established tolerances and explicit meanings:
lithium relative drift ≤1e−6, charge error ≤1e−6 Ah, finite electrolyte minimum >0,
node/surface concentration bounds from −1e−6 to c_max + 1e−6 mol/m3, and absolute
thermal stored-minus-net-energy residual / max(integrated absolute generated
heat, 1 J) ≤1%. Preserve
any failure. Export the scalar curves, extrema/audit summaries and parameter,
forcing, dependency and complete driver-source fingerprints.

## Empirical reporting

Report time-weighted low-rate voltage RMSE and maximum absolute error on the
union of native measured and model-export knots, coverage and available endpoint
capacity/energy evidence. Preserve the complete existing gates: voltage RMSE ≤50 mV,
maximum absolute voltage error ≤300 mV, capacity and delivered-energy relative
errors ≤5%, coverage ≥95%, exact minimum-voltage event and physical audits. A measured-input stop is not a model
cutoff prediction; cutoff capacity and cutoff-energy qualification are unavailable in that case.
Define each rate's Q by the analytic piecewise-linear current integral starting
at that rate's first measured loaded time. Exclude the model's assumed initial
interval charge before all capacity and Q comparisons: low rate excludes
0.00006945052080684238 Ah; high rate uses its independently archived forcing
integral at 1.0003 s. Integrate measured energy from the first measured loaded
sample to its end, and predicted energy from the corresponding start to the
actual model cutoff. Do not crop capacity/energy to common voltage support or
substitute measured-endpoint quantities for an absent predicted cutoff. Report skin/bulk
temperature comparison as a proxy with historical 2 K/5 K provenance, not independent
thermal validation. Missing numerical or physical checks prevent an overall PASS.
The historical high-rate 55.003 mV FAIL remains tied to its original implementation.

Cross-rate model comparison uses recovery run 37871885149, source commit
`50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84`, not the later diagnostic execution.
Pin `docs/benchmarks/stanford-k2-recovery-evidence.zip` SHA-256
`2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d`,
member `stanford-k2-recovery/mesh120-timeseries.csv` SHA-256
`179d75db7c0ad638b7811feee9d1d4ecd49615848b5e2c81951671295dca710d`,
input.json SHA-256
`72548f736df9ed90d12c26b27603ccf3ca18681debb261ad1120e5c3d8ab3cbf`,
and forcing.csv SHA-256
`c8a0ec7b33eaf61c890e4825dc23fccfc9149eddf92cd0030deb183ae43f1fb1`.
The archived input starts from mesh 80; the explicitly selected comparison member
is its retained mesh 120 result. The new driver and old driver differ, so
first establish parameter/forcing/algebra equivalence of their shared equations
and explicitly label the distinct execution identities. The allowed-difference manifest is restricted to measured current waveform,
initial temperature, measured-support duration, output-storage mode/grid, and
recorded current-interpolator implementation identity. Model options, all other
constitutive functions, initial electrode concentrations, boundary conditions
and event equations must match by construction and reviewed expression/config
fingerprints; parameter-set names alone are insufficient. The archived core
SHA-256 `1295d1b51e0989021b037ecc8a5b7b66d8e38da43958cfd1df98bc1c031f506b`
still matches the current ordinary core exactly. A non-solving construction test
will compare raw DFN RHS/algebraic/initial/boundary/event expressions against
that core's captured construction, as well as all parameter entries outside the
allowed differences. The parameter/dependency identity and model options must
match; extra scalar audit observables must not modify those equations. Preserve the historical
current-interpolator difference already quantified in its original audit.
No high-rate replay is automatically authorized by this protocol.

Record actual Python, PyBaMM, NumPy, CasADi, SciPy and pybammsolvers versions for
input preparation, execution and later verification. Identical dependency locks
do not imply an identical Python patch runtime: the historical high-rate archive
records Python 3.12.15, whereas local implementation checks used Python 3.12.14.
Disclose the eventual managed execution versions and preserve that distinction.
Persist the native final state with its own hash. Saved-result verification must
rebuild without solving, reevaluate every final scalar from that state, and
recheck the entire frozen observation-grid prefix; a saved success flag alone
does not establish these checks.

## Durable inputs, singleton execution and stopping rule

Before any battery solve, persist the protocol, exact input CSV/metadata, parameter values,
code/dependency hashes, planned config, forcing and launch receipt as a GitHub
artifact and verify successful upload before integration. Use a unique workflow identifier, concurrency group and run-attempt/
prior-run guards to prevent duplicate launch. Publishing implementation alone
must not launch it: add the execution trigger only after review and coordination.
Always upload complete or partial outputs and exit/resource receipts. After the
run, independently verify hashes and metrics and commit durable scientific
artifacts/results to the draft repo. Do not treat workflow exit 0 as scientific PASS.

Stop this experiment after that single bounded execution and verified report,
whether it supports or challenges the model. Any further solve needs a new
falsifiable plan. Ordinary CI must not silently trigger this experiment on a
cache miss or pull-request update.

## Preflight recovery amendment: zero scientific work in the first attempt

[Run 37946424176](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37946424176)
on `e99e9219b35324a3cc77ff3aa6e6e86e688dd7f3` uploaded all 53 prepared-input files,
then its immediate artifact metadata GET returned HTTP404. Both scientific
execution and scientific comparison steps were skipped. The later metadata read
showed the correct artifact/run/head/digest; delayed visibility is consistent with
these observations but is not established as the unique cause. Preserve the
[terminal receipt](benchmarks/stanford-k2-low-rate-preflight-failure.json).
No battery integration or shared scientific wall budget started. Setup/upload
did consume ordinary runner time. Do not rerun that workflow.

One separately named v2 replacement may proceed after reviewed software checks
and CI. It must first verify the prior run still has attempt 1, the pinned head,
terminal failure, exactly one job, and a skipped scientific execution step.
Its own first-attempt/singleton guards remain required. No scientific settings,
two-solve limit, shared 1200-second budget, or 4 GB worker cap changes.

For the newly uploaded artifact, poll only its exact GitHub metadata endpoint
for at most 60 seconds, at 5-second intervals with each request capped by remaining
time and 10 seconds. A process alarm enforces the overall deadline. Only HTTP404
is retryable within that preflight window. Authorization errors, other HTTP
errors, redirects, malformed responses, or mismatched identities fail immediately.
Require artifact ID, name, run ID, head SHA, nonexpired/nonempty metadata and an
exact digest match against the upload action's returned SHA-256. This is a
bounded metadata-read policy, not a scientific retry or a weakened persistence
gate. A second preflight failure stops the replacement; no blind restart follows.

The original input/evidence artifacts remain on GitHub. The connected artifact
download tool produced a temporary file reference, but its cloud materialization
returned HTTP403; that retrieval path was stopped. Zero-solve classification is
based on completed GitHub job steps/logs, not a claim to have inspected ZIP
members that were unavailable locally.
