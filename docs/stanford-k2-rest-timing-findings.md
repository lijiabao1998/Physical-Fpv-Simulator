# Descriptive cutoff-to-rest timing in two saved k2 records

Both records continue changing after their first recorded zero-current sample. Between the fixed 1800 and 3600 second queries, low-rate voltage rises another 52.840905 mV and high-rate voltage another 17.646063 mV. These observations make the choice of a finite-rest voltage anchor consequential. They do not identify equilibrium OCV, SOC, resistance, or a unique polarization mechanism.

This is a modest descriptive characterization aid. The endpoint changes were partly known from earlier inventory and cooling audits; the added deliverable makes the interruption bracket and fixed-window partition reproducible. It is not new experimental validation.

## Fixed query table

Recovery below is measured from each record's first actual rest sample, not from a fabricated t=0 voltage. Time is nominal commanded rest time; it does not establish the physical switching instant or acquisition latency. Original Date_Time values remain timezone-unspecified source timestamps, not UTC.

| Nominal rest time, s | Low-rate further recovery, mV | High-rate further recovery, mV | Low skin, °C | High skin, °C |
|---:|---:|---:|---:|---:|
| 2 | 2.638039 | 18.903750 | 24.660725 | 32.349747 |
| 10 | 13.328243 | 76.703325 | 24.713497 | 32.361703 |
| 60 | 42.275282 | 161.895652 | 24.655435 | 31.545294 |
| 600 | 123.953110 | 227.143760 | 24.470219 | 26.311823 |
| 1800 | 192.368984 | 252.470978 | 24.409888 | 24.693995 |
| 3600 | 245.209889 | 270.117041 | 24.415924 | 24.373232 |

Every query uses adjacent actual source samples with no extrapolation. The JSON/CSV preserve both Excel-row IDs, exact source times and interpolation weights. In particular, the 3600 s values differ slightly from the actual final samples at 3600.0013 s (low) and 3600.001 s (high); those final samples remain separately recorded.

## Actual sample boundaries

| Observation | Low-rate record | High-rate record |
|---|---:|---:|
| Last loaded voltage, V |2.499997616|2.499992371|
| Last loaded current, A |−0.250020385|−5.000402451|
| First rest voltage, V |2.515622854|2.749690771|
| First nominal rest sample, s |1.0006|0.9997|
| Last-load/first-rest Test_Time sample bracket, s |1.135296|1.139968|
| Observed first recovery, mV |15.625238|249.698400|
| Actual final rest voltage, V |2.760849237|3.019788742|
| Further first-to-last recovery, mV |245.226383|270.097971|

Each rest has 3601 samples, all with recorded external current zero. The sample brackets describe recorded timestamps; they do not bound the true switching time or filter latency. No instantaneous ohmic drop or resistance is inferred by dividing these voltage changes by current.

## Limits and next missing measurements

The low record and high record finish at different passed charge, temperature and unknown prior inventory. Their 45.4967575-hour inter-record gap remains unobserved; no continuous state replay or matched-SOC comparison is permitted. High-rate skin temperature changes by about 8°C during rest; low-rate skin also varies. Neither skin temperature nor the nominal chamber label measures the complete internal/ambient thermal state. No temperature correction, relaxation fit, OCV inversion or parameter adjustment was applied.

Finite rest is not equilibrium, and there is no quantified voltage/current calibration or slow-relaxation uncertainty. Consequently this table supplies no new empirical acceptance threshold. The original high-rate 55.003054 mV RMSE still fails the 50 mV gate; low-rate qualification and the separate Chen empirical failures are unchanged.

The concrete missing causal data are synchronized, higher-resolution current-interruption or pulse-relaxation measurements with controlled inventory and characterized temperature, timing and instrument uncertainty. A rested OCV-versus-passed-charge reference would constrain finite-rest interpretation. Separating inventory error from transferred OCP laws additionally requires an independent electrode-capacity/inventory or electrode-resolved potential anchor. No additional solve is launched from this table.

## Frozen sources and reproduction

The protocol was hashed before the single extraction/analysis pass: 3025ddf13b794034cb7cd8a7e73cf5ae7a3b461b9fd4be65b74f453b9593beca. The pass used 3.533621 s and peak 73464 KiB within 60 s / 512 MiB, with zero downloads, fits or model solves. Source workbooks and normalized records retain their original hashes, authors and CC-BY 4.0 attribution in the machine-readable receipts.

- [Frozen protocol](benchmarks/stanford-k2-rest-timing-protocol.json)
- [Complete result and source brackets](benchmarks/stanford-k2-rest-timing-result.json)
- [CSV table](benchmarks/stanford-k2-rest-timing-result.csv)
- [Low normalized source rows](benchmarks/stanford-k2-low-rate-rest-records.csv.gz) and [source receipt](benchmarks/stanford-k2-low-rate-rest-source.json)
- [Existing inventory/rest limits](stanford-k2-rest-inventory-findings.md)

Reproduce from committed normalized inputs with `OPENBLAS_NUM_THREADS=1 python scripts/characterize_stanford_k2_rest_timing.py --out results/rest-timing.json`. Optional `--extract-low` accepts only the already available checksum-identical original workbook; it never downloads one. The command enforces the frozen wall/address-space budget.

Independent verification matched all 3602 selected low-workbook rows and all 12 query brackets using 60-digit Decimal arithmetic; maximum recovery difference was 3.26e-16 V. The complete local suite passed 727 tests with 7 skipped and 6 warnings in 166.55 s. Nine focused tests also verify source identity, finite/zero-current data and no extrapolation or model/network calls. [Verification receipt](benchmarks/stanford-k2-rest-timing-verification.json).
