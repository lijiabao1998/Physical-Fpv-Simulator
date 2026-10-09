# K2 low-rate experiment: coarse charge-closure failure

The frozen-parameter mesh80 run produced a voltage RMSE of **19.210 mV**, but it
**failed the charge-closure audit**. The unchanged limit was 1.000000 microAh;
the maximum error was 1.100296 microAh. The supervisor stopped as declared and
never started mesh120. There is no mesh-converged low-rate qualification and no
replacement for the historical high-rate 55.003 mV FAIL.

[Managed run 37948404436](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37948404436)
used source `208d34882acb79b32b48e578575760580675c868`. Its input upload was verified
before integration. One battery DFN completed; the worker took 67.819 seconds and
peaked at 650,700 KiB RSS. Shared execution took 69.482 seconds within the declared
1200-second / 4 GB bounds. Scientific exit code 2 records the failed audit; it is not
an unhandled software crash. No retry or additional solve followed.

## Reproduced coarse observations, not an overall PASS

| Quantity | Saved/reproduced value |
| --- | ---: |
| Voltage RMSE | 19.210 mV |
| Maximum absolute voltage error | 47.252 mV |
| Observed-time coverage | 99.9643% |
| Minimum-voltage cutoff time | 70,344.806549 s |
| Capacity relative error | 0.035666% |
| Delivered-energy relative error | 0.095895% |
| Skin/bulk temperature proxy RMSE / maximum | 0.667 / 0.977 K |
| Lithium inventory relative drift | 2.121e-14 |
| Thermal energy-balance relative residual | 1.0501e-5 |
| Maximum source/model charge discrepancy | 1.100296e-6 Ah, FAIL |

All spatial finiteness witnesses, electrode bounds, positive electrolyte and
thermal-energy checks passed. The heat-capacity measurement domain is still
exceeded below 25°C by both measured skin and modeled bulk temperatures. The
skin/bulk comparison is a proxy, not independent thermal validation.

Independent offline verification reconstructed the exact archive, checked all
47 source files and 5 derived inputs, rechecked all 70,355 output times against
the frozen grid, rebuilt the equations without solving and reevaluated all 21
final-state observables. Empirical and physical metrics reproduced. Actual
execution used Python 3.12.15; local verification used Python 3.12.14, with the
same recorded pinned scientific dependency versions.

## Where the charge-closure discrepancy originates

The maximum occurs at 61,597 seconds, inside the trajectory. Endpoint error is
0.950345 microAh, which is below the gate. Restricting the audit to the cutoff
would hide the failed interior check. There are 5,528 failing sampled times,
between the first breach at 55,834 s and the last at 66,225 s; these bounds do not
imply one continuously failing interval.

An independent exact-rational integral of the source's stored binary-float
piecewise-linear law separates the possible numerical contributions:

| Comparison with exact source integral | Maximum difference |
| --- | ---: |
| Production analytic current integrator | 4.530e-14 Ah |
| Trapezoidal integration on exported output times | 7.437e-11 Ah |
| Saved solver capacity state | 1.100296e-6 Ah |

The compiled model current also matches the prescribed current exactly at all
137,313 source-knot/output queries. The compiled capacity-state RHS matches
I/3600 to within 1.355e-20 Ah/s at those same queries, confirming its
sign and units. Initial solver capacity is zero. The native
final state reproduces the exported endpoint capacity, so this is not solely an
exported-cutoff interpolation problem. The same discrepancy persists when both
capacity conventions consistently exclude the assumed first second. An
independent observed-start check gives Q_solver(1 s) − Q_exact(1 s) =
−6.191e-13 Ah; even re-anchoring each curve at its own first-observed capacity
cannot remove the failure.

These checks constrain the discrepancy to numerical evolution/interpolation of
the solver's capacity state at the configured tolerance. Source quadrature,
current sign, source serialization and the initial/cutoff accounting convention
do not account for its size. They do not uniquely identify an IDAKLU mechanism
or establish an internal physical-model defect. The maximum discrepancy is
2.252e-7 relative to endpoint charge. That small size does not authorize relaxing
the frozen audit threshold, replacing the saved state with an analytic integral,
or declaring the voltage trajectory converged.

## Exploratory rate comparison: unqualified mesh80

At the nine predeclared discharged-Ah queries, use E = model − measurement and
G = low-rate voltage − high-rate voltage. The algebraic identity
G_model − G_observed = E_low − E_high reproduces. The low-rate trajectory is the
failed coarse run; the high-rate curve is the pinned historical mesh120 run.

| Conditional discharged Ah | E_low (mV) | E_high (mV) | G_model − G_observed (mV) |
| ---: | ---: | ---: | ---: |
| 0.5 | +10.728 | +56.876 | -46.149 |
| 1.0 | -0.512 | +45.699 | -46.211 |
| 1.5 | +0.781 | +62.926 | -62.145 |
| 2.0 | -11.212 | +55.819 | -67.031 |
| 2.5 | -19.965 | +67.786 | -87.752 |
| 3.0 | -17.981 | +58.662 | -76.643 |
| 3.5 | -18.898 | +35.654 | -54.553 |
| 4.0 | -31.398 | +21.938 | -53.335 |
| 4.5 | +42.872 | -29.006 | +71.878 |

The modeled rate gap is smaller than the observed gap at 0.5–4 Ah. The gap
error changes sign at 4.5 Ah, where the model overestimates the observed gap by
71.878 mV; both voltage gaps remain positive. This is a conditional development
observation, with no new rate-response
PASS threshold. Equal discharged Ah does not establish equal absolute SOC,
electrode inventory, prior history or temperature. The records have different
thermal paths and an unobserved history gap. Neither the lower coarse RMSE nor
the gap vector identifies contact resistance, kinetics, diffusion or initial
inventory as the unique empirical cause.

## Durable evidence and reproduction

The complete 13,856,564-byte GitHub artifact is preserved as two numbered binary
parts to keep individual transfers bounded. The
[artifact manifest](benchmarks/stanford-k2-low-rate-model-artifact.json) records
part sizes/hashes and the full byte-identical ZIP SHA-256
`f841d0016f9787186f129c5c563226696fd340ab5c6212fcc8c2eb59ae5546cb`.
It includes the complete frozen inputs, scalar arrays, native final state,
worker report, upload receipt and launch ledger. The
[verified result](benchmarks/stanford-k2-low-rate-model-result.json) preserves all
metrics and qualification flags. No arrays or historical results were overwritten.

From this result's source revision with the pinned dependencies installed:

```sh
python scripts/verify_stanford_k2_low_rate_evidence.py --out results/low-rate-verification.json
```

Verification never downloads or runs a battery solve; tests explicitly forbid
those calls. It fails if source identities, archive bytes, metrics or verdicts
change. The original failed preflight remains separately preserved.

## Next numerical question, not an automatic execution

A new reviewed protocol could test a tenfold tighter solver tolerance with the
same source, model, physical parameters and audit limits. Its falsifiable targets
would be reduced capacity-state closure error, agreement with this saved coarse
voltage curve and, only after a passing coarse audit, an independently qualified
fine mesh. Tolerance refinement is numerical verification, not fitting physical
parameters to the voltage gate. No such solve is launched by this report.
