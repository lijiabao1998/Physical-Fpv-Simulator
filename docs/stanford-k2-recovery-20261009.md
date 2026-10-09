# Explicit new k2 recovery window, October 9, 2026

The original October 8 grid120 execution has no surviving terminal receipt and
remains **unknown**. Its previously reported grid80 RMSE of 54.50899787 mV is a
historical coarse result, not a reconstructed curve or a verified fine-grid
result. Neither its arrays nor the prepared recovery handoff could be recovered
from the current cloud runtime, available task records or relevant Library files.

The user explicitly authorized recovery retries. This is a **new reproduction**
of both meshes, not reuse of missing grid80 arrays or continuation of the original
execution. Numerical source files, protocol and fixed input contract remain
unchanged from commit `0eaba04e63423e1f60bf8fbfc042840c4676684d`.

## Bounded acquisition and execution

Because the old raw source is also unavailable, acquire only the original k2
1C/25C workbook from the exact official URL in the frozen manifest. Require
1,802,458 bytes and SHA256
`20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086`.
Source: Edoardo Catenaro and Simona Onori, DOI 10.17632/kxsbr4x3j2.2, CC BY 4.0.
No retry or alternate source is included. Acquisition has a 90-second total
deadline and persists its started receipt before network access. All three stopped k6/5C downloads remain
stopped. This addendum changes only availability/recovery handling; the original
scientific protocol and its hashes are preserved.

Use standard free GitHub-hosted `ubuntu-latest` CPU on this public repository.
Repository-wide recovery concurrency is one, without cancelling an active run.
The one publication-triggered run has no schedule or manual-dispatch trigger,
and rejects manual reruns (`github.run_attempt` must equal 1). Concurrency alone
only serializes runs; do not edit/re-publish this workflow to create a second window.
Before publication, verify there is no active recovery run. Do not rerun the
workflow after a timeout merely to obtain a pass.

After pinned dependencies, software tests (including small pre-existing model
integration tests, separate from the two scientific k2 solves), checksum
acquisition, the real-data k2 test and static preflight,
invoke the unchanged runner with a **shared 1200-second budget for both meshes**,
hard 4,000,000,000-byte address-space limits and one-thread numerical libraries.
An external process-group timeout sends SIGTERM at 1200 seconds and SIGKILL after
five seconds solely for shutdown, not extra calculation time. A 30-minute job
cap includes setup and evidence upload; it does not extend the solve budget.
At most two new solves occur. Preserve partial results on failure; no silent
budget increase, mesh increase, fitting or change to the 50-mV RMSE threshold.

Persist the frozen source identity, acquisition receipt and original raw workbook
before the solve; always upload full/partial numerical outputs plus the external
exit receipt after it. GitHub commit/run IDs identify this new window. A missing
terminal receipt is still unknown, never inferred successful or budget-exhausted.

## Interpretation

All original electrical, physical and spatial gates remain unchanged. Software
CI success and solver completion do not imply scientific acceptance. Read the
empirical and numerical booleans separately. No independent thermal validation,
whole-cohort validation, GUI, deployment, paid runner or calibration is included.

Stop after this one new two-grid result or an explicit stopping condition.
