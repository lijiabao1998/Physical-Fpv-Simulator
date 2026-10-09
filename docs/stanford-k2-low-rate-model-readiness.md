# Low-rate experimental driver: implementation readiness

This package contains no new battery trajectory. It implements the
[frozen k2 protocol](stanford-k2-low-rate-model-protocol.md) and an
[inert workflow template](experiments/stanford-k2-low-rate-model.workflow.yml).
The template lives outside `.github/workflows`, so publishing it cannot launch
the experiment. Historical k1/k2 empirical failures remain unchanged.

## Independent review and software checks

Independent review accepted publication and judged one resource-bounded execution
technically defensible. It found and resolved two issues before launch:

1. Mesh endpoint capacity normalization must exclude the assumed initial-current
   interval, consistently with the empirical observed-start capacity definition.
2. Saved-result verification must independently verify the frozen time grid and
   native final state, rather than trusting a saved success receipt. The driver
   now persists and hashes that state; verification rebuilds without solving and
   reevaluates all 21 final scalar observables.

The reviewer independently confirmed all 21 endpoint reevaluations and rejection
of a 1 mV scalar alteration. Tests cover the unchanged ordinary current guard,
both mesh constructions/equations/parameters, NaN/Inf witnesses, analytical toy
ODE storage/event behavior, full endpoint capacity/energy, cutoff-unavailable
handling, threshold-edge mesh normalization, upload identity, shared deadlines,
coarse-failure stopping, and tampered saved metrics/hashes. Synthetic scalar
pipeline fixtures are explicitly analytical software fixtures, not battery solves.

The full local suite passed 653 tests with 7 environment/data-dependent skips and
6 upstream deprecation warnings. Small analytical toy ODE tests are included;
no experimental battery integration was run for this package. Lint passed.
Actual dependency/runtime versions are recorded for preparation, execution and
verification. Local checks used Python 3.12.14; the historical high-rate archive
records Python 3.12.15. This patch-level runtime difference is disclosed, not
treated as an identical execution environment.

## Non-solving resource check

Under a fresh one-thread Python process with a 4,000,000,000-byte `RLIMIT_AS`,
the independent reviewer built mesh120 and called IDAKLU `set_up` without
integrating. The process exited successfully in 20.357113392 seconds with peak
RSS 1,120,672 KiB. It contained 29,643 state variables and 21 scalar outputs.
A separate build-only check completed in 3.494248836 seconds, peak 303,160 KiB.

The exact check was:

```python
import resource, time
resource.setrlimit(resource.RLIMIT_AS, (4_000_000_000, 4_000_000_000))
started = time.monotonic()
from pathlib import Path
from physical_fpv.experimental_low_rate import build, prepare
sim, outputs, metadata = build(prepare(Path.cwd()), 120)
sim.solver.set_up(sim.built_model, inputs={})
print(time.monotonic() - started,
      resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
```

It used `PYTHONDONTWRITEBYTECODE=1`, `PYBAMM_DISABLE_TELEMETRY=true`, and
`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=NUMEXPR_NUM_THREADS=1`.
Versions: Python 3.12.14, PyBaMM 26.9.0.0, pybammsolvers 0.10.0, NumPy 2.5.3,
SciPy 1.18.1 and CasADi 3.8.1. The check preceded the grid/final-state/mesh-Q
verification fixes, which do not change `build()` or the model/setup equations.

This establishes construction/setup feasibility only. Full factorization memory
and integration time remain unproven. The prospective execution is limited to
two sequential DFNs under one shared 1200-second deadline and a 4 GB worker cap.
A resource failure remains UNVERIFIED, preserves available evidence, and cannot
trigger a retry, budget extension or parameter adjustment. A workflow exit of
zero never substitutes for numerical or empirical qualification.

## First managed preflight outcome

The first managed run uploaded its prepared inputs, then stopped on HTTP404
from the immediate metadata verification call. Both scientific steps were
skipped. The [protocol amendment](stanford-k2-low-rate-model-protocol.md#preflight-recovery-amendment-zero-scientific-work-in-the-first-attempt)
describes a bounded same-endpoint visibility check and a separately identified
replacement, without changing the scientific budget or input-persistence gate.
The original workflow remains immutable and is not rerun.
