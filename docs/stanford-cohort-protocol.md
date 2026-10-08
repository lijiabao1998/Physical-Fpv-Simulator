# Stanford six-cell measurement comparison, frozen before k2–k6 inspection

## Purpose and prior knowledge

Determine whether the measured loaded-voltage behavior of the existing k1 pilot is shared by the other five specimens in the same published study. This is an exploratory, source-to-source comparison after seeing the k1 result. It is not a blind study, a model fit, or a replay of the k1 model as though its current and initial state belonged to every cell. The manufacturing batch is unverified. No new battery-model solve is included.

The six nominal 25°C/1C files were selected in the original manifest before any model error. k1 has since been fully inspected and simulated. Its numerically converged 191.474 mV error and the existing Chen 6/12 and ORegan 30/36 failures remain. k2–k6 raw bytes have not yet been inspected for this comparison; their prior high-rate exposure and fresh-cell eligibility remain unresolved until their histories are separately traced. No file is replaced based on results.

## Fixed input selection and budget

Use every file below from `data/stanford-manifest.json` (SHA256 `94bde5dd872de039d145abf33f66fc81c38897b4666d68586f00c950478dc482`), DOI 10.17632/kxsbr4x3j2.2, Catenaro and Onori, CC BY 4.0. Preserve the official filename, byte count, URL and SHA256. Reuse the unchanged, already verified k1 workbook. Only k2–k6 require acquisition: 9,104,714 new bytes, 10,973,677 bytes for all six source workbooks. No manufacturer file, other rate, other temperature or complete dataset archive is newly downloaded.

| File | Bytes | SHA256 |
|---|---:|---|
| NMC_k1_1C_25degC.xlsx |1868963|b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6|
| NMC_k2_1C_25degC.xlsx |1802458|20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086|
| NMC_k3_1C_25degC.xlsx |1815535|7cf8168771c033405f6cf343240762c47322de4c7773e231c35d0d13b714515d|
| NMC_k4_1C_25degC.xlsx |1799620|f03e1bf2cc25ab8bfb631666768abc85947e47a21473041e92bb622067686a86|
| NMC_k5_1C_25degC.xlsx |1810452|43088a9b15950868fd505cdb9281e02750d0765f7cf1bdfc9b50260c397228b5|
| NMC_k6_1C_25degC.xlsx |1876649|8d1042224f8ba2e96da341dfd15e6d7542039c36c937d777d550c378e66c1fe1|

Bound acquisition and analysis to 600 seconds total and 10,000,000 new downloaded bytes. Read files sequentially, capped at their expected length plus one byte, with at most 60 seconds per network request and no unbounded retries. Verify size/SHA256 before parsing; preserve originals. Existing workbook safeguards reject encryption, macros, external links and inflated content above 50 MB per file. Record script/module/protocol hashes before reading new data and require them unchanged when writing final results.

An unavailable source, integrity failure, unsupported schema or overall budget exhaustion stops acquisition and preserves completed evidence as partial. Do not swap specimens or silently continue as a complete cohort. A missing final rest remains absent. Invalid or ambiguous measurement intervals disable the associated comparison and are reported, never repaired by selecting a better-looking trace.

## Identical source checks

Inspect all source rows: units and schema; recorded dates versus test/step clocks; duplicate/conflicting timestamps; contiguous protocol steps; current sign, range and time-weighted mean; unique discharge selection; all measured first/end times; cutoff voltage and observed capacity. Preserve the actual recorded amperes instead of deriving current from either 4.85 Ah or 5 Ah labels.

For each specimen retain preceding CC/CV endpoints, zero-current rest duration, final rest voltage/temperature, final 600-second rest-voltage drift where available, first loaded samples, commanded-time missing prefix and adjacent-sample delay. Report ΔV/ΔI only as an apparent transient ratio at that actual delay. The unobserved current ramp, measurement/calibration uncertainty, ambient trace and fixture cooling remain unknown. Do not create uncertainty bars from decimal precision or nominal instrument resolution.

Zero-current or protocol mismatches are visible qualification flags, not permission to omit a specimen. Duplicate source times are retained in inspection. Pairwise interpolation requires strictly increasing, finite discharge data; it does not collapse conflicting left/right values. No time-zero shift, capacity/SOC normalization, voltage offset, smoothing or fitted correction is allowed.

## Declared comparisons and outputs

Plot all six actual voltage curves, recorded current histories and measured skin temperatures with units, source identities, missing initial windows and actual endpoints. Each curve keeps its commanded discharge step-time. Source-only figures contain no inferred curves or invented model predictions.

Compute all 15 unordered source-to-source pairs, including the five comparisons to k1. For each pair use the union of original measurement knots on `[max(first times), min(last times)]`. Voltage, temperature and current differences use candidate minus reference; integrate the squared piecewise-linear difference exactly in time. Report time-weighted RMSE, signed time mean, maximum absolute difference and its time. Retain both complete observed intervals, common coverage relative to each, individual full observed current integrals and separate endpoint/capacity differences. Never extrapolate a measured tail or assume current during the missing initial interval for these metrics.

Report the full pairwise matrix and all specimen summaries. Do not fit a representative curve or declare an outlier using a post hoc cutoff. The result can show whether k1 resembles the recorded cohort, conditional on observed protocol differences. It cannot establish manufacturing-batch identity, equal histories, independent full-cell validation or a common physical cause. Each specimen would require its own correctly initialized measured-current replay before assigning it a model error.

Publish a compact JSON/Markdown report, source-only figure, source checksums/attribution, reproducible scripts and meaningful synthetic tests for irregular grids, unmatched windows and actual current differences. Raw workbooks remain outside Git. No model parameters, empirical gates or prior failed results change.
