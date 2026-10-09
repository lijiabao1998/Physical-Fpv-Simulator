# K2 low-rate mesh120 spatial comparison, protocol v1

Prospectively frozen 2026-10-09 after the independently verified mesh80 tolerance diagnostic. This is one distinct spatial-refinement question; it does not retry either previous workflow.

## Question and controlled change

At fixed IDAKLU relative and absolute tolerances of 1e-8, does mesh120 agree with the valid saved mesh80 trajectory within the original numerical bounds while independently passing every original physical audit and reaching the same 2.5 V cutoff event?

Only discretization changes: negative electrode, positive electrode, negative particle and positive particle points 80→120; separator points 40→60. All equations, ORegan2022 parameters, initial concentrations (28866/13975 mol/m3), initial temperature proxy (297.4955352783203 K), ambient (298.15 K), heat-transfer coefficient (15 W/m2/K), measured forcing, output queries, cutoff and 333.15 K temperature guard remain fixed. Preserve the original builder and audit functions byte-for-byte. Mesh-dependent state dimensions and finite-witness field sizes change naturally; they are not parameter changes.

Require Python 3.12.15 and the exact baseline scientific dependencies: PyBaMM 26.9.0.0, NumPy 2.5.3, CasADi 3.8.1, SciPy 1.18.1 and pybammsolvers 0.10.0. Assert no model-level absolute-tolerance override and inspect the expanded absolute-tolerance vector after setup: every entry 1e-8, with relative tolerance 1e-8; recheck after the only solve. Tolerances control local weighted solver state errors, not a uniform physical-unit or global error guarantee.

## Immutable mesh80 reference and complete inputs

Reference run 37954785347, source `c8e3088fd808b213992285cabfaf9b69e9528d89`, complete archive SHA256 `a35aa5d8dc2fb0c744f2f62fd4d0ea46eba553c4885aeed2a674fd2aa04b56da`, durably published at result commit `567b94ac876013e89602f99ecea0685aa73fe040`. It used one mesh80 solve at 1e-8, passed every physical audit (charge closure 0.611278 µAh), and had 19.210369 mV measured voltage RMSE. Its spatial convergence was not established.

Before new execution, verify the full committed reference archive and extract its byte-identical scalar arrays, native final state, report, effective-tolerance receipt, input manifest, upload receipt, launch ledger and completed comparison. Pin each selected member's SHA256 prospectively. In particular, arrays SHA256 `5d3b85c8d269800d1776f7b960950c3f3dbe1e19fc999362c3b5f3668438b1c3`, native state `62d85d54c06c39a9e1da658f59915f6c0edbfd91626ce19e9f13ce08c05df0ad`, report `94c0f013904ab6f7fceda1c8f1ddd91e744b850cb23f793ccbd42e6031734adb`.

Persist those exact reference members, all normalized forcing/observation/query/parameter inputs, current physical source dependencies and new protocol/runner/workflow, runtime identities and run/head metadata before solving. Selected reference bytes suffice for the new comparison; do not recursively embed the entire old archive and its nested archives. The original complete archives remain immutable in the repository. Record the verified full-archive identity and all selected member hashes, so this is explicit deduplication, not replacement or invented baseline evidence. Match normalized input hashes and all physical source hashes against the baseline; allow only the predeclared mesh metadata/field-size changes and new experiment wrapper.

## Predeclared comparisons and unchanged gates

Reconstruct each saved trajectory's 21 native endpoint observables without solving. Repeat its complete physical audit and empirical report. Compare the two trajectories using the existing unchanged `compare_meshes` rule: union of saved times over common support including its true endpoint, linear interpolation of saved scalar arrays, maximum |ΔV| <=5 mV, maximum |ΔT| <=0.1 K, and relative observed-start endpoint-charge difference <=1%, with the mesh120 charge as denominator. Both physical audits must pass and both voltage cutoffs must be verified. Report actual cutoff times, common-support endpoint and its interpolation convention. Also report differences on exact shared timestamps separately, with last shared query and both actual endpoints; this does not replace the original mesh criterion.

All original physical gates remain: maximum sampled charge error <=1e-6 Ah, relative lithium drift <=1e-6, finite state witnesses and outputs, positive electrolyte and heat capacity, original electrode bounds, and thermal-energy closure <=1%. Independently evaluate exact rational integration of the imposed piecewise-linear forcing, signed extrema and their times, sample violation count and endpoint charge error. These are sampled maxima plus the true endpoint; continuous-time extrema remain unverified. Verify forcing and capacity RHS units/signs, without fitting.

All empirical gates remain: voltage RMSE<=50 mV, maximum<=300 mV, capacity/energy errors<=5%, coverage>=95%, valid cutoff and physical audit. Record skin/bulk proxy gates 2 K RMSE and 5 K maximum with their limitations; the existing aggregate acceptance also requires both mesh120 proxy flags, without claiming independent thermal validation. The sub-25 C heat-capacity support caveat, missing prior history, finite initial skin proxy and lack of fresh independent validation remain unchanged. A numerical mesh PASS does not identify correct latent physics or erase historical high-rate 55.003 mV FAIL.

## Falsifiable outcomes and stopping

If both trajectories are physically valid, reach cutoff and meet all mesh comparison bounds, report agreement of this 80/120 mesh pair at the fixed tolerance. It is not a convergence order, asymptotic proof or universal mesh guarantee. If mesh120 violates any physical gate, stops at another event, lacks complete saved evidence or misses a numerical bound, preserve FAIL/UNVERIFIED as appropriate and report which condition failed. Empirical acceptance is a separate conjunction with numerical and physical qualification, with dataset/domain caveats retained. No threshold changes, parameter fitting, third mesh or tolerance search follow automatically.

## Resources and launch controls

Exactly one new mesh120 DFN, one free Ubuntu GitHub Actions job, singleton and run-attempt 1 guards. Maximum scientific subprocess wall time 1200 s, address space 4,000,000,000 bytes, one numerical thread. Outer job 30 minutes accommodates pinned dependency installation and durable artifact transfer; it cannot extend the scientific deadline. Verify uploaded input artifact ID/run/head/digest with the existing bounded same-endpoint mechanism before the worker starts. Always preserve complete or partial outputs.

Perform a fresh-process mesh120 build and IDAKLU setup under the actual 4 GB cap without solving, then independently review protocol, effective tolerances, resource feasibility, input identities and stopping behavior. The earlier mesh120 setup at 1e-7 took 20.357 s and 1120672 KiB; the new 1e-8 check must be measured, not assumed. The mesh80 reference worker used 79.892 s and 751880 KiB; these observations support a bounded attempt, not a guarantee of completion. Publish inert implementation, pass exact-head ordinary CI, verify no prior trigger and coordinate the single launch. Finish after independently verified evidence and final publication/CI; do not launch another experiment automatically.
