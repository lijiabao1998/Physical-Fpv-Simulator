# Fixed-mesh tolerance diagnostic readiness

This is preparation for the separate [frozen protocol](stanford-k2-tolerance-protocol.md). It does not replace the [published coarse failure](stanford-k2-low-rate-model-findings.md). No additional scientific solve was performed during preparation.

## Controlled implementation

The original model builder, original execution runner, input records, physical audits and historical verifier remain byte-identical. A separate runner reuses the original built mesh80 model and changes only relative and absolute integration tolerances from 1e-7 to 1e-8 before setup. It rejects model-level absolute-tolerance overrides, checks the effective 13,363-entry tolerance vector before execution and again afterward, and records the applied values. All baseline source hashes, derived forcing/observation/grid/parameter hashes and the original configuration are checked before preparing inputs. The managed run must use exactly the baseline Python and scientific dependency versions.

The comparison verifies the original archive and its failed verdict, independently checks the new saved arrays and native endpoint state, repeats the unchanged physical and empirical audits, and evaluates charge closure using the independent rational source integral. Voltage and temperature differences use exact shared timestamps; true endpoints and the last shared sample are reported separately. This is a tolerance-sensitivity comparison, with spatial convergence still unavailable.

## Resource feasibility without a solve

A fresh process with `RLIMIT_AS=4,000,000,000` bytes built mesh80 and completed IDAKLU setup in 7.606959470998845 seconds. Peak RSS was 649856 KiB. The effective absolute-tolerance vector contained 13363 entries, all exactly 1e-8; relative tolerance was 1e-8. No model-level override existed. Zero battery solves ran. Peak RSS is diagnostic information, not a replacement for the address-space limit.

The previous same-mesh 1e-7 scientific worker used 67.818546947 seconds and 650700 KiB peak RSS. This supports a bounded attempt, not a promise that tighter tolerance finishes. The scientific worker retains its independent 1200-second timer and 4 GB limit; the parent enforces the same deadline. There is only one permitted stage, even on success. The workflow is initially inert outside `.github/workflows`; publication and exact-head ordinary CI precede separate launch coordination.

## Review and stopping

Independent protocol review accepted the narrow falsifiable question and required effective-tolerance inspection, exact baseline runtime equality, exact shared queries and distinct closure/stability/physical/empirical verdicts. These checks are implemented. Final implementation review and tests are recorded with the publication receipt. The experiment stops after one attempt without a fine mesh or second tolerance. Any failure or incomplete result remains visible and is preserved.

Final independent implementation review accepted the package after correction of endpoint-charge normalization, offline upload-receipt binding, invalid-trajectory hypothesis labeling and signed-maximum reporting. All 47 archived baseline source hashes remained unchanged. The final local suite passed 682 tests with 7 skips and 6 existing warnings in 59.44 s; lint and formatting passed across 141 Python files. The focused diagnostic suite passed 8 tests. Ordinary remote CI remains the next publication check.
