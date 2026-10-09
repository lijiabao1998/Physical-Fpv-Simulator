# A frozen early specimen difference persists over the tested later interval

The low-rate 1.001 s descriptors predict the later 1C **between-specimen**
loaded-voltage-fall contrast to within 8.252 mV over the tested 10–3333.132326 s
interval. Measured tails beyond archived-model cutoff are excluded.
They do not predict either specimen's absolute voltage fall. Large individual
errors largely cancel in the contrast. No DFN state or physical parameter was
changed; the historical k1/k2 terminal RMSE values remain 191.474/55.003 mV,
both above the unchanged 50 mV gate.

The protocol received independent approval before calculation; its retained text
is the pre-run specification. Independent final review verified every retained
k1 source row and reproduced 300 summary values with a scalar implementation.

## Frozen prediction and later evaluation

The [reviewed protocol](stanford-contrast-persistence-protocol.md) froze the
previously published 0.05C response at 1.001 s:
k1 = 61.735064 mΩ and k2 = 32.283457 mΩ. These are signed descriptive
voltage/current ratios, not independently identified contact resistances.
Each is multiplied by that specimen's measured positive 1C current; the
prediction for the k1-minus-k2 fall contrast is about 147.266 mV.
No parameter was selected using the later windows or the 50 mV gate.

Let D be the fall from each record's own last rest voltage. The discrepancy is
Z = D1 − D2 − (I1 r1 − I2 r2). The common measured/model support ends at
3333.132326 s. The first 10 s were already examined; the following fixed windows
are development evaluation on previously viewed records.

| Elapsed-time window (s) | Mean Z (mV) | RMS Z (mV) | Max abs Z (mV) | Mean original DFN residual contrast (mV) |
|---|---:|---:|---:|---:|
| 10–60 | 0.640 | 0.649 | 0.899 | 150.825 |
| 60–300 | 0.193 | 0.326 | 0.775 | 150.328 |
| 300–900 | −1.619 | 1.767 | 2.947 | 147.509 |
| 900–1800 | −3.630 | 3.664 | 5.058 | 144.481 |
| 1800–3333.132326 | −5.533 | 6.253 | 8.252 | 142.171 |

The small contrast discrepancy must be read alongside the mean **individual**
D − I r errors: k1/k2 are 59.832/59.193, 129.168/128.975,
235.038/236.657, 463.633/467.263, and 814.776/820.309 mV across those
same windows. Their common growth includes the evolution of the underlying
cell voltage and polarization; a frozen onset descriptor was never a model
of that full evolution. It cannot be promoted to a complete voltage model.

## Conditional discharged-Ah alignment

Charge starts at each first observed loaded sample. The omitted command-to-first
sample intervals are 1.0006 s (k1) and 1.0003 s (k2); no charge is imputed.
Positive recorded current is integrated piecewise linearly and the quadratic
segment integral is inverted. All five predeclared points are supported by both
measurements and archived models.

| Conditional charge (Ah) | k1 time (s) | k2 time (s) | Z (mV) | Measured skin k1−k2 (K) |
|---|---:|---:|---:|---:|
| 0.5 | 360.977901 | 360.973334 | −0.637 | 0.587 |
| 1 | 720.954515 | 720.947399 | −2.265 | 0.369 |
| 2 | 1440.907855 | 1440.895350 | −3.511 | 0.213 |
| 3 | 2160.861620 | 2160.842059 | −6.417 | −0.008 |
| 4 | 2880.813649 | 2880.788335 | −7.481 | −0.373 |

This gives a similar gradual drift under a second coordinate. It does not
establish matched absolute SOC or electrode inventory. The roughly 45-hour
unobserved low/high-rate histories remain unresolved; no continuous replay is
performed across them. Acquisition latency and the exact physical switch time
are unverified.

Mean measured skin-temperature contrast changes from +0.798 K in the first
window to −0.280 K in the last. The corresponding model bulk-temperature
contrast changes from +0.741 K to +0.015 K. These are different observables;
correlation with the voltage drift does not identify a thermal cause.

## What this constrains

A specimen-dependent current-proportional descriptor captures most of the
between-record loaded-fall contrast across both rate and time. The remaining
time variation is real at the numerical resolution used here, but measurement
uncertainty is unavailable, so no physical/statistical acceptance is assigned.
The result motivates testing separately constrained specimen/fixture terms
rather than changing common electrochemical parameters to absorb the entire
~150 mV specimen difference. It does not identify which part is fixture loss,
cell ohmic response, kinetic/transport response or unresolved inventory/history.

A useful next discriminant is to inspect both cached low-rate full discharge
curves for capacity/cutoff and voltage-shape compatibility before treating
matched discharged Ah as a common internal state. No new simulation or fit is
justified solely by the small contrast error.

## Reproduction and provenance

[Machine-readable result](benchmarks/stanford-contrast-persistence.json) retains
all window summaries, individual errors, exact times, temperature observables,
archived model implementation identities, source hashes and history records.
[Source receipt](benchmarks/stanford-contrast-persistence-source.json) records
all 3601 rest and 3391 discharge k1 rows; all are retained in
[the normalized source](benchmarks/stanford-k1-discharge-records.csv.gz).
The original workbook SHA-256 is
`b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6`.
The gzip SHA-256 is
`9d5c84c83a116b2ed032ee638a57664c690866837c925a6fbf62c2e2acfb893c`.
Source: Catenaro and Onori, [Mendeley dataset v2](https://doi.org/10.17632/kxsbr4x3j2.2),
CC-BY-4.0. Existing k2 records and both archived mesh-120 curves are hash-pinned.

Run `python scripts/check_stanford_contrast_persistence.py` from the repository's
pinned environment. This cached-data analysis took 0.33 s within a 60 s/1 GiB
bound. No download, DFN solve, parameter fit or gate change occurred.
Voltage identities enforce 1e−12 V and charge inverse-forward checks enforce
1e−12 Ah as arithmetic tolerances only. Synthetic integration/inversion tests,
unsupported-point handling, source-tamper rejection and offline reproduction
protect the implementation; they do not validate the physical hypotheses.
