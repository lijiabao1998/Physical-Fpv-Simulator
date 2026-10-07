# Thermal numerical status and bounded diagnostics

The frozen ORegan protocol requires grid40→80 and tolerance1e-7→1e-8 checks. A36-case mesh40 empirical run without those checks is explicitly NOT a converged/qualified model. `--skip-numerics` writes `not_run` for those stages; it cannot be used as evidence that the numerical targets passed.

Initial80-point diagnosis was constrained by runtime, not a demonstrated scientific impossibility. A120-second IDAKLU diagnostic did not finish; its sampled native stack was in integration. Ahead-of-time C compilation trials (official PyBaMM code generation, including default and reduced compiler optimization) also exceeded their short diagnostic budgets. Those experiments do not justify relaxing the numerical targets or altering physical parameters.

A separate representative check is implemented in `scripts/verify_thermal_grid.py`. It uses the unchanged1C /25°C /initial297.75K /h15 case with grid80, default IDAKLU and solver statistics. The supervising process has an explicit maximum600-second budget and persists progress, input settings, solver logs and final status; the child has a4GB address-space ceiling to protect the shared executor. A completed fine-grid solve still needs comparison with the matching40-point result. A timeout is reported as budget exhaustion, not proof of divergence.

Run from an installed checkout:

```sh
python scripts/verify_thermal_grid.py --timeout 600
```

No paid service, new credential, altered experimental threshold, or high-current hardware experiment is involved. Longer numerical qualification remains an open gate until actual results establish convergence. The candidate stays a research draft.

## Completed representative result

The600-second supervised run finished in187.46 solver seconds (190.01 wall seconds including supervision). It reached the2.5V event with valid actual-node/surface concentrations, lithium and heat-balance audits. Solver statistics:21719 steps,49308 residual evaluations,1624 Jacobian evaluations and1221 error-test failures.

Comparison on the full common time domain[0,3333.3464]s failed the unchanged numerical targets:14.331mV voltage maximum difference (at340s),0.207438K temperature difference (at970s), and0.004792% capacity difference. The cutoff times differ by0.1598s. The last10% of the common interval still has6.422mV voltage difference; it is retained. These failures are genuine mesh sensitivity, not endpoint extrapolation.

A controlled80→120 representative refinement is the next numerical stage, with unchanged physical parameters/state/tolerances and a separately declared budget. No full-cohort numerical pass is claimed.
