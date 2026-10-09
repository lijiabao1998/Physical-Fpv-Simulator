# Current-source replay: two numerical passes, k1 empirical failure retained

Both reviewed mesh120 jobs completed under their original per-case resource
limits. This closes the implementation-specific missing numerical evidence for
these two cases. It does not repair empirical disagreement or validate the whole
battery model.

Source commit: 744794b02d44bcbfc702ad8e5c403782128d11b0.
[Run 37887926852](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37887926852)
was attempt1 and executed exactly two sequential solves, with authenticated
historical mesh80 references. No k2 solve, parameter fitting or new dataset was
included. Standard Chen PR CI remained separate.

| Case | Supervisor time | Maximum ΔV | Maximum ΔT | Capacity difference | Numerical result |
|---|---:|---:|---:|---:|---|
| Stanford k1 | 850.067 s | 3.234943 mV | 0.017554 K | 0.0034589% | PASS |
| Representative thermal | 690.046 s | 3.320930 mV | 0.018018 K | 0.0034460% | PASS |

Frozen numerical limits remain5mV,0.1K and1%, plus original physical and cutoff
audits. Both worker exit codes are0. Total scientific supervisor time was
1540.113s against the combined2400s ceiling. K1 recorded peak process RSS was
2148436KiB; thermal did not separately record RSS. Both workers had a
4,000,000,000-byte address-space limit, also imposed before imports by the
outer shell; this is not a claim about aggregate runner RAM.

## Scientific interpretation

K1 voltage RMSE is **191.473522mV**, failing the unchanged50mV gate. Its other
recorded electrical gates pass. A successful workflow or spatial check cannot
turn this empirical failure into acceptance. The newly generated mesh120 curve
is byte-identical to the historical fine curve (CSV SHA256
84e181cd1c04180be660791abb42790862d35d4b5f2bd99b38fa5332b03d326d).
Thus this run supplies direct new-source reproduction evidence for that one case.

Thermal's current-source spatial metrics pass with only tiny differences from
the historical comparison; no measured-temperature empirical claim is added.
One representative spatial pass does not establish the remaining cohort's
convergence, and the prior ORegan30/36 and Chen6/12 empirical failures remain.

The historical k2 result remains55.003054mV FAIL at its original implementation.
This task does not claim a new k2 voltage result. Its joint inventory/OCV causal
question still requires independent external constraints; permission is not the
missing ingredient.

## Verification and durable evidence

Before each solve, the job successfully uploaded all authenticated inputs:
42 staged files for k1 and34 for thermal. Each downloaded input ZIP was checked
against its Actions digest and every staged member against the recorded manifest.
The workflow source, full package imports, references, raw k1 inputs and prior
receipts are included. Execution source hashes match the manifest and committed
calculation inputs.

After execution, independent saved-array arithmetic reproduced k1 voltage RMSE,
both cases' spatial voltage/temperature maxima, and the thermal capacity ratio.
Original launch, external-exit and supervisor receipts are retained verbatim.
The original cache files were not overwritten; separate new-source receipts
supply the current cache defaults. Genuine-receipt tests use the recorded hashes
without rebasing them. Historical receipts remain rejected for current code.

| Case | Input artifact | Output artifact |
|---|---:|---:|
| k1 | 11597286705 | 11596639695 |
| thermal | 11597616222 | 11598092120 |

Full input/output ZIPs are also retained in the owner's Library under these names,
so preservation is not limited to the90-day Actions artifact retention:
- current-source-k1-inputs-37887926852.zip
- current-source-k1-evidence-37887926852.zip
- current-source-thermal-inputs-37887926852.zip
- current-source-thermal-evidence-37887926852.zip

The following receipts contain exact ZIP sizes and SHA256 values, per-member
hashes, input manifests, code contracts, references, metrics and terminal records:
- [Current-source k1 receipt](benchmarks/stanford-k1-current-source-20261009-evidence.json)
- [Current-source thermal receipt](benchmarks/thermal-current-source-20261009-evidence.json)
- [Frozen replay protocol](current-source-replay-protocol.md)

Current-source cache reuse is now backed by these actual runs, not by changing
historical hashes to fit new code. The fail-closed PR cache-miss controls remain:
a later calculation change again requires separately reviewed bounded execution.
No automatic retry or further experiment follows this task.

## Sources and attribution

Stanford measurements: Edoardo Catenaro and Simona Onori,
[dataset DOI10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
CC BY4.0. Parameter measurements: Kieran O'Regan, Ferran Brosa-Planella,
W. Dhammika Widanage and Emma Kendrick,
[DOI10.5281/zenodo.5171874](https://zenodo.org/records/5171874), CC BY4.0.
The thermal setup's prior provenance is the
[TEC v1.0 archive](https://zenodo.org/records/4864437), BSD3-Clause;
full notices and transformation descriptions are retained in the new receipts.
These derived model comparisons are not new measurements or source endorsement.
