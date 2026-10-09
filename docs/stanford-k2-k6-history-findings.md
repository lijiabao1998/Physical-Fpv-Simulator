# k2/k6 published-history inspection: incomplete source acquisition

**Overall premise: UNRESOLVED.** The frozen 30-file campaign stopped after 27 complete, checksum-verified workbooks because the next official download could not establish its HTTPS tunnel. Missing records are not counted as absent exposure.

The separately complete k2 history qualifies: its only recorded experiment before the selected 25°C/1C target is 25°C/0.05C. No nominal ≥2C experiment precedes that target in the selected published campaign. This is a narrow published-order result; unpublished exposure and manufacturing/storage history remain unknown.

k6 has 12 of its 15 selected records. Their provisional ordering also puts a 25°C/0.05C record before its target, but its three uninspected 5C records cannot be assigned a chronology. The predeclared contrast, “k6 had prior ≥2C exposure while k2 did not,” is neither established nor rejected.

## Frozen source and resource outcome

- Source: Edoardo Catenaro and Simona Onori, [DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original workbooks are unchanged; chronology, quality flags and integrals are derived analysis.
- [Protocol](stanford-k2-k6-history-protocol.md) and [exact 30-file manifest](../data/stanford-k2-k6-history-manifest.json) were frozen in [d962779](https://github.com/lijiabao1998/Physical-Fpv-Simulator/commit/d962779dda4c67a032cb519a7872fb6cccb65931) before acquisition.
- Inspected 995,676 rows in 27 workbooks: k2 526,560 rows / 15 files; k6 469,116 rows / 12 files. All acquired source lengths and SHA256 values matched.
- New response bodies: 62,199,183 bytes, within the 80,000,000-byte cap. Elapsed 287.399 seconds, within 600 seconds. Peak RSS 104,184 KiB; enforced address-space limit 4,000,000,000 bytes. The failure was transport, not exhaustion of these limits.
- The original failure report remains unchanged. A separate 0.008-second analysis read only its saved inspection JSONs to expose qualified k2 and provisional k6 ordering. It fetched no bytes and read no new workbooks.
- [Complete partial-evidence bundle](benchmarks/stanford-k2-k6-history-partial.json) retains the original acquisition result, every available phase, input/code hashes, per-file report digests, attribution and the stricter history qualification.

## Missing records and stop reason

| Missing source | Nominal temperature | Nominal rate | Status |
|---|---:|---:|---|
| NMC_k6_5C_05degC.xlsx | 5°C | 5C | CONNECT tunnel failed; no source body obtained |
| NMC_k6_5C_25degC.xlsx | 25°C | 5C | Not attempted after stop |
| NMC_k6_5C_35degC.xlsx | 35°C | 5C | Not attempted after stop |

These three manifest entries total 3,291,858 compressed bytes. Exact saved error: `URLError: <urlopen error Tunnel connection failed: 403 Forbidden>`. The Python HTTP client raises this message while establishing the CONNECT tunnel, before an origin HTTP response. No source-server headers were received, so this does not establish that Mendeley itself denied access. The reason for the tunnel denial is unknown. No retry, alternate endpoint or replacement specimen was used. All successfully verified raw files are retained locally for a separately authorized recovery.

## Quality and measured chronology

All 27 available records pass the fixed date/test and source-step clock checks: maximum relative date/test discrepancy 0.003596 s, maximum per-step origin deviation 1.46e-11 s, no reversed/duplicate test times, no recorded same-cell overlap or touching target boundary. Cross-cell simultaneous records are permitted. k2/25°C/5C has five recorded phases and no final rest; it is preserved as such. The other 26 inspected records have all six phases. Qualifying available files does not qualify an incomplete campaign.

Timestamps below are measured naive local dates; their time zone is not supplied. Upload dates are not used. Negative current is measured discharge current. Charge integrates only the observed discharge interval and does not fill missing starts. Temperatures are measured skin values, not a model average. Original measurement uncertainty and sensor/fixture calibration are not supplied.

### k2: 15/15 records

| Nominal condition | Measured start | Measured end | Relative to 25°C/1C target | Mean discharge A | Observed Ah | Peak skin °C | Steps |
|---|---|---|---|---:|---:|---:|---|
| 25°C / 0.05C | 2019-08-30T20:17:42.632000 | 2019-08-31T21:41:12.806000 | recorded before target | -0.250022 | 4.887153 | 25.158 | 1–2–3–4–5–6 |
| 25°C / 1C | 2019-09-02T19:11:01.133000 | 2019-09-03T02:54:42.246000 | target | -5.000371 | 4.770869 | 32.333 | 1–2–3–4–5–6 |
| 25°C / 2C | 2019-09-03T14:41:28.503000 | 2019-09-03T18:19:02.081000 | recorded after target | -9.998760 | 4.703478 | 45.358 | 1–2–3–4–5–6 |
| 25°C / 3C | 2019-09-04T07:09:16.445000 | 2019-09-04T13:57:22.542000 | recorded after target | -14.997260 | 4.559188 | 60.401 | 1–2–3–4–5–6 |
| 25°C / 5C | 2019-09-04T22:52:40.506000 | 2019-09-05T04:30:48.480000 | recorded after target | -24.997743 | 2.201183 | 75.088 | 1–2–3–4–5 |
| 35°C / 0.05C | 2019-10-04T16:04:36.154000 | 2019-10-05T17:22:46.952000 | recorded after target | -0.250026 | 4.860657 | 34.948 | 1–2–3–4–5–6 |
| 35°C / 1C | 2019-10-06T15:44:58.646000 | 2019-10-06T22:41:56.331000 | recorded after target | -5.000379 | 4.741939 | 40.417 | 1–2–3–4–5–6 |
| 35°C / 2C | 2019-10-07T00:21:02.938000 | 2019-10-07T06:43:20.508000 | recorded after target | -9.997523 | 4.599810 | 50.299 | 1–2–3–4–5–6 |
| 35°C / 3C | 2019-10-07T08:38:49.213000 | 2019-10-07T14:45:10.335000 | recorded after target | -14.997469 | 4.385638 | 61.836 | 1–2–3–4–5–6 |
| 35°C / 5C | 2019-10-07T16:10:46.173000 | 2019-10-07T21:59:39.691000 | recorded after target | -24.997351 | 3.495898 | 85.181 | 1–2–3–4–5–6 |
| 5°C / 2C | 2019-11-18T13:22:19.610000 | 2019-11-18T19:12:09.651000 | recorded after target | -9.997416 | 3.994005 | 29.203 | 1–2–3–4–5–6 |
| 5°C / 3C | 2019-11-19T00:35:38.996000 | 2019-11-19T06:48:34.753000 | recorded after target | -14.998673 | 3.993176 | 43.762 | 1–2–3–4–5–6 |
| 5°C / 5C | 2019-11-19T10:21:07.715000 | 2019-11-19T16:14:52.477000 | recorded after target | -24.997895 | 0.746610 | 29.357 | 1–2–3–4–5–6 |
| 5°C / 0.05C | 2019-11-19T16:25:11.423000 | 2019-11-20T14:19:20.267000 | recorded after target | -0.250023 | 4.675494 | 9.246 | 1–2–3–4–5–6 |
| 5°C / 1C | 2019-11-25T11:16:12.899000 | 2019-11-25T17:56:38.302000 | recorded after target | -5.000331 | 4.246130 | 13.173 | 1–2–3–4–5–6 |

### k6: 12/15 records

| Nominal condition | Measured start | Measured end | Relative to 25°C/1C target | Mean discharge A | Observed Ah | Peak skin °C | Steps |
|---|---|---|---|---:|---:|---:|---|
| 25°C / 0.05C | 2019-08-30T20:21:01.128000 | 2019-08-31T21:55:56.820000 | recorded before target | -0.250028 | 4.871639 | 25.526 | 1–2–3–4–5–6 |
| 25°C / 1C | 2019-09-02T19:14:19.907000 | 2019-09-03T03:11:57.569000 | target | -5.000355 | 4.732040 | 34.957 | 1–2–3–4–5–6 |
| 25°C / 2C | 2019-09-18T15:29:53.906000 | 2019-09-18T18:35:01.050000 | recorded after target | -9.998596 | 4.572229 | 47.674 | 1–2–3–4–5–6 |
| 25°C / 3C | 2019-09-20T10:17:24.464000 | 2019-09-20T16:41:17.187000 | recorded after target | -14.998677 | 4.272525 | 63.440 | 1–2–3–4–5–6 |
| 35°C / 0.05C | 2019-10-04T16:08:27.921000 | 2019-10-05T16:47:03.337000 | recorded after target | -0.250017 | 4.810579 | 35.075 | 1–2–3–4–5–6 |
| 35°C / 1C | 2019-10-06T15:48:50.008000 | 2019-10-06T23:02:40.709000 | recorded after target | -5.000138 | 4.620400 | 46.212 | 1–2–3–4–5–6 |
| 35°C / 2C | 2019-10-10T09:43:35.661000 | 2019-10-10T15:58:13.514000 | recorded after target | -9.999743 | 4.595042 | 53.771 | 1–2–3–4–5–6 |
| 35°C / 3C | 2019-10-10T16:15:00.871000 | 2019-10-10T22:19:30.969000 | recorded after target | -14.998691 | 4.449148 | 66.914 | 1–2–3–4–5–6 |
| 5°C / 0.05C | 2019-10-25T08:37:48.325000 | 2019-10-26T07:45:55.051000 | recorded after target | -0.250036 | 4.627342 | 7.407 | 1–2–3–4–5–6 |
| 5°C / 1C | 2019-10-26T15:02:52.548000 | 2019-10-26T22:23:28.823000 | recorded after target | -5.000203 | 4.420485 | 27.577 | 1–2–3–4–5–6 |
| 5°C / 3C | 2019-11-22T16:01:28.274000 | 2019-11-22T22:05:32.763000 | recorded after target | -14.998526 | 3.536532 | 13.992 | 1–2–3–4–5–6 |
| 5°C / 2C | 2019-11-25T11:26:58.001000 | 2019-11-25T17:58:36.764000 | recorded after target | -9.999351 | 4.233354 | 32.501 | 1–2–3–4–5–6 |

## Independent verification

An independent implementation re-read every one of the 995,676 raw rows and checked all 27 original lengths/hashes, source/report digests, date/test/step clocks, phase endpoints, current and temperature ranges, and charge integrals. It reproduced the qualified k2 ordering and provisional k6 ordering without calling the production classifier. This audit completed in 28.14 seconds with approximately 47 MiB peak RSS and no downloads, model calls or edits to the observations.

## What this changes

The complete k2 data establish its published target order without borrowing k6 chronology. They do not resolve the selected two-cell exposure contrast, establish equal initial electrode states or explain the previously observed voltage patterns. k3–k5 history remains unqualified. The existing k1 voltage RMSE of 191.474 mV, temperature-proxy failure and ORegan 30/36 empirical failures remain unchanged. No parameter, physical gate or material interpretation was fitted in this inspection.

Software checks for the frozen implementation passed all 309 tests; that is separate from incomplete source acquisition and unresolved scientific inference. Existing 80→120 numerical evidence was reused after calculation-hash verification, with no new large solve.

The next missing evidence is precisely the three checksum-pinned k6/5C workbooks, under an explicit recovery decision for the failed transport. Their eventual measured dates could qualify the fixed premise. Until then, the published report remains incomplete.
