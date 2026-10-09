# K2 fixed-mesh tolerance sensitivity: charge closure passes, mesh convergence remains open

The single predeclared mesh80 diagnostic supports numerical tolerance sensitivity. Tightening IDAKLU relative and absolute tolerances from 1e-7 to 1e-8 reduced the maximum sampled charge-closure error from **1.100296 to 0.611278 µAh**, below the unchanged **1 µAh** gate. All original physical audits pass. Voltage is effectively unchanged at this mesh: the largest difference on exact shared queries is **0.003919 mV**, and measured-trace RMSE remains **19.210369 mV**.

This does not establish spatial convergence or a unique internal solver mechanism. Mesh120 was not run at the tighter tolerance. The original 1e-7 result remains a recorded physical-audit FAIL, and historical high-rate k2 remains **55.003 mV FAIL** against 50 mV. No parameters, sources, initial inventory, forcing, physical equations or acceptance thresholds changed.

## Frozen experiment and verified execution

[Protocol](stanford-k2-tolerance-protocol.md), [readiness](stanford-k2-tolerance-readiness.md), [machine-readable result](benchmarks/stanford-k2-tolerance-result.json), and [artifact manifest](benchmarks/stanford-k2-tolerance-artifact.json).

- Source commit: `c8e3088fd808b213992285cabfaf9b69e9528d89`.
- [Managed run 37954785347](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37954785347), exactly one mesh80 DFN; no retry or fine stage.
- Scientific start: 2026-10-09T15:51:45.917102+00:00. Worker 79.892455488 s, shared execution 81.213417329 s, peak RSS 751880 KiB; enforced bounds 1200 s and 4,000,000,000-byte address space.
- Before solving, input artifact 11626444919 was uploaded and its run/head/ID/digest verified. Its independent copy is 19,202,973 bytes, SHA256 `6be1d982ef524541de0710d4a41a1f91789d69d89f531c6c47f1bed85405a4f8`.
- All 47 original baseline source identities and normalized forcing/observations/grid/parameter identities stayed unchanged. The new input bundle contains 56 source files and four derived inputs. Runtime exactly matched the baseline: Python 3.12.15, PyBaMM 26.9.0.0, NumPy 2.5.3, CasADi 3.8.1, SciPy 1.18.1 and pybammsolvers 0.10.0.
- Effective IDAKLU relative tolerance and all 13,363 expanded absolute tolerances were 1e-8; no model-level override existed. These are local solver error weights, not uniform physical-unit accuracy guarantees.

## Saved-array comparison

| Observable | Original 1e-7 | Tightened 1e-8 |
| --- | ---: | ---: |
| Maximum absolute sampled charge error, µAh | 1.100295727 | 0.611277826 |
| Independent rational-oracle maximum, µAh | 1.100295698 | 0.611277824 |
| Samples beyond unchanged 1 µAh gate | 5528 | 0 |
| Measured voltage RMSE, mV | 19.210239 | 19.210369 |
| Maximum measured voltage error, mV | 47.252417 | 47.252734 |
| Observed-start endpoint charge, Ah | 4.885410201 | 4.885410148 |
| True voltage-cutoff time, s | 70344.806549 | 70344.815738 |
| Physical audit | FAIL, charge closure | PASS |

The charge maximum fell about 44.44%, not tenfold. The new signed error ranges from −0.087618 µAh at 5200 s to +0.611278 µAh at 25103 s; its endpoint error is +0.258589 µAh. This covers all prescribed saved samples and the true endpoint, not unobserved continuous-time extrema. The source integral agrees with the exact rational integral to 4.53e-14 Ah; the compiled current matches every source/query point, and the compiled capacity derivative matches I/3600 to 1.36e-20 Ah/s. Source quadrature, sign, units and endpoint convention remain excluded as explanations for the sampled discrepancy at this precision.

There are 70,354 exact shared query times from 0 to 70344 s. Across these, maximum |ΔV| is 3.918555662e-6 V and |ΔT| is 3.395277537e-5 K. The earlier actual cutoff is 70344.806549 s, beyond the final shared sample. The cutoff shifts +0.009188138 s; relative endpoint-charge difference is 1.097811553e-8, using the tightened endpoint denominator. These satisfy the prospectively retained 5 mV, 0.1 K and 1% descriptive stability bounds. No resampling or endpoint extrapolation is used in these differences.

Other physical checks pass: relative lithium drift 2.120995579e-14, finite spatial witnesses, electrode concentration bounds, positive electrolyte and heat capacity, and thermal-energy residual/generated heat 4.379245545e-7. At this mesh the original electrical gates pass: 19.210369 mV RMSE, 47.252734 mV maximum error, 0.0356669% capacity error, 0.0958819% energy error, 99.9643279% coverage and a valid 2.5 V cutoff. This is one previously viewed low-rate record, not independent holdout validation.

The skin/bulk temperature proxy gives 0.667022 K RMSE and 0.977238 K maximum error. It is not independent thermal validation. Skin temperature reaches 24.1916 C and the predicted bulk starts at 24.3455 C, below the 25 C lower support of the cited heat-capacity measurements; the domain caveat remains. Missing prior history and initial-temperature assumptions are unchanged.

## Interpretation and next discriminating step

The result supports that the original small charge-closure failure was sensitive to numerical tolerances, while the low-rate voltage trajectory is stable under this particular tolerance change. It does not distinguish adaptive integration error from output interpolation, establish an error order, promise monotonic improvement at other tolerances, or explain the much larger high-rate empirical voltage failure. No physically meaningful parameter was calibrated.

The next necessary numerical question is spatial convergence at the now-tested 1e-8 tolerance: one separately reviewed mesh120 run with the same source, forcing, physics, initial state and unchanged gates, compared against this saved mesh80 trajectory. That would require its own bounded protocol and resource review. No such run was launched as part of this experiment.

## Durable reproduction

The complete 27,644,650-byte GitHub evidence ZIP is stored byte-for-byte in four ordered repository parts. Concatenation SHA256 is `a35aa5d8dc2fb0c744f2f62fd4d0ea46eba553c4885aeed2a674fd2aa04b56da`. It includes all persisted inputs, runtime/source identities, upload receipt, one-stage ledger, effective-tolerance receipt, native final state, scalar arrays and reports. It also preserves the complete baseline archive within the input dependency snapshot.

Run `python scripts/verify_stanford_k2_tolerance_evidence.py` to verify every part and the full archive, bind the pre-solve upload receipt, regenerate physical/empirical/charge comparisons and check all 21 native final-state observables without a new battery solve or source download. Both the CI-produced and committed reports must reproduce with strict schema/verdict identity and the existing finite floating-point reproduction allowance.

Independent result review reproduced the source/oracle and same-query metrics and accepted the bounded conclusions. All 56 persisted source Git blob hashes were checked against the connected GitHub execution tree, rather than the recovery checkout's stale local history. The complete local suite passed 684 tests with 7 skips and 6 existing warnings in 94.26 s; lint and formatting passed across 143 Python files. The one-stage ledger retains its original pre-comparison status string; the separate comparison report and terminal workflow receipt establish subsequent completion.

A subsequent separately reviewed [mesh120 comparison](stanford-k2-mesh120-findings.md) at the same 1e-8 tolerances now establishes agreement of the 80/120 pair within the original gates. This later evidence does not rewrite the scope or historical verdict of the one-mesh tolerance diagnostic above.
