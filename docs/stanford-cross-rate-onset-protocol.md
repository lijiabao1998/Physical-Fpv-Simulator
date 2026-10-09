# Frozen k1/k2 two-rate onset scaling screen

2026-10-09: frozen before recovering or examining the k1 0.05C waveform.
The record was previously catalogued/summarized in the chronology audit; this
is a post-hoc characterization screen, not a fresh blind holdout.

## Question and frozen prediction

The 1C comparison showed about 148 mV larger early loaded fall in k1 than k2,
with roughly 5 A current and nearly equal measured rest anchors. Does that
between-specimen contrast scale with current when compared with 0.05C records?
This tests transfer of an observable finite-time response, not contact resistance.

For each cell i and rate j define A_ij as the last recorded rest voltage,
D_ij(t)=A_ij-V_ij(t), and I_ij(t)=-I_raw,ij(t)>0 in amperes. At each frozen time:

- R_ij(t)=D_ij(t)/I_ij(t), finite-time apparent voltage response per ampere.
- Predict low-rate fall from the high-rate descriptor without refitting:
  Dpred_i,low(t)=R_i,high(t)*I_i,low(t).
- Report low-rate prediction difference D_i,low-Dpred_i,low for each cell.
- Report between-cell contrast at each rate, DeltaR_j=R_k1,j-R_k2,j, and the
  interaction DeltaR_low-DeltaR_high. Also report observed and predicted
  low-rate between-cell voltage-fall differences using both actual currents.

The high-rate descriptor is fixed pointwise by the prior observable calculation;
there is no optimization, selected R or fitted physical parameter. The existing
~29.6 mOhm high-rate contrast suggests about 7.4 mV at roughly 0.25 A only under
this proportional-transfer assumption. The calculation must use actual sampled
currents and report both cells individually, not only their difference.

No measurement uncertainty or statistical acceptance threshold is established.
Report magnitudes, signs and relative discrepancies when denominators are safely
nonzero; do not call numerical inequality a statistical rejection or assign a
physical PASS. Do not tune the unchanged 50mV aggregate voltage gate. Even close
agreement would not identify contact resistance: kinetics, transport, relaxation,
state/history, fixture and instrumentation can produce similar finite-time ratios.

## One bounded source recovery

Recover only the exact existing official chronology-manifest entry:

- `NMC_k1_0_05C_25degC.xlsx`, size 6,096,861 bytes.
- SHA256 `e5870c6989c94995de10e053f04efcf96951790e3c26e51d4c537261ba847ec5`.
- URL https://data.mendeley.com/public-files/datasets/kxsbr4x3j2/files/45abb642-b346-4041-b24d-88860aef1f28/file_downloaded
- Catenaro and Onori, DOI10.17632/kxsbr4x3j2.2, CC BY4.0.

One request, 120 s wall, 1 GB address space, at most expected size plus one byte read.
Verify exact size/SHA and existing 50 MB inflated-workbook safety guard before use.
Stop on denied access,403, hash/format mismatch or bounds violation; no alternative
route or blocked k6 retry. No other acquisition, solver or calibration is authorized
by this protocol. Preserve receipt, original identity and source normalization.

## Sources, support and timing

Reuse the already committed k1/k2 1C source slices and k2 0.05C rest/onset slice.
Inspect all original k1 0.05C rest/discharge records before retaining the complete
rest and initial discharge through first sample at/after10s. Preserve row indices,
naive dates, test/step clocks, voltage, current and skin temperature. Apply existing
canonical-phase, finite-value, strict-clock/date, zero-rest-current and negative-
discharge-current checks; report full-phase and retained-slice clock audits.

Use one common T0=max(first supported discharge sample of all four records),
then2,5,10s; require T0<2. No extrapolation or outcome-selected windows. This may
move the prior1.0006s query only if a new record requires later support. Re-evaluate
all four records at that same T0 from adjacent samples, and retain query brackets.
Use nominal command clocks; physical switching times and acquisition/filter
latency are not independently synchronized or known. Recorded rest/load sample
brackets are not verified bounds on physical current onset.

Report each last-rest anchor and both10s/60s rest-tail summaries. Report measured
skin temperature at every query and all pairwise within-cell cross-rate and
between-cell same-rate differences. No internal-temperature equivalence is implied.
Report naive record dates and same-cell inter-record gaps without replaying missing
history. Similar rest voltage does not establish equal SOC, inventory, state of
health or equilibrium. Cell and fixture identity/history remain confounders.

## Verification, limits and deliverables

Independent protocol review before recovery and computation; source/implementation
review before publication. Analysis bound 60 s / 1 GB / one BLAS thread, no DFN solve.
Synthetic checks cover proportional transfer, nonlinear/nontransferring response,
current signs/units, current imbalance, source identities and supported queries.
Retain all four individual responses, predicted low-rate values, discrepancies,
source/license/hash records, reusable code and concise findings in draftPR1.
No GUI, deployment, parameter promotion or threshold relaxation. Existing k1
191.474mV and k2 55.003mV failures remain unchanged.

Independent protocol review: GO for the single bounded recovery. Interpolate
voltage and signed current separately before computing D/I. The voltage interaction
uses both actual low-rate currents, never a substituted common current. Report
current ranges over each retained onset interval and preserve the conditional
nature of instantaneous ratios when current histories differ. The four nominal
times are correlated observations, not independent replicates; rest-tail variation
is descriptive and is not an uncertainty estimate.
