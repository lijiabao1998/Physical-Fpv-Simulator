# K2 fixed-mesh tolerance sensitivity, protocol v1

Frozen before execution, 2026-10-09. This is a distinct numerical diagnostic against the preserved coarse failure at commit `9c45fd1ea2db8ad5aaa6d00edaaa22456aa2ef7b`, scientific run `37948404436` (source `208d34882acb79b32b48e578575760580675c868`). It does not retry that workflow.

## Question and controlled change

Does reducing both IDAKLU scalar relative and absolute integration tolerances from `1e-7` to `1e-8` reduce the full-trajectory capacity-state versus exact imposed-charge discrepancy at fixed mesh80, while leaving voltage, temperature and cutoff observables stable? Both tolerances change together; this cannot distinguish relative from absolute tolerance sensitivity, integration error from solver output interpolation, or certify spatial convergence.

Only those two solver tolerances change. Reuse the existing low-rate builder, equations, ORegan2022 parameters, lumped thermal model, initial inventories, initial skin-temperature proxy, imposed current, mesh80 discretization, all 21 scalar outputs, full 1 s/fixed-Ah output grid, event definitions and physical/empirical audit code without editing them. The builder is called once and its not-yet-used solver receives the two new tolerances before setup. Persist original and changed configuration and assert that all other metadata and parameter/forcing identities agree. Require the execution Python and all pinned scientific dependency versions to match the archived baseline. Before the sole solve, assert no model-level absolute-tolerance override and inspect the effective expanded IDAKLU absolute-tolerance vector after setup; every entry must be 1e-8 and relative tolerance 1e-8. Recheck after solving. These are local solver state error weights, with the model's existing variable scaling; they are not a guaranteed global error bound in Ah, volts or kelvin.

No fitting, new source acquisition, selected capacity window, replaced charge state, correction term or capacity threshold change. The previously published 1e-7 result stays FAIL. The historical high-rate 55.003 mV FAIL stays unchanged.

## Evidence and observables

Baseline ZIP SHA256: `f841d0016f9787186f129c5c563226696fd340ab5c6212fcc8c2eb59ae5546cb`, stored as two repository parts. Verify its complete identity before using its mesh80 arrays. Baseline maximum absolute capacity closure is 1.1002957274186542e-6 Ah by the unchanged audit, 1.1002956981087664e-6 Ah by the independent rational oracle, at 61597 s. Baseline endpoint alone is below the gate and is insufficient.

For the new trajectory, report the maximum/minimum signed charge error across every prescribed saved sample plus the true endpoint (continuous-time extrema remain unverified), time of maximum absolute error, number and first/last times exceeding 1e-6 Ah, and cutoff error, using both the original analytic integral and independently evaluated exact rational integration of the pinned piecewise-linear forcing. Report their agreement. Verify saved final state against all 21 endpoint observables, source hashes, forcing/RHS units and all physical audits.

Compare the two trajectories at their exact shared saved query times without resampling or extrapolation. Report common-support duration, last shared query time, earlier true event time and sample count, maximum absolute voltage and bulk-temperature differences, and separately each true event endpoint, observed-start delivered capacity and cutoff-time difference. Different event endpoints are never silently treated as common times.

## Predeclared interpretation and unchanged gates

The narrow hypothesis is supported if the new full-support maximum charge error is smaller than baseline and satisfies the original 1e-6 Ah closure gate. A decrease that still exceeds the gate indicates sensitivity but leaves the defect unresolved; no decrease or a larger error does not support the proposed remedy. Timeout, incomplete/invalid outputs or other physical failure leave the diagnostic unverified or failed, with complete available evidence retained. This single comparison cannot establish a convergence order or identify a unique numerical mechanism.

Use the existing numerical comparison bounds descriptively: maximum common-query voltage difference <= 5 mV, temperature difference <= 0.1 K, and relative observed-start endpoint capacity difference <= 1% (absolute difference divided by the tightened run's endpoint charge, matching the existing refined-run denominator). Both runs must reach the voltage cutoff. These bounds were already part of the low-rate protocol; passing them here is tolerance stability at mesh80, not mesh80-to120 convergence.

All original physical gates apply unchanged: maximum charge closure 1e-6 Ah; relative lithium drift 1e-6; finite outputs and state witnesses; positive electrolyte and heat capacity; electrode bounds with their original tolerance; thermal-energy closure <=1%; original temperature guard and cutoff. All empirical gates stay 50 mV voltage RMSE, 300 mV maximum error, 5% capacity/energy error, 95% coverage, valid cutoff and physical audit. Report the 2 K/5 K skin/bulk temperature proxy gates with their original limitations. No fresh independent thermal validation is claimed. Below-25 C heat-capacity domain caveat remains explicit.

Even if every new gate passes, spatial convergence remains UNVERIFIED because fine120 was never run. No automatic fine stage follows this diagnostic.

## Execution, resources and stopping

One ordinary free Ubuntu GitHub Actions job, one mesh80 DFN solve maximum, one attempt, singleton guard, no retry and no parameter or tolerance search. Scientific subprocess wall limit 1200 s, address-space limit 4,000,000,000 bytes, one numerical thread. The outer workflow may allow 30 minutes for existing pinned dependency installation, input persistence and evidence upload; it cannot extend the 1200 s solve/worker budget.

Baseline same-mesh run used 67.819 s and 650700 KiB peak RSS. Tenfold tighter tolerance can increase runtime, so this observation supports feasibility without guaranteeing completion. Before launch, build/setup without solving under the same 4 GB limit and independently review the implementation, limits and immutable comparison. Stop after this one attempt whether it passes or fails; do not launch mesh120 or another tolerance.

Before scientific execution, persist all original model/source dependencies, the new runner/protocol/workflow, normalized observed and forcing arrays, output grid, complete parameter values, both original and tightened configuration, runtime versions and source/run identities. Upload inputs and require the existing bounded same-endpoint artifact ID/run/head/digest verification. Preserve native final state, scalar arrays, all reports and failure receipts with an always-upload step. Independently download/materialize and hash-verify the final archive, then commit durable evidence and conclusions to the draft branch.
