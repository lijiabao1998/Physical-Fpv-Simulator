# Li2025 GITT figure-to-input provenance

This static audit follows the [source qualification](battery-independent-source-audit.md).
It identifies two exact author-referenced input filenames but does not certify their public availability,
recorded temperature or specimen identity. No author code, simulation or fit was run.

## Verified source mapping

The official [Li2025 record](https://zenodo.org/records/14995785) supplies
`Scripts_to_reproduce_paper.zip` under CC-BY-4.0. The acquired archive is
2,634,078 bytes, MD5 `e720766f5244eee14c8fb840c6821926`, SHA256
`b97ec00f7e063ecfa8eb3b3f727a764381fb89fc95415a586cf4a87b04db20cc`.
[Machine-readable evidence](benchmarks/li2025-gitt-provenance.json) records
notebook hashes, zero-based cell indices and the loading-source excerpts.

| Figure panel | Author notebook | Exact relative input |
| --- | --- | --- |
| 14(a), 2C | `Reproduce_Li2024/2C_GITT.ipynb`, cell 8 | `LG_M50_BOL_GITT/2C_GITT_25deg.csv` |
| 14(b), 1C | `Reproduce_Li2024/1C_GITT.ipynb`, cell 7 | `LG_M50_BOL_GITT/1C_GITT_25deg.csv` |

Both read CSV without a header, ignoring `#` comment lines. They interpret column
0 as seconds, column 2 as volts, and negate column 3 divided by 1,000 to obtain
amperes. This establishes the author's interpretation of the missing input,
not independently verified units or raw measurements. Temperature is not read.

The figure export converts experimental time to hours and subtracts its first
value; it retains voltage and omits current. No experimental resampling or cropping
appears in that export path. Model and experimental series have different lengths.
The model current comes from an ideal pulse schedule; the measured current array
is used in a separate charge integration and does not drive the solve here.

## Timing and protocol qualifications

The main figure export and RMSE routine shift model time to
`sol.cycles[1].steps[2]` (post-pulse rest). The zoom routine instead uses
`steps[1]` (pulse onset). The specified pulse durations are 144 s at 1C and 72 s
at 2C, subject to the model's voltage cutoff. These are different model time
references; actual offset duration requires the saved solution. They do not
establish the experimental switch time or prove a measured/model alignment.

The [supplement](https://media.springernature.com/original/springer-static/esm/art:10.1038%2Fs41467-025-57968-3/MediaObjects/41467_2025_57968_MOESM1_ESM.pdf)
Figure 14 caption identifies 2C/1C, whereas Note 1 describes a separate C/2 RPT
GITT protocol. Its 10 Hz statement cannot be assigned to these arrays. The
notebook README has stale figure numbering, and the 1C notebook's opening heading
says 2C; the loading path, pulse specification and export panel establish the more
specific mapping above. A `25deg` filename and a 298K plot label are nominal
conditions, not measured temperature histories.

## Availability and exact missing evidence

The official 835.1 MB archive preview warns that it does not show all files. Its
visible listing ends among C/10 experiment files before the identified GITT folder
appears. Therefore absence from that preview does not prove absence from the ZIP.
The large archive was not acquired; neither raw CSV has a verified public member
identity, byte count, checksum or inspected channel schema in this audit.

A reusable input-driven comparison requires those two exact CSVs (or a verified
mapping to original acquisition files), their comments/headers and source hashes,
measured current/voltage timing, recorded cell and ambient/base temperature, and
cell identity plus conditioning/history. No cell serial or experiment-cell mapping
was identified in the selected notebooks. Same-specimen inventory/capacity or
independent electrode anchors remain separate requirements for resolving k2's
causal ambiguity. Do not reconstruct measured current from the ideal model pulse
text or substitute the generic C/2 ageing protocol.

The smallest next acquisition question is whether the official archive's full
member listing contains these exact paths, with bounded retrieval of only those
members if the host supports it. A complete 835 MB download, author outreach and a
new solver were outside this audit. No scientific acceptance gate changed.

## Audit chronology and reproduction

The [bounded static-inspection protocol](benchmarks/li2025-gitt-provenance-protocol.json)
was reviewed before opening notebook contents. The single small archive download
had already completed during parallel metadata research before that review. It
used a 40 s timeout and 4 MB maximum-size guard, and its actual size is below the
protocol's 3 MB post-download acceptance limit. Those bytes were reused; there was
no second download. Consequently this is not described as reviewed-before-download
acquisition. The receipt preserves this sequencing exception.

Verify the archive hashes, parse the selected notebook JSON as text, and read the
specified `cells[index].source` values. Do not execute notebook cells, imports,
outputs or author scripts. The independent review confirmed the file mapping,
column conversions, time-reference distinction and unresolved measurement claims.

Attribution: Ruihe Li and the Li et al. 2025 authors, DOI
[10.5281/zenodo.14995785](https://doi.org/10.5281/zenodo.14995785),
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). The receipt contains
selected source excerpts and a new descriptive mapping; original notebooks were
not modified or incorporated into the model implementation.
