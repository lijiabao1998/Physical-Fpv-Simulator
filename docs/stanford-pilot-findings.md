# Stanford external M50 pilot: measurements acquired, prediction not yet tested

The [official six-file manifest](../data/stanford-manifest.json) and [acquisition selection](stanford-acquisition-protocol.md) were committed in d26e24e81e138f6132989963fed76b66525fd24c before raw inspection. The k1 and manufacturer workbooks total1,878,840bytes; their official lengths and SHA256 digests match. Source files remain unchanged, and exported evidence carries CC BY4.0 attribution to Edoardo Catenaro and Simona Onori.

The exact manufacturer row identifies LG Chem INR21700-M50,4.85Ah,3.63V,69.25g and2.5V discharge cutoff. k1 contains28,669 measured records with named time, step, voltage, current and surface-temperature columns. The measurement timestamps span2019-09-02 to2019-09-03. Workbook creation in2020 and repository upload in2021 are different metadata and cannot substitute for experimental chronology.

| Contiguous phase | Recorded duration from step clock | Current or endpoint condition |
|---|---:|---|
| Thermal rest |3600.0014s|0A|
| Constant-current charge |8871.6131s|approximately1.62518A|
| Constant-voltage charge |5602.8989s|ends at0.0499914A and4.200017V|
| Pre-discharge rest |3600.0009s|0A; ends at4.186448V and25.187941°C|
| Discharge |3390.3968s|time-weighted mean−5.000325A; ends at2.499981V|
| Post-discharge rest |3600.0008s|0A; ends at3.061777V|

The source label is1C, but the actual current must be replayed in amperes. Neither4.85A from the manufacturer capacity nor a rounded5A is silently substituted.

The first discharge observation is at step-time1.0006s. The exporter preserves that coordinate; it does not shift the record to zero, invent initial data, or stretch the curve. Observed-window charge is4.707801Ah. Extending the constant-current assumption over the missing initial interval would add approximately0.00138981Ah, but that is explicitly a conditional estimate, not a measured value, rigorous bound or gate pass. Native intervals are retained, including short end-of-step intervals; there are no exact duplicate times in this pilot.

The [inspection JSON](benchmarks/stanford-k1-inspection.json) records every contiguous phase, original Excel row ranges, clock consistency, signed currents, temperature ranges and source provenance. The numerical schema tests reject corrupted hashes, active workbook content, reversed clocks and nonfinite fields. Repeated discharge blocks and conflicting timestamps cannot be silently reduced to a preferred trace.

This completes only the acquisition/parser pilot. No Stanford model comparison or parameter fit has run. The workbook does not establish its order relative to other high-current or temperature experiments. Freshness at campaign start is not proof that this record preceded all stress exposure. A subsequent validation protocol must resolve or explicitly qualify that history and preserve all empirical failure gates. The existing30/36 ORegan failures remain unchanged.
