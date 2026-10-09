# Same-cell load-transition inspection

All 15 previously checksum-pinned k1 workbooks were inspected in 20.63 seconds, with no new download, battery-model solve or fit. Every 530,735 measurement row was read. The selection is the original chronology manifest, not a subset chosen for prediction agreement. These are repeated measurements of one cell, not 15 independent specimens or an independent validation set. k2–k6 have not been inspected or simulated by this diagnostic.

Run `python scripts/inspect_stanford_transitions.py`. The full output retains every protocol boundary and the first/last ten samples in each recorded phase. The [public scalar and boundary summary](benchmarks/stanford-k1-transitions.json) retains all 15 cases, raw-file hashes, row numbers, the preceding CV endpoint, rest duration, temperatures, first ten loaded samples, original timestamps and earlier high-rate filenames. The computation uses the last rest sample and first loaded sample without time alignment, smoothing, current normalization or an inferred voltage offset.

## Apparent transient impedance at the recorded delay

The reported quantity is ΔV/ΔI between adjacent recorded samples. Its sign convention uses the source's negative discharge current. It contains finite-rest effects, unresolved fast response, electrochemical polarization and the measurement boundary. It is not isolated ohmic or contact resistance. The interval from the commanded discharge start to the first source sample remains unobserved; the true initial current ramp is unavailable.

Rows below follow measured chronology, not rate order. The two delay columns deliberately differ: one is the first recorded discharge step-time, the other is the actual gap from the last recorded rest sample. “Earlier high-rate files” counts prior published k1 records labelled at least 2C; unrecorded history remains unknown. Surface temperature is measured at the end of the preceding rest, not inferred from the nominal chamber label.

| Source file | First discharge magnitude (A) | Initial skin (°C) | First step-time (s) | Adjacent-sample gap (s) | ΔV/ΔI (mΩ) | Earlier high-rate files | Final rest |
|---|---:|---:|---:|---:|---:|---:|---|
| NMC_k1_0_05C_25degC.xlsx |0.250039|25.058|1.0010|1.046304|61.735|0|yes|
| NMC_k1_1C_25degC.xlsx |5.000240|25.188|1.0006|1.045580|61.299|0|yes|
| NMC_k1_3C_25degC.xlsx |15.002747|24.468|1.0002|1.046004|33.677|0|yes|
| NMC_k1_5C_25degC.xlsx |25.004250|24.418|1.0004|1.045080|32.499|1|absent|
| NMC_k1_2C_25degC.xlsx |9.997650|24.995|1.0007|1.045080|48.628|2|yes|
| NMC_k1_0_05C_35degC.xlsx |0.250042|35.264|1.0009|1.047828|74.229|3|yes|
| NMC_k1_1C_35degC.xlsx |5.000428|35.150|1.0012|1.047004|74.681|3|yes|
| NMC_k1_5C_35degC.xlsx |25.004356|34.678|1.0006|1.047852|36.328|3|absent|
| NMC_k1_3C_35degC.xlsx |15.004112|34.661|1.0007|1.047340|37.351|4|yes|
| NMC_k1_2C_35degC.xlsx |10.002098|34.678|1.0001|1.046628|37.954|5|yes|
| NMC_k1_0_05C_05degC.xlsx |0.250044|5.784|1.0007|1.045680|84.013|6|yes|
| NMC_k1_1C_05degC.xlsx |5.000353|8.342|1.0003|1.044656|79.761|6|yes|
| NMC_k1_2C_05degC.xlsx |10.002243|7.061|1.0006|1.045604|53.873|6|yes|
| NMC_k1_3C_05degC.xlsx |15.002258|4.796|1.0001|1.043756|57.194|7|yes|
| NMC_k1_5C_05degC.xlsx |25.002625|4.808|1.0004|1.043956|55.986|8|yes|

The apparent ratio spans 32.499–84.013 mΩ. In the 25°C-labelled series, the 0.05C/1C values are 61.735/61.299 mΩ, whereas 3C/5C are 33.677/32.499 mΩ; the later 2C measurement is 48.628 mΩ. These observations do not establish a temperature or current law: sample delays are not identical, the nominal 5°C/1C file starts at 8.342°C, and rates/temperatures are mixed with chronology and prior exposure. A universal fixed correction resistor is not identified by this table. No resistance is inserted into the model.

## Missing phases and uncertainty

Thirteen files contain six phases; 25°C/5C and 35°C/5C end during discharge, with no recorded final rest. The original individual inspections correctly marked this, but the earlier chronology prose incorrectly said all 15 contained six phases. That prose is corrected. The first transition-inspector attempt likewise rejected the missing final rest after 13 files; the parser now explicitly accepts either the complete six-phase sequence or the documented five-phase prefix, and reports absent rest without manufacturing records. Missing internal phases still fail inspection. Existing thermal-curtailment observations and source checksums remain unchanged.

Campaign calibration uncertainty for voltage/current and the sampling clock is unavailable, so uncertainty fields are null. Instrument display precision, advertised resolution and the authors' differently defined pulse averages do not supply uncertainty bounds for this ratio. No confidence intervals or equal-delay claims are invented. The first ten loaded records are preserved for checking the measured part of the current transition; they cannot recover the unobserved ramp.

This is evidence for narrowing a diagnosis, not proof of a unique defect in sensing, contacts or electrode kinetics. Cell-batch transfer, published calibration conditions, state history and sensing/thermal boundaries remain unresolved. The previously completed 80→120 numerical PASS and 191.474 mV empirical FAIL are unchanged, as are Chen 6/12 and ORegan 30/36 failures. Further parameter work requires a separately frozen calibration/check plan; these inspected k1 traces cannot subsequently be relabelled blind holdouts.

Measurements and adapted boundary excerpts: Edoardo Catenaro and Simona Onori, DOI [10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), CC BY 4.0. No source data were modified and no institutional endorsement is implied.
