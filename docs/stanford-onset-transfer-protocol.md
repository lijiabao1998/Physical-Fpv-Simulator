# Frozen k1/k2 same-query near-start transfer

2026-10-09: frozen before comparing the k1 near-start values. Both records were
previously viewed in other analyses; this is a descriptive transfer of the k2
rest-to-load method, not a blind holdout or a parameter calibration.

## Question

Does the much larger historical k1 terminal-voltage error appear already near
load start, and how much of its difference from k2 is associated algebraically
with measured rest-anchor differences versus measured rest-to-load voltage falls?
Use only cached original records and saved model terminal curves. Do not infer
unsaved k1 internal concentrations, bulk OCV or polarization components.

## Inputs and frozen method

- k1 original `NMC_k1_1C_25degC.xlsx`, retained in the current-source replay input
  ZIP from run37887926852, exact original SHA256
  `b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6`.
- k1 committed mesh120 terminal CSV gzip SHA256
  `b88bee993c17315197598f50f19ed72d6023d158b0bb8b1ea8c6e86761a611ba`.
  Verify against the existing committed evidence receipt; any transcription
  mismatch stops analysis until reconciled from that unchanged receipt.
- k2 committed original records and state-scalar terminal curve, already used
  by the onset comparison, with their exact existing pinned hashes.

No acquisition, solve or fit. Reuse the validated clock and phase qualification
from the k2 onset method. Inspect all original rest/discharge rows before retaining
all rest rows and initial discharge through the first sample at/after10s, with
original dates, row numbers and both clocks. Require zero rest current, negative
raw discharge current, monotone clocks/dates and no removed or reordered rows.
Report per-phase clock audit and recorded rest-to-load sample brackets. Unknown
instrument/filter latency means these are not verified physical-switch bounds.

Query at T0=max(first supported discharge sample of both cells and first supported
model output of both), then2,5,10s; require T0<2. Use the same common T0 for both
cells, without extrapolation. This support rule is frozen before reading k1 values;
it avoids comparing an unsupported earlier time. The remaining queries are exactly
the previously frozen2/5/10s. Interpolate only between adjacent actual samples.
Report exact query times and provenance brackets. The clocks are nominal command
and model clocks, not independently synchronized physical-current onset times.

For each cell retain both10s and60s rest-tail mean/extrema/endpoint-change summaries,
last-rest anchor, measured current/voltage/skin temperature at all queries, and
saved model terminal voltage/temperature. Skin and bulk temperature remain
separate observables. Report different cells, experimental histories and fixture
identity as potential confounders; equal nominal rate/ambient is not equivalence.

## Predeclared algebra and interpretation

For cell i, let A_i be its last observed rest voltage, H_i(t) its measured loaded
voltage, M_i(t) its saved model terminal voltage, D_i=A_i-H_i its observed fall,
and E_i=M_i-H_i its terminal residual. All deltas below mean k1 minus k2:

Delta E = Delta M - Delta A + Delta D.

Report every term at every fixed query, with closure≤1e-12V. This separates an
observed rest-anchor contrast from an observed loaded-fall contrast without
inventing a k1 internal-state decomposition. The identity itself is not a causal
model. Report the signs and magnitudes; do not assign statistical significance
without measurement uncertainty. A small Delta A cannot establish equal SOC,
inventory or equilibrium, and Delta D does not uniquely identify ohmic/kinetic/
diffusive behavior or fixture resistance.

Define I_i(t) = -I_raw,i(t) > 0 in amperes. Report each observed D_i/I_i
as finite-time apparent response per ampere, without
selecting/fitting a sharedR or comparing it as equivalent to30sDCIR/1kHzACIR.
The previously found absence of a shared whole-trajectory algebraicR interval
remains intact. No pointwise query is judged against an aggregate RMSE gate.
Preserve original k1~191.474mV and k2~55.003mV failures at unchanged50mV.

## Bounds and verification

One cached-data calculation,60s/1GB/oneBLASthread. Independent protocol review
before calculation and final source/code review before publication. Synthetic
checks cover Delta identity/signs, constant-anchor-only and load-fall-only cases,
unequal support, changed hashes and no-download/no-solve reproduction. Persist
source slice, recipe, hashes, exact-query result and concise findings in draftPR1.
No changes to physical parameters, model caches, deployment or GUI.

Independent protocol review: GO after explicit positive-current definition.
Report known forcing and thermal-boundary differences between archived model
runs; Delta M retains these effects. Missing model temperatures must remain
unavailable rather than being reconstructed.
