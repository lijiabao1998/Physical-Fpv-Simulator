# Bounded current-source replay after evaluator precision correction

Frozen before launch on 2026-10-09. This is implementation revalidation of two
existing cases, not parameter calibration or acquisition of a new dataset.

## Cases and comparison

1. Stanford k1: run exactly one DFN/ORegan2022 lumped mesh120 case with the
   unchanged Stanford validation, scheduling and memory protocols. Reuse the
   authenticated mesh80 curve with its original failed empirical report.
2. Representative thermal: run exactly one existing 5 A/25°C DFN/ORegan2022
   lumped mesh120 case, initial 297.75 K, h=15 W/m²/K. Reuse the authenticated
   mesh80 curve and parameter identity.

Both retain tolerance 1e-7, original forcing and cutoff/temperature guards.
Spatial targets remain maximum ΔV <=5 mV, ΔT <=0.1 K and cutoff-capacity
relative difference <=1%, with original physical/event gates. K1 empirical
voltage RMSE remains <=50 mV, maximum error <=300 mV and all other original
capacity/energy/coverage gates unchanged. Execution success is not empirical
success. No cutoff extension, fit, gate relaxation or search is permitted.

The standalone evaluator changed, but core solver forcing still uses the same
PyBaMM.Interpolant and the same exact knot bytes. Charge integration is unchanged.
A preflight requires every recorded calculation input hash except
current_profile.py to match the prior verified contract, and pins its new hash
3ac01b06b0b43e6fa464d861e5117a7d28f1b4f55f339ec781069a76e74905a6.
It verifies mesh80 provenance, parameter identity and content-profile identity
before reuse. Thus this is an explicitly mixed-source 80→120 comparison with an
unchanged solver/forcing law, not a claim that mesh80 was newly solved. If any
other calculation dependency differs, stop before solving and review the scope.

## Inputs and durability

K1 uses only the already-selected workbook NMC_k1_1C_25degC.xlsx (SHA256
b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6) and its existing
checksum-pinned manufacturer specification from the committed Stanford manifest.
Reacquiring those same bytes is permitted; no new dataset or k6 request occurs.
Thermal inputs and mesh80 references are committed locally.

Before each solve, upload a 90-day input artifact containing the exact checked
source/config/reference files, raw K1 inputs when applicable, protocol, source
commit, versions, physical/profile identities and SHA256 manifest. Upload must
succeed before launch. Record launch and terminal receipts. Always upload complete
or partial output, logs and status after execution; independently verify and
persist the returned evidence before updating any current-source cache. Preserve
historical evidence under its original commit and run identity.

## Resource and launch accounting

Exactly two scientific solves total, sequential independent jobs. Each uses the
existing ubuntu-latest CPU runner, one worker, 1200-second scientific wall limit
and 4,000,000,000-byte worker address-space limit; job limit remains25 minutes for
setup/packaging. Total planned scientific ceiling2400 seconds, never concurrent;
there is no automatic retry or budget extension. If preflight/setup exceeds180
seconds, do not launch: preserve at least120seconds of job time beyond the
scientific limit for termination and output upload. Existing one-thread environment
settings apply. A supervisor plus external timeout terminates a failed run;
up to5 seconds of termination grace is bookkeeping, not an extended solve budget.

The connector does not expose workflow_dispatch. Launch is an explicitly reviewed
one-shot commit of the unique path .github/workflows/current-source-replay-20261009.yml,
restricted to battery/research-core-v1, attempt1, with a fixed singleton and no
cancel-in-progress. A preflight API check rejects any earlier run of this unique
workflow. Ordinary PR cache-miss workflows remain fail-closed and cannot launch
these solves. Standard existing Chen CI is unchanged and may run its normal tests.
The launch file must not be rewritten to trigger a second run. Later report/cache
commits do not match its path trigger.

## Outcomes and stopping

A complete result establishes only this exact new-source run and its recorded
gates. Preserve empirical failures even if spatial convergence passes. A budget,
resource, source or numerical failure remains failed/incomplete; no automatic
repeat. Preserve both receipts, close cache verification only with genuine new
source-matched evidence, then stop this validation task. No k2 rerun, broad cohort,
GUI, deployment, paid runner, new credentials or unrelated experiment is included.
