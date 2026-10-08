# Stanford k1: recorded exposure history qualified

The [15-file selection and acquisition budget](stanford-chronology-protocol.md) and [official checksums](../data/stanford-chronology-manifest.json) were committed at 98141849eea6528a1b4b4abff4785b48c3b051cf before inspecting the additional raw files. Every workbook matched its source byte count and SHA256. Inspection completed in 163.80 seconds: 530,735 measurement rows, 35,182,688 compressed bytes total, of which 33,313,725 bytes were newly downloaded. The largest inflated workbook was 34,684,956 bytes, below the frozen 50 MB limit.

All 15 workbooks have the six contiguous protocol phases. Measurement dates are monotone; the largest disagreement between elapsed Date_Time and Test_Time is 0.006744 seconds. No experiment intervals overlap. Step clocks are nonnegative and monotone within each phase. Dates remain naive local source values; no timezone is invented.

The fixed pilot, k1/25°C/1C, ran on September 2–3, 2019. Within this published k1 campaign, only the 25°C/0.05C record preceded it. That preceding discharge delivered 4.861208 Ah over its observed window at approximately 0.250009 A, with a maximum measured skin temperature of 27.572°C. **No preceding high-rate experiment is present in these 15 files.** Manufacturing, storage, intervening and unpublished exposure remain unknown. This finding cannot establish a completely fresh cell or be generalized to k2–k6.

| Observed start, local date | Chamber label | Rate label | Mean discharge magnitude | Observed discharge | Maximum skin temperature | Last loaded voltage |
|---|---:|---:|---:|---:|---:|---:|
| 2019-08-30 | 25°C | 0.05C | 0.250009 A | 4.861208 Ah | 27.572°C | 2.499969 V |
| 2019-09-02 | 25°C | 1C, fixed pilot | 5.000325 A | 4.707801 Ah | 31.163°C | 2.499981 V |
| 2019-09-05, morning | 25°C | 3C | 14.997451 A | 4.554700 Ah | 61.117°C | 2.499969 V |
| 2019-09-05, afternoon | 25°C | 5C | 24.997355 A | 2.194217 Ah | 75.278°C | 2.744246 V |
| 2019-09-18 | 25°C | 2C | 9.998337 A | 4.502392 Ah | 48.524°C | 2.499827 V |
| 2019-10-04 | 35°C | 0.05C | 0.250011 A | 4.848749 Ah | 35.458°C | 2.499991 V |
| 2019-10-06 | 35°C | 1C | 5.000329 A | 4.651132 Ah | 41.919°C | 2.499990 V |
| 2019-10-08 | 35°C | 5C | 24.997266 A | 2.534442 Ah | 74.780°C | 2.615275 V |
| 2019-10-09, morning | 35°C | 3C | 14.997724 A | 4.350214 Ah | 59.373°C | 2.499987 V |
| 2019-10-09, afternoon | 35°C | 2C | 9.998046 A | 4.555629 Ah | 48.478°C | 2.499929 V |
| 2019-10-25 | 5°C | 0.05C | 0.250015 A | 4.686713 Ah | 7.257°C | 2.499989 V |
| 2019-10-26 | 5°C | 1C | 5.000398 A | 4.351278 Ah | 20.171°C | 2.499979 V |
| 2019-11-21 | 5°C | 2C | 9.997703 A | 3.737351 Ah | 16.578°C | 2.499971 V |
| 2019-11-22 | 5°C | 3C | 14.998526 A | 3.536532 Ah | 13.992°C | 2.499999 V |
| 2019-11-23 | 5°C | 5C | 24.999810 A | 0.398315 Ah | 7.575°C | 2.499989 V |

The ordering matters: 25°C/2C followed a high-temperature 5C record; rates were not performed in ascending order. Later temperature groups also followed earlier cycling. These repeated measurements are one cell's history, not 15 independent cells or an isolated causal temperature sweep. Prior stress is not proof of damage.

The [source paper](https://pangea.stanford.edu/ERE/pdf/OnoriPDF/Journals/57.pdf) specifies both 2.5 V discharge termination and a 75°C skin-temperature stop. The 25°C/5C record reaches 75.278°C while ending at 2.744246 V; the 35°C/5C record peaks at 74.780°C and ends at 2.615275 V. These are consistent with thermal curtailment, but the exported columns contain no explicit stop-cause channel. Do not treat their capacities as complete 2.5 V discharges or infer exact event causes from a rounded peak.

The [machine-readable chronology](benchmarks/stanford-k1-chronology.json) preserves every source digest, observed interval, actual current and temperature range, clock audit, ordering relation, acquisition budget and per-workbook inspection-report digest. Raw files remain unmodified and are not vendored. Reproduce with:

```sh
python scripts/inspect_stanford_chronology.py --fetch
```

This is source qualification, with **zero new model solves and zero fitting**. The k1 source-inspection pilot is separate from prospective k2–k6 predictions. Stanford's chamber setpoint is not a measured ambient time series, and its central skin thermocouple is not a core or volume-average thermometer. The fixture heat-transfer coefficient is unspecified; ORegan's fitted h=15 cannot be called an experimentally verified Stanford boundary. A future comparison must declare those assumptions, preserve the missing first 1.0006 seconds, and retain all existing empirical gates. The ORegan cohort remains 30/36 FAIL.

Data and derived summaries: Edoardo Catenaro and Simona Onori, DOI [10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), CC BY 4.0. Changes: checksum verification, protocol/time inspection, chronological ordering and scalar summaries. No laboratory endorsement is implied.
