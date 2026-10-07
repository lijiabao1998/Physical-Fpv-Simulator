# Numerical refinement addendum v1 (2026-10-07)

The original predeclared protocol is preserved byte-for-byte. The initial complete report is retained in `docs/benchmarks/initial-mesh20.json` and `.md`.

The first mesh-20 to mesh-40 comparison failed the unchanged 5 mV numerical tolerance at 1 C (6.61 mV) and 1.5 C (8.11 mV). Solver-tolerance refinement passed. This diagnoses discretization sensitivity, not a reason to loosen an experimental error threshold.

For the next bounded run, promote the working grid to 40 points and audit it against 80. Keep all electrochemical parameters, initial concentrations, empirical metrics and empirical acceptance targets unchanged. Run a stricter 1e-8 solver tolerance separately. This numerical procedure was refined after seeing the first results; it is not represented as the original predeclared mesh protocol. No changes are fitted to the measured voltage/capacity curves, and no failing initial result is removed.

Maximum mesh is 80, CPU only, single solver thread. If the refined model still fails a numerical target, retain the failure. Do not silently choose a coarser grid based on a better match to experimental data. Temperature remains explicitly unvalidated.
