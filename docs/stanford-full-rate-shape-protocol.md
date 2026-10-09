# Frozen four-record capacity and voltage-shape characterization

Pre-run specification: obtain independent review before calculating results.

## Question

Do the cached k1/k2, 0.05C/1C full discharge records show capacity, cutoff,
voltage-shape or temperature differences that limit treating equal discharged
Ah as comparable internal state? A secondary descriptive column removes only
the already frozen onset voltage/current terms. It must not identify physical
resistance or become a parameter fit.

All four records have been viewed; this is development characterization, not
blind holdout validation. The manufacturer identifies LG Chem INR21700-M50,
4.85 Ah nominal capacity and 2.5 V discharge cutoff. A shared product label does
not establish matched production lot, prior history, inventory or SOC.

## Sources and selection

Use complete phase5 discharge rows from the already cached, checksum-verified
NMC_k1_0_05C_25degC.xlsx, and the committed complete k2 low-rate normalized
source, complete k1 1C rest/discharge source and k2 1C source. Reuse the committed
cross-rate report for the four rest anchors and the frozen 1.001 s low-rate
descriptors. No source acquisition or model simulation is needed.

Qualify every source phase's finite values, positive discharge-current magnitude,
strictly increasing date/test/step clocks and fixed command origin. Retain row
indices, source timestamps, all complete discharge rows, archive/workbook and
normalized hashes, CC-BY-4.0 attribution, normalization recipe and source metadata.
The existing normalized low-rate schema retains row/date/step/current/voltage/skin
columns; per-row test time is absent. Its pinned source receipt retains the
original test/step clock audit. Preserve that distinction; never reconstruct test
time and label it observed. Use the same explicit schema for newly normalized
cached k1 low-rate rows.
Record exact first/last sample dates and step times, and distinguish source-naive
timestamps from UTC. No unobserved interval is interpolated across records.

## Frozen observables

For each full measured record report:

- First/last loaded voltage and skin temperature, minimum/maximum voltage and
  skin temperature, and time-weighted mean discharge current and current range.
- Observed duration and positive discharged Ah, integrating the piecewise-linear
  measured current from the first loaded sample to the final loaded sample.
- Final recorded voltage minus the nominal 2.5 V cutoff, without assigning a
  cutoff pass/fail or assuming the acquisition captured the exact crossing.
- The command-origin to first-sample time interval, with omitted charge explicitly
  unknown. Do not impute that charge or call the observed integral total capacity.
- Observed Ah divided by 4.85 Ah as a descriptive nominal-capacity fraction,
  never inferred SOC, SOH, capacity loss or an aged-cell diagnosis.

Report k1-minus-k2 observed-charge differences at each rate and low-minus-high
rate differences within each specimen. A difference cannot be assigned uniquely
to degradation: rate, temperature, cutoff, missing initial observations and
unknown intervening history also affect it.

At Q = 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5 Ah from each first observed sample,
invert each piecewise-linear current integral to obtain that record's own time.
Reject nonpositive current; preserve unsupported points as unavailable with a
reason. No extrapolation, re-zeroing at another support boundary or fractional
capacity alignment. Verify inverse-forward arithmetic within 1e-12 Ah.
Interpolate voltage, current and skin temperature only inside each support.
Report the four times and temperatures at each Q.

Use the previously frozen r_j = [A_j,low − V_j,low(1.001 s)] / I_j,low(1.001 s).
For each record report raw V and the separate descriptive quantity W = V + I r_j.
It is an algebraic offset to measured voltage, not simulated terminal voltage,
OCV or a physical correction. Do not recalibrate r_j at any later Q or rate.

At supported points report:

1. Raw and W k1-minus-k2 contrasts within each rate.
2. Raw and W low-minus-high voltage differences within each specimen.
3. Low-minus-high temperature differences within specimens, and k1-minus-k2
   temperature differences within rates.
4. The low/high rate interaction of the specimen contrast, both raw and W.
   Define the sign explicitly, for X in {V, W}:
   (X1,low − X2,low) − (X1,high − X2,high) =
   (X1,low − X1,high) − (X2,low − X2,high).
   Verify this equivalent within-specimen difference-of-differences identity
   within 1e-12 V; do not interpret an identity as an independent experiment.

Keep every predeclared point and each specimen/rate result. Preserve a pairwise
contrast whenever its own two records are supported; only the four-record
interaction needs all four. W at its defining low-rate onset query equals that
record's rest anchor by construction, which is not independent validation. No selection by
outcome and no new goodness-of-fit threshold. These correlated development
observations lack experimental uncertainty and matched state, so assign no
statistical or physical acceptance label. The historical DFN 50 mV gate and
k1/k2 failures remain unchanged.

## Bounded execution and tests

No download, DFN solve, parameter search, paid resource or new credential.
Normalize the cached workbook under a 120 s/1 GiB bound; evaluate the four records
under 60 s/1 GiB. Pin the protocol and all input/code identities before analysis.
Independently review signs, Ah units, complete-phase inclusion and the interpretation
of W. Tests cover analytically integrable variable current, unequal supports,
retained unavailable targets, contrast identities, frozen-descriptor use, exact
source rows/hashes and changed-input rejection. Reproduce without network access.
