# k2 recovery: numerical convergence passes; empirical voltage RMSE fails

The explicitly new October 9 recovery completed both grids in **911.043 seconds**
under the shared 1200-second budget, with external exit code 0. This means the
execution completed. **Scientific empirical acceptance remains FAIL.**

Source: [run 37871885149](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37871885149)
at commit `50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84`, October 9 01:53:38–02:08:49 UTC.
The original October 8 grid120 attempt still has no terminal receipt and remains
unknown. Its historical coarse result is not relabeled as the new fine result.

| Result | Grid80 | Grid120 | Frozen target |
|---|---:|---:|---:|
| Voltage RMSE | 54.508998 mV | **55.003054 mV: FAIL** | ≤50 mV |
| Maximum absolute voltage error | 262.607340 mV | 262.800221 mV | ≤300 mV |
| Capacity relative error | 2.984905% | 2.988243% | ≤5% |
| Delivered energy relative error | 1.070196% | 1.056599% | ≤5% |
| Observed-time coverage | 97.015105% | 97.011767% | ≥95% |
| Temperature-proxy RMSE | 1.892276 K | 1.887452 K | ≤2 K, descriptive |
| Temperature-proxy maximum error | 4.919070 K | 4.912810 K | ≤5 K, descriptive |

Both grids reached the correct 2.5-V event and passed native physical audits.
The fine-grid cutoff is 3333.132326 s versus the measured 3435.771300 s, **102.638974 s early**.
The full observed charge and energy denominators are retained; no tail was removed.
The voltage RMSE is the only failed electrical gate in this selected case.

## Spatial check

80→120 passes: maximum voltage difference **3.362045 mV** (target 5 mV),
maximum temperature difference **0.018187 K** (target 0.1 K), and cutoff-capacity
relative difference **0.003440%** (target 1%). Voltage and temperature maxima occur
at 141.0007 s and 913.0012 s on the shared domain. True event endpoints are retained.
This reduces the numerical uncertainty for this case; it does not erase the
55.003054-mV empirical failure or establish a unique physical cause.

Grid80 took 156.319 s and grid120 743.962 s. Fine-grid peak RSS was 2,162,532 KiB.
Both solver processes enforced 4,000,000,000-byte address-space limits. The shared
elapsed time includes supervision and postprocessing. No extension or retry was used.

## Provenance and limits

Exactly one original `NMC_k2_1C_25degC.xlsx` was reacquired: 1,802,458 bytes,
SHA256 `20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086`.
Edoardo Catenaro and Simona Onori, [DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). All three stopped k6 downloads remain stopped.

The frozen ORegan2022/DFN parameters, measured current knots, initialization,
tolerances, physical audits and empirical thresholds were unchanged. No fitting,
OCV alignment or smoothing occurred. k2 was chosen after observing its trace;
this remains exploratory, not blinded independent validation or cohort generalization.

Temperature compares predicted volume average with measured central skin.
The h=15 cooling coefficient is an ORegan prior, not measured for this Stanford
fixture. Initial uniform temperature is assumed from the final rest skin reading;
it lies 0.595432 K below the released heat-capacity measurement domain. The two
descriptive temperature gates pass, but **independent thermal validation is not established**.
No FPV, aging, abuse, safety or new-material performance claim follows.
Existing k1 191.474-mV, Chen 6/12 and ORegan 30/36 empirical failures remain.

## Durable evidence and no-solve verification

- [Summary, source fingerprints and terminal receipts](benchmarks/stanford-k2-recovery-summary.json)
- [Original recovery artifact ZIP](benchmarks/stanford-k2-recovery-evidence.zip), SHA256
  `2fbea2b607ad1e6b149f1033af8a2123e86a39f18319b4c8b5f18ee5b040795d`
- ZIP contains both native-array snapshots, curves, residuals, forcing, solver logs,
  complete reports, attribution, acquisition/preflight and external exit receipts.
- Input artifact 11590866548 SHA256
  `6c992750395a4e8d4e320b856ec3a944d66b5107051413a6d69e835a10af2b1a`
  retains the original workbook in the source run through January 7, 2027.

Run `python scripts/verify_stanford_k2_recovery.py` in the pinned environment to
check artifact integrity, calculation fingerprints, native snapshot hashes,
terminal receipts and recompute spatial comparison **without a new solve**.
This is evidence verification, not a new experimental validation.
