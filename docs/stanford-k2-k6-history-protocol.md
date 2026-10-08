# Selected k2/k6 published-history test v1

Frozen before acquiring or inspecting the 28 additional raw workbooks. The six nominal 25°C/1C records have already been inspected: k1/k6 showed similar voltage trajectories, whereas k2–k5 differed. This selection is exploratory after that observation. Choose k6 and the lowest-numbered specimen in the other observed pattern, k2. These are not established causal classes or manufacturing batches.

## Question and fixed selection

Test this narrow premise: strictly before each nominal 25°C/1C target in the published campaign, k6 had at least one nominal ≥2C experiment and k2 had none. This premise could explain a recorded exposure contrast; its truth would not establish damage or explain voltage causally. Its falsity would reject only that specific recorded contrast. Unpublished history remains unresolved in every outcome.

Select every published workbook for each chosen specimen: nominal 0.05, 1, 2, 3 and 5C at 5, 25 and 35°C, 30 files total. The exact selection, official individual URLs, byte counts and SHA256 values are in `data/stanford-k2-k6-history-manifest.json`, SHA256 `079b92508bba9e62ceabe3bb602fc358835d2abf799ea079ab0c0bc95e3f0cff`. Its official folder-response digests match the previously retained metadata in the original k1 chronology manifest. Source: Edoardo Catenaro and Simona Onori, [version 2, DOI 10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original measurements remain unchanged; exported chronology and integrals are derived analysis with attribution.

Selected compressed bytes total 69,170,148. The two previously verified 25°C/1C target workbooks total 3,679,107 bytes; newly required transfer is 65,491,041 bytes. Do not substitute specimens or omit inconvenient records. k3–k5 history remains unqualified; the existing k1 inspection is background only.

## Bounded acquisition and preservation

Use existing free cloud CPU, at most 80,000,000 new response-body bytes, 600 seconds for acquisition, parsing and classification, and a 4,000,000,000-byte process address-space limit. Read one workbook at a time; at most 50,000,000 inflated ZIP bytes per workbook. Reuse checksum-verified originals. Require exact compressed length and SHA256 before parsing. Download individual manifest URLs only, never the entire archive or executable author scripts. Record actual received bytes even for a failed transfer, preserve originals, and write per-file reports and progress atomically.

Stop on download, integrity, unsupported schema, time or memory failure. Preserve completed reports and identify the active file. A partial or budget-limited run cannot establish absent exposure. Do not automatically retry or change the selection. Freeze the protocol, manifest and tested implementation on the candidate branch before new raw acquisition, then record the exact source commit and before/after implementation digests with results.

## Observables and qualification

Inspect every row and contiguous phase. Retain source specimen/name/hash, naive local measurement start/end, all actual current ranges and time-weighted means in amperes, observed signed charge in Ah, measured skin-temperature extrema in °C, endpoint voltages in V, recorded steps and durations in seconds. A real five-step record ending after discharge is retained explicitly; absence of a final rest does not invent an extra phase or alone invalidate its recorded interval. Source labels are nominal C-rates, never a substitute for measured current or a change between 4.85-Ah and 5-Ah definitions. No DFN solve or parameter adjustment is performed.

Qualification requires all 15 selected files for each cell with matching source hashes, the fixed target present, supported contiguous phases [1,2,3,4,5] or [1,2,3,4,5,6], and both clock audits. Measurement dates must not reverse and elapsed date versus test-time discrepancy must be at most 1 second. Each source step clock must not reverse or become negative, must retain a stable test-minus-step origin within 1 second, and must have no duplicate test times or conflicting duplicate measurements. These are timestamp qualification tolerances, not physical model gates. Keep all violations visible; never repair, deduplicate or shift clocks.

Sort by measured start time, not file creation/upload time. Same-cell interval overlaps leave the campaign unqualified. Relative to the target, an earlier record must end strictly before its start, and a later record must start strictly after its end. Touching endpoints or overlaps are ambiguous. Report earlier lower-rate/other-temperature records and all later records, rather than only those supporting the premise. Cross-cell simultaneous intervals are allowed because different specimens can be tested concurrently.

Only when both entire selected histories qualify, report the premise as holds or false and enumerate the earlier nominal ≥2C records. Otherwise report unresolved with reasons and provisional order; missing data is never converted into zero exposure. The legacy k1 `recorded_order_qualified` field describes date order only; the new `history_qualified` additionally requires the complete clock/phase/hash/target checks above and alone governs this premise.

## Interpretation and stop

End after the 30-file chronology and fixed premise report, or the declared resource/failure limit. Manufacturing batch, storage, unrecorded cycling, sensor placement/calibration and fixture resistance remain unknown unless separate evidence resolves them. Measurement uncertainty is not supplied here. Similar rest voltage does not prove equal electrode state. Neither result establishes fresh cells, causal damage, independent predictive validation, or correctness of the model on k2–k5. Preserve the existing k1 ≈191-mV voltage failure and ORegan 30/36 empirical failures. No fitting, new simulation, GUI or deployment belongs to this batch.
