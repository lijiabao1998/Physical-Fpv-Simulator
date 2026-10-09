# Current-profile arithmetic precision and implementation identity

This change repairs a floating-point evaluator defect. It does not fit a battery
model, acquire measurements, run a new k2 scientific solve, or establish physical
accuracy of the new implementation.

## Reproducible defect and correction

For time knots [0, 3] seconds, current knots [2^50, 1] amperes, and the largest
binary64 query below 3 s, the old convex-weight evaluator returns 1.125 A.
Exact rational evaluation of those same binary64 inputs rounds to
1.1666666666666665 A: an absolute error about 0.0416667 A, or 3.57143%.
These extreme currents are arithmetic stress inputs, far outside the solver's
research-current envelope. They do not demonstrate this error magnitude in a
real battery or the recorded k2 benchmark.

The defect comes from computing a small left weight as 1 minus an almost-one
fraction. Computing both weights directly fixes cancellation but can overflow
for finite maximal currents when independently rounded weights sum above one.
A regression preserves that rejected alternative's witness too.

The correction evaluates from the nearer endpoint, using its direct distance
and at most approximately half the endpoint difference. Positive input currents
keep that difference finite; near-endpoint subtraction is well conditioned.
Constant maximal finite current stays exactly constant. Charge integration is
unchanged; its subtractive coefficient is bounded below by one half.

The independent oracle integrates affine polynomials segment by segment using
Python Fraction representations of the actual binary64 inputs. It does not call
production interpolation/search/integration helpers. Tests cover 16 deterministic
irregular profiles, exact knots, adjacent representable times, interior points,
closed-interval rejection, power-of-two time/current scaling, a closed-form ramp,
and maximal finite current. The 256-machine-epsilon relative tolerance is an
arithmetic error allowance, not a relaxed scientific gate. Negative and signed-zero
currents remain rejected by the existing positive-discharge domain; negative-zero
initial time remains canonicalized. Subnormal, nonfinite and overflow constructor
cases retain their existing regressions.

## Recorded k2 inputs: scope of the change

The committed source archive yields currents 5.0003070831–5.0004320145 A.
No workbook is downloaded for this audit.

| Query set | Count | Changed evaluated values | Maximum absolute difference |
|---|---:|---:|---:|
| All source and declared-assumption knots | 3438 | 0 | 0 A |
| Historical mesh120 output times | 3993 | 146 | 8.881784197e-16 A |
| Adjacent representable internal-knot queries | 6872 | 500 | 8.881784197e-16 A |

These compare old and new standalone evaluator arithmetic, not solved voltages.
The core constructs its solver forcing with PyBaMM.Interpolant from the supplied
knots; it does not call CurrentProfile.value_at during that solve. Nevertheless,
this change does not certify the new implementation through an old solver result.
The historical 55.003054 mV k2 FAIL remains evidence for its original source commit,
not newly established voltage accuracy at the updated source tree.

## Identity and fail-closed validation

The profile content/protocol fingerprint is unchanged: identical knot bytes,
units and mathematical piecewise-linear law. Implementation identity is separate:
the full current_profile.py SHA256 changes from
9324ed84ee6ddd5bd142db99383ee69116b0d51bde759cd503680acde144d5d7 to
3ac01b06b0b43e6fa464d861e5117a7d28f1b4f55f339ec781069a76e74905a6.
Both scientific evidence caches include this source hash and therefore reject
reuse. Recorded artifacts and their hashes are unchanged.

PR cache misses now fail explicitly as scientific validation UNVERIFIED. They
cannot automatically fetch data or start expensive k1/thermal solves. The existing
manual dispatch route retains its 1200-second solve and 25-minute job limits;
using it requires a separately reviewed bounded scientific protocol. No dispatch
is performed by this change. The ordinary Battery research CI is unchanged: it
still acquires its existing checksum-pinned Chen inputs and runs its standard
benchmark/integration tests. This is not a claim that all CI is download- or
solve-free. A red scientific job is intentional evidence of
unverified current-code status, not a waived gate.

The no-solve k2 historical verifier authenticates its pinned ZIP, receipts and
original source commit, then recomputes the saved-array spatial comparison. Its
analysis dependencies remain pinned; only the unused current-profile evaluator
may differ. It explicitly reports current_calculation_compatible=false. The live
runner's strict current-source comparison is unchanged. This preserves readable
historical results without pretending they validate new code.

- [Reproducible k2 arithmetic comparison](benchmarks/current-profile-arithmetic.json)
- Run python scripts/audit_current_profile_arithmetic.py to reproduce it.
- Run pytest tests/test_current_profile_oracle.py for the independent arithmetic suite.
- Historical recovery source: 50c73ba21a6327c50e6d6c7ceec80f0e5c2dca84,
  [run 37871885149](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37871885149).

The missing external inventory/OCV constraints are a scientific identifiability
limit, not a pending permission request. This bounded software correction does
not resolve that limit or authorize a new solver search.
