# Independent electrical characterization source audit

Audit date: 2026-10-09. This is source qualification, not a new model validation.
The existing Stanford k2 55.003054 mV error still fails the 50 mV gate.

## Why this increment

The saved Stanford traces cannot distinguish inventory/OCP mismatch from loaded
polarization uniquely. Their approximately 1.14 s last-loaded/first-rest brackets
miss the instantaneous interruption response; temperature and prior history also
change, including an unobserved 45.497 h gap. Another fit or arbitrary solve would
not supply those missing measurements.

## Candidate decisions

| Official source | Useful constraint | Qualification limit | Decision |
| --- | --- | --- | --- |
| [Piombo et al. dataset, Mendeley zh58byr53c/1](https://data.mendeley.com/datasets/zh58byr53c/1), [methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC10907183/) | Fresh M50T cells; pseudo-OCV, HPPC and MultiSine characterization at 23 C; CC-BY-4.0 | Stated 1 s acquisition is not evidence of a subsecond interruption; no electrode inventory anchor | Relevant conditioned-cell comparison; not selected for a fast-pulse claim |
| [Kirkaldy et al. Zenodo10637534](https://zenodo.org/records/10637534) | M50T GITT and controlled base-cooling conditions; description states 10 Hz, 0.1 s response | Multi-GB archives; degradation-mode inventory estimates use fitted full-cell/half-cell alignment | Potential later acquisition, not downloaded wholesale |
| [National-lab rapid-pulse record14597394](https://zenodo.org/records/14597394) | Broad pulse design, SOC, temperature and health variation | 2.4 GB archive; no small original specimen file qualified in this pass | Deferred; no wholesale acquisition |
| [Li et al. source record14995785](https://zenodo.org/records/14995785), [paper](https://www.nature.com/articles/s41467-025-57968-3) | Small source-data package; electrode OCP and GITT figure workbooks | Figure data may mix measured, fitted and simulated series; cell/temperature/timing provenance needs inspection | Selected for bounded schema audit only |
| [ICM author repository](https://github.com/gumrukcuoglu/ICM), [published paper](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/306803333/GumrukcuogluAE2026Fast.pdf) | Electrode GITT study | Repository example is synthetic P2D; paper says experimental data available on request | Excluded as publicly available experimental input; no author contacted |
| [Fan2022 three-electrode study](https://wrap.warwick.ac.uk/id/eprint/166065/) | Electrode-resolved LG M50 study | No official public raw-data manifest/license verified | Literature lead, not acquired data |
| [ORegan5171874](https://zenodo.org/records/5171874) | Electrode parameter evidence | Already represented by this repository's ORegan kinetics manifest | Not new independent validation |

## Frozen acquisition question

[Protocol](benchmarks/li2025-source-audit-protocol.json) selects only Li2025
Supplementary Figures 10 and 14 before acquisition. The official record displays
Source_Data.zip as 10.8 MB, MD5 686c44f88eb26d26956a06c3d144409f. Its Rights
control was directly verified as CC-BY-4.0 in the cloud browser. Exact byte size
must be established from acquired bytes, not inferred from rounded display size.

The [supplement](https://media.springernature.com/original/springer-static/esm/art:10.1038%2Fs41467-025-57968-3/MediaObjects/41467_2025_57968_MOESM1_ESM.pdf)
discusses measured lithiation/delithiation OCP and separate analytic fits. Figure
14 is labelled 1C/2C GITT, whereas the ageing RPT description uses C/2. The latter's
10 Hz acquisition cannot automatically be assigned to Figure 14.

No electrode curve from another cell establishes Stanford k2's inventory. No
figure-table fit becomes an independent measurement. The audit must retain
unknown provenance, missing channels and access failures as explicit outcomes.

## Acquired evidence and result

The single reviewed official download succeeded. The archive is exactly
10,776,640 bytes; its published MD5 matches. SHA256:
`054b6019a110d2928f5abf1420ed13febf57231f6d8abb76a799ef0447765964`.
The archive inventory and selected workbook headers/row counts are saved in
[the schema receipt](benchmarks/li2025-source-schema.json).

Figure 10 contains four sheets of 1,001 rows each (including headers): graphite
OCP lithiation/delithiation/Chen comparisons, analogous NCM comparisons, and
separate electrode entropy curves. These are tabulated figure series. Neither
stored numeric cells nor the absence of Excel formulas establishes that values
are raw measurements; external analytic functions can be exported as numbers.
No raw measurement status or new electrode inventory constraint is certified.

Figure 14 contains two sheets labelled fig(a)/fig(b), with 123,194 and 140,783
rows including headers. Each explicitly separates `Time_h_Experiment`,
`Voltage_V_Experiment`, `Time_h_Model`, and `Voltage_V_Model`. Experimental and
model arrays must not be treated as synchronized by row index. The first sheet's
model times even start before zero. The headers contain no current or measured
temperature channel. Therefore the source supplies experimental voltage figure
series, but does not supply the synchronized input/thermal evidence required for
an independently specified pulse replay or instantaneous resistance estimate.

This is a useful partial qualification, not a new empirical PASS. Subsecond
voltage timestamps alone do not prove instrument latency, current-switch timing,
or current/voltage synchronization. Measured current, cell/ambient temperature,
conditioning and cell identity, and the mapping from source acquisition to figure
arrays remain prerequisites. Same-specimen inventory/capacity or electrode
anchors are still needed to resolve Stanford k2's separate causal ambiguity.

## Reproduction and attribution

Download only the pinned official file above, then run:

```sh
python scripts/inspect_li2025_source.py /path/to/Source_Data.zip
```

The inspector checks hashes and ZIP/XML limits and writes
`results/characterization-source-audit/schema.json`. It executes no workbook
formulas or external code. It records an initial header/row sample, counts all
selected-sheet rows/formulas, and explicitly marks time-distribution and
synchronization analysis as not evaluated. A byte-identical receipt was reproduced
locally. Two source-rejection tests pass, including Python optimized mode.

Attribution: Ruihe Li (repository creator) and Ruihe Li, Niall D. Kirkaldy,
Fabian F. Oehler, Monica Marinescu, Gregory J. Offer, Simon E. J. O'Kane,
2025, DOI [10.5281/zenodo.14995785](https://doi.org/10.5281/zenodo.14995785),
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
The committed schema receipt is an extraction/reformatting of selected workbook
metadata and initial rows; the original archive was not changed. The upstream
pinned archive remains the acquisition source. No manuscript text, author scripts,
or model parameters were imported into the battery implementation.

An [independent streaming XML check](benchmarks/li2025-source-independent-check.json)
confirmed both workbook hashes, all six sheet schemas and full column coverage.
Figure 14 experimental arrays have 123,193 and 140,782 points, versus 108,188 and
125,462 model points. Experimental timestamps strictly increase, but spacing is
mixed: the median is approximately 1 s in both sheets, with many 0.1 s and some
10 s intervals. The overall range is approximately 0.002 to 10.0001 s. This
positively rules out describing the complete figure arrays as uniform 10 Hz;
it does not identify the acquisition clock or switch latency. The inspector's
own timing fields remain 'not evaluated'; these timing statistics belong to the
separately identified independent check.

The successful independent streaming pass took 5.39 s. Its receipt also preserves
an unavailable optional-parser precheck and a stopped 512 MiB openpyxl attempt;
those attempts are not represented as successful verification.

Independent checker reproduction: place the pinned archive at
`results/characterization-source-audit/Source_Data.zip`, then run
`python scripts/verify_li2025_source_schema.py` from the repository root.
Its report matches the committed receipt apart from measured elapsed time.
Run without `-O`; optimized mode is explicitly rejected before source access.
Historical stopped-attempt labels are retained as recorded history, not new runs.
Full local suite: 729 passed, 7 skipped, 6 warnings (163.50 s).

The subsequent [GITT provenance trace](li2025-gitt-provenance.md) identifies the
two exact author-input CSVs, their column mappings and competing model time
origins. Their original raw bytes, recorded temperature and specimen mapping
remain unverified.
