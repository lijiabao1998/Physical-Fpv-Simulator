# FPV thermal and physical-evidence audit

Audit date: 2026-10-11. Machine-readable findings, source hashes, exact probe
settings and a portable analytical oracle are in
[`fpv-thermal-audit.json`](fpv-evidence/fpv-thermal-audit.json).

## Result

**The new synthetic powertrain passes the inspected thermal equations and
accounting checks. Real FPV thermal prediction remains unvalidated.** The saved
ORegan cohort still has **6/36 empirical passes and 30/36 failures**, with no
uniquely established physical cause for those failures. No parameter, initial
state, model core, acceptance target or source trace was changed in this audit.

The initial verification stage was entirely offline. A subsequent single bounded
official raw-data acquisition attempt was denied by the network tunnel; no raw
archive was acquired. No PyBaMM battery solve was run. The new powertrain time
steps verify an analytical synthetic model;
they are not laboratory observations. The audit independently reviews the new
module rather than treating its author's tests or energy residual as empirical
validation.

## 1. What was actually reproduced

### Frozen cohort: scalar re-gating, not raw-trace reconstruction

Every retained case in [`thermal-summary.json`](benchmarks/thermal-summary.json)
was re-gated from its stored scalar errors with the unchanged protocol limits.
All stored gate and aggregate classifications match. There are **12 cells reused
across temperature, not 36 independent cells**.

| Result | Cases |
|---|---:|
| Electrical and temperature-proxy gates pass | 6 |
| Electrical gates fail, temperature-proxy gates pass | 19 |
| Temperature-proxy gates fail, electrical gates pass | 4 |
| Both fail | 7 |

Thus “30/36 failures” is the combined empirical outcome, **not 30 temperature
failures**. The surface-temperature proxy passes in 25 cases and fails in 11.
Overlapping failure counts are: voltage RMSE 23, voltage peak 26, capacity 16,
energy 16, coverage 12, temperature RMSE 11 and temperature peak 8. Voltage RMSE
ranges 24.5124–87.9992 mV; temperature-proxy RMSE ranges 0.352031–14.680688 K.
All 36 stored physical-audit flags pass; all 36 cohort numerical stages are
`not_run`. A recorded audit flag is not a fresh reconstruction of its inputs.

**Local evidence gap:** `data/oregan/raw/validation.zip`, the 36 complete model
trajectories and their raw residual/heat arrays are absent from this checkout.
Consequently this audit cannot independently regenerate the 36 measured/model
RMSEs, missing-tail coverage, sensor selection or heat integrals from raw samples.
The compact summaries and saved historical verification receipts do not replace
those inputs. No missing data are inferred or fabricated.

### Bounded official raw-data acquisition: BLOCKED

After the initial audit, one attempt used the unchanged
`physical_fpv.thermal_data.fetch_thermal_data` path and the manifest-pinned
[official Zenodo archive](https://zenodo.org/records/4864437/files/brosaplanella/TEC-reduced-model-v1.0.zip?download=1).
The expected file is 23,155,564 bytes with SHA256
`3848d0eb1d70e4fc86cc77c272433053760b0bdfe25825ef652135edc43275b8`.
The complete attempt had a 120-second wall-time limit; the existing downloader
reads at most 24,000,001 bytes and rejects content exceeding 24,000,000 bytes,
within the authorized 32 MiB bound.

At 2026-10-11 04:51:42 UTC it started; after 6.331 seconds it returned
`URLError: <urlopen error Tunnel connection failed: 403 Forbidden>`. No archive
was created and no checksum could be verified. The attempt stopped without a
retry or alternate route around the access denial. Consequently no new raw-derived
cell790 empirical comparison or full source-cohort inspection was performed.
The saved cell790 metrics below retain their original evidence labels. Even if
the raw archive is later made available through an authorized route, the missing
36 model trajectories remain a separate whole-cohort replay limitation.

### Saved representative numerical curves: directly recomputed

Both historical 335-row grid80 and grid120 CSVs are present. This audit directly
compares their piecewise-linear curves on the union of time knots over the full
common interval, 0–3333.391292865383 s, without extrapolation:

| Quantity | Recomputed value | Frozen limit | Result |
|---|---:|---:|---|
| Maximum voltage difference | 3.320930023 mV at 140 s | 5 mV | PASS |
| Maximum temperature difference | 0.018017735 K at 920 s | 0.1 K | PASS |
| Relative endpoint-capacity difference | 0.003445980% | 1% | PASS |

Both saved curves are finite with strictly increasing times and approximately
2.5 V terminal endpoints. Their independently recomputed maximum charge errors
are 2.35e-13 and 2.44e-13 Ah; relative total-lithium drifts are 1.85e-14 and
2.54e-14. Native spatial concentrations, heating and cooling fields cannot be
reconstructed from these five-column CSVs.

The retained grid40→80 result **fails** at 14.331231 mV and 0.207438 K; its peaks
are away from the cutoff endpoint. The grid40 trajectory is absent, so that
comparison was read from its saved report rather than recalculated here. A
single grid80→120 pair passing does not establish an exact-solution error bound,
the complete cohort's convergence or its required tolerance-refinement result.
See [numerical status](thermal-numerical-status.md).

## 2. Established mechanisms versus unresolved causes

### Surface, volume average and core are different observables

The research model evolves **volume-average lumped temperature** and compares it
with a casing thermocouple as an explicit proxy. It does not resolve a core-to-skin
gradient, sensor attachment/time lag or spatial casing temperatures. In the
retained cell790 model-state diagnostic, the field named “surface temperature” is
the prescribed 298.15 K boundary; it is not a second predicted thermocouple.
At cutoff the evolving lumped temperature is about 309.626 K.

This observable mismatch is established. Its contribution to any empirical
residual is not identified. A passing temperature-proxy error cannot establish
core temperature, local hotspots, safety or correct heat generation.

### Cooling boundary is assumed, not independently measured per trace

The frozen research reconstruction uses published **h = 15 W/(m² K)**, a source
fitted parameter, with nominal ambient. Initial cell temperature comes from the
last zero-current pre-discharge reading. Those are different roles. For cell790,
the saved report explicitly says the ambient sensor is absent; a nominal 25°C
value must not be relabelled as a measured chamber time history.

Heat generation, thermal capacity, boundary conductance, ambient drift and
surface/core mismatch can compensate in a single temperature trace. Neither a
heat-balance residual nor imposed measured-surface-temperature forcing identifies
the cooling coefficient. Such forcing would jointly bypass thermal generation,
storage and cooling and still assume surface≈volume-average temperature.

### Cell790 identifies model behavior, not a unique real-cell defect

The retained grid120 empirical result has voltage RMSE **54.8086 mV** and peak
error **383.3522 mV**, both failures. Its temperature-proxy RMSE **1.17226 K** and
peak **1.62967 K** pass. Model cutoff is **157.6567 s early**, with 95.4840% time
coverage. These measured/model metrics are quoted from the saved diagnosis,
not independently recalculated from absent raw measurements here.

The saved internal-state diagnostic reconstructs model voltage within 9.934e-10 V
and independently relates electrode means to conserved charge. At cutoff, the
largest modeled loss is **338.651 mV of negative-particle concentration
polarization**. This establishes how this particular model reaches cutoff while
average lithium remains available. It does not prove that the real cell has that
gradient or that changing negative diffusivity is the correct repair.

### Initial inventory and history remain underdetermined

The eight concentration/active-fraction/thickness values in the published-
definition ledger were independently compared with installed ORegan2022 scalars;
all match. This is a recheck of the retained ledger, not a new reading of the
original manuscript, and it establishes no numeric transcription correction.
The source's initial concentrations are calibrated published values, not direct
measurements of each cohort cell's initial electrode inventories.

Cell790's initial uniform-state OCV is only about 1.64 mV above its pre-discharge
rest value at the actual initial temperature (1.69 mV using the 25°C reference).
One OCV does not determine both electrode stoichiometries and active capacities.
At the measured delivered charge, frozen-inventory uniform-state accounting
predicts about 2.776684 V versus 3.089640 V at the recorded two-hour rest endpoint,
a conditional −312.956 mV discrepancy. That endpoint still rises 3.45 mV over its
last ten minutes: equilibrium is not established.

Inventory/capacity, OCP applicability, residual gradients, hysteresis and
conditioning/history remain competing explanations. This calculation is neither
a measured SOC nor a relaxation simulation. An initial-voltage/SOC fit would not
resolve that identifiability problem and was not performed. See the
[causal diagnosis](causal-diagnosis.md) and
[retained rest audit](benchmarks/cell790-rest-state.json).

### Parameter extrapolation is established; its error is unquantified

The declared measured temperature supports differ: solid diffusion 5–45°C,
exchange current 15–45°C, heat capacity 25–100°C. The cold cohort conditions
necessarily extrapolate some laws; hot endpoints can cross upper support too.
Nominal ambient inside one interval does not establish trajectory-wide or
stoichiometry-wide support.

This audit also directly compares the locally vendored kinetic sample envelope
with **cell790's own** saved polarization extrema:

| Electrode | Released kinetic stoichiometry range | Cell790 surface range |
|---|---:|---:|
| Negative | 0.1585–1.0000 | 0.03886694–0.97576311 |
| Positive | 0.2598–0.8499 | 0.26997006–0.99557727 |

Both leave the measured envelope. Extrema do not supply crossing times or
duration, and interpolation inside an envelope is not automatically validated.
The separate `oregan-parameter-support.json` uses **Stanford k1** temperature
evidence; its temperature results are not transferred to this ORegan cohort.
Released-point versus fitted-function differences and the documented source
composition/geometry questions remain provenance limitations, not demonstrated
causes of the 30 failures.

Cell791 is retained. Its large temperature anomaly does not establish whether
the cause is the sensor, mounting, protocol, cell or another issue. Excluding it
would remove evidence without resolving the cause.

## 3. Independent audit of the new powertrain thermal model

The implemented per-cell equation is

`C_i dT_i/dt = i_i² R_internal,i − H(v)(T_i − T_ambient)`.

`C_i` is J/K; `H(v) = H0 + K v` is **W/K per cell**, not the research model's
area-normalized h. The units, cooling sign and midpoint update are consistent:

`T_new = T_old + dt [q_mid − H(T_old − T_ambient)] / [C + dt H/2]`.

The enforced `dt H/(2C) <= 1` keeps the homogeneous cooling amplification factor
nonnegative. It does not turn a numerical step bound into a battery safety limit.
A colder cell correctly receives ambient heat: its signed “cooling” ledger is
negative. Negative branch current still produces positive `i²R` Joule heat.

Branch harness, shared harness, motor and ESC losses are separate energy outflows
outside the cell thermal node. That separation conserves the declared electrical
energy budget. It assumes no heat returns from those components into cells and
predicts no harness/ESC/motor temperature. Adding all those losses indiscriminately
to every cell would double-count or misallocate heat; a physical correction would
require an explicit measured/declared thermal coupling network.

Independent probes, beyond the author's existing tests, give:

| Probe | Result |
|---|---|
| Exact zero-load exponential cooling, dt 0.2/0.1/0.05 s | Temperature errors 0.00355062/0.000887260/0.000221790 K; ratios 4.00178/4.00044 |
| Cold cell in warmer ambient | Exact midpoint warming reproduced; signed cooling negative; balance error 1.60e-14 J |
| Analytic two-cell circulating-current heating with simultaneous cooling | Temperature-error ratios 4.00367/4.00092; thermal residual ≤2.81e-13 J |
| Adiabatic loaded pack with deliberately large branch/shared harness losses | Cell internal heat 12.864389 J, branch heat 64.321946 J, shared heat 45.025362 J; cell storage matches only cell heat within 4.73e-13 J |
| Airspeed-dependent conductance at 12 m/s | H=0.36 W/K per cell; exact midpoint temperature reproduced |

The simultaneous-heating oracle is independent of the implemented step formula.
For two otherwise equal branches at zero bus load, SOC difference obeys
`δz(t)=δz0 exp(−λt)` with `λ = OCV_slope/(R_branch_total Q_capacity)`.
Cell heat is `A exp(−2λt)`, where
`A = R_internal [OCV_slope δz0/(2 R_branch_total)]²`.
Writing `β=H/C` gives the closed-form temperature rise above ambient:

`θ(t)=θ0 exp(−βt)+(A/C)[exp(−2λt)−exp(−βt)]/(β−2λ)`.

The chosen probe has distinct β and 2λ. It checks current sharing, Joule heat,
thermal storage, cooling and external branch heat against an analytic trajectory,
rather than merely checking a ledger assembled from the same rates.

Existing focused suite: **55 tests passed** with
`.venv/bin/pytest -q tests/test_fpv_powertrain.py`.
The independent probes all pass. No thermal equation/accounting correction is
identified within this declared synthetic model.

### What these passes do not supply

All new numerical defaults are synthetic. Constant resistance, linear SOC OCV,
thermal capacity and linear airspeed conductance are not measured FPV hardware
laws. The OCV has no temperature dependence and there is no reversible/entropy
heat; that is consistent with the chosen synthetic source but insufficient for
real battery calorimetry. Temperature does not feed back into resistance,
capacity or load. No inter-cell conduction, radiation model, tab/contact heat
return, propwash boundary, motor/ESC thermal state or hotspot is resolved.

Lumped applicability itself requires evidence. Cell geometry, thermal
conductivity/diffusivity and boundary characterization are insufficient here to
evaluate a Biot-number/spatial-gradient justification. A small discrete energy
residual alone cannot establish uniform real-cell temperature. Static propeller
coefficients also do not establish moving-flight load or power validity.

## 4. Specific evidence needed before physical qualification

1. **Separate cooling from generation.** Obtain synchronized current, voltage,
   actual near-cell ambient, multiple casing temperatures and sensor uncertainty,
   time constants and mounting. Independently measure heat capacity and heat
   generation, or characterize relaxation only where residual generation is
   bounded. Record fixture/tab/contact conductance, exposed area and actual
   airflow/propwash; establish core-to-surface transfer or a qualified spatial
   thermal model. A single fitted temperature curve cannot identify all of these.
2. **Constrain inventory and history.** Retain per-cell conditioning, charge/hold/
   rest, storage/aging history and calibrated coulomb counts. Obtain matched
   low-rate capacities, OCP/entropy laws and independent electrode-state/capacity
   constraints. Use pulse/rest evidence across relevant SOC and temperature,
   especially where transport and kinetics leave measured support.
3. **Characterize actual FPV hardware.** Measure individual branch currents,
   four-wire cell/lead/contact resistance versus SOC/temperature, pack geometry
   and cell thermal coupling. Obtain motor/ESC torque-speed-current/loss maps,
   transients and component cooling, plus propeller CT/CQ versus RPM/advance ratio
   and appropriate Reynolds conditions. Do not substitute commercial names or
   the research cells' low-C data for high-C pack measurements.
4. **Close evidence and numerical gaps before fitting.** Restore checksum-pinned
   ORegan raw records and model/heat trajectories to enable complete no-solve
   replay. Preserve existing failures. Declare the next numerical cohort plan
   and independent measurement/development/held-out split before selecting new
   parameters. A new model must be versioned and assessed alongside the frozen
   baseline; a newly inspected old trace is not a blind validation set.

The immediately actionable result is a correct evidence boundary and a
reproducible implementation audit, not an invented calibration or a passing
hardware claim.

## Reproduce the new analytical probes

The JSON contains the complete standalone oracle source and exact configurations:

```sh
.venv/bin/python -c "import json; exec(json.load(open('results/fpv-thermal-audit.json'))['reproduction']['analytical_oracle_python'])"
```

The audit JSON also fixes every inspected source by SHA256 and preserves the
research sources' attribution/license distinctions. Source measurements are by
Ferran Brosa Planella, Muhammad Sheikh and W. Dhammika Widanage
([TEC validation archive](https://doi.org/10.5281/zenodo.4864437), BSD-3-Clause), and
Kieran O'Regan, Ferran Brosa-Planella, W. Dhammika Widanage and Emma Kendrick
([parameter archive](https://doi.org/10.5281/zenodo.5171874), CC BY 4.0).
These are retained provenance references, not new source retrievals or
endorsement. Original project-code licensing remains undecided.
