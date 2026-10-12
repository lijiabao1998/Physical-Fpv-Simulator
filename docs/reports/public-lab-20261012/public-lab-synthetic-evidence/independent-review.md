# Independent review: finite synthetic battery envelope

Review verdict: PASS for the bounded synthetic implementation and its recorded numerical verification. Physical parameter identification and unseen measured validation remain NOT_ESTABLISHED. The earlier M3 candidate remains NOT_FIT_READY / NOT_IDENTIFIED.

Reviewed 2026-10-12 UTC on `study/public-lab-synthetic-envelope-20261012`, against baseline `ee5ca8ada4542cb3ad985ba07971b9fe02b42cf5`. This review accepts a conditional engineering deliverable. It does not accept a new physical calibration, reconstructed real history, battery operating envelope, or flight/thrust error bound.

I inspected the frozen protocol and source before the primary solve, raised specific defects, and reviewed the resulting source, receipts, raw verification output, case metadata, final report and plot. I ran no simulation, optimizer, numerical battery test, GUI operation, or public-data retrieval. My independent checks were file hashes and saved-result metadata comparisons. This file is my only workspace edit.

## Frozen design and provenance

The protocol, scenario manifest and four oracle cases were committed as `28ce7e2483da6033a009945b6c63bf2f194c57f8` at 02:40:50 UTC, before the first numerical check at 02:49:55 UTC and the primary solve at 03:01:12 UTC. The manifest contains two references, all 25 non-baseline one-factor variations, and 64 PCG64 rows with seed 20261012. Every non-baseline axis value is represented in the controls. Seeded inputs are generated in the declared axis order, with no replacement of invalid or duplicate rows.

The inherited Q, R0, fast R/tau, C/H and nine effective potential values have source provenance from the earlier cell02 calibration. They are legacy assumptions, not independently qualified physical constants. The new 13-node potential is interpolation of those nine values plus a prelisted stress term; no new node is fitted.

Charge anchors, initial polarization, slow R/tau, potential stress, gap input and thermal variations are illustrative engineering priors. Previously observed voltage/temperature scales and R4 fixed-tau probes do not turn these choices into measured parameter bounds or a probability distribution. In particular:

- The gap durations 2640/2760 seconds reuse conditional wall-display arithmetic. A synthetic gap followed by 7200 seconds of rest is not the actual SBr chronology or restoration of missing current, elapsed time or temperature.
- The usable-charge coordinate and unit charge efficiency are model assumptions, not identified electrode inventory or charge/CV efficiency. States propagate through all phases without resetting the coordinate to one.
- The initial RC energy limit `0.1*3600*Q*4.25 J` is an arbitrary prior applied at the anchor only. It is neither a conservation law nor a measured or all-time cap.
- The continuous 4.25 V upper guard is a model prior, not a certified safety rating. Invalid initial states are rejected before a later relaxation could conceal their violation.

The primary path reads the old parameter file and hashes the raw training file; it contains no measured-voltage objective, parameter optimizer, old-eight-curve selection, or new data acquisition. Zero fit and coefficient-update counters agree with that code path.

## Physical and event consistency

The constant-current solution has the correct signed charge evolution and passive RC response. For each enabled branch, capacitance is `tau/R`, stored energy is `tau*p^2/(2R)`, and its derivative is `I*p-p^2/R`. Irreversible heat is `I^2*R0 + sum(p^2/R)`. Thus terminal loss power equals resistor dissipation plus the change in stored RC energy; polarization work is not incorrectly counted entirely as heat. A disabled zero-R slow branch requires zero state and is omitted from division and energy accounting.

The exact thermal convolution uses that dissipation and constant ambient, including the equal-pole limit. Temperature-independent potential and zero reversible heat are explicit synthetic simplifications. Adding a slow branch to the inherited effective potential may double-count previously absorbed loss. These equations do not establish the actual cell's entropy term, temperature-dependent resistance, heat transfer, or material behavior.

Within each linear-potential interval, voltage derivative is a constant plus up to two exponentials. The implementation partitions its derivative at the at-most-one extremum, isolates stationary roots, then searches voltage in chronological monotonic pieces. Potential-knot crossings and initial values are included. This supports the first cutoff through a dip and recovery rather than relying on interval endpoints. A current jump that immediately puts voltage below the threshold correctly stops at time zero.

The charge-domain endpoint is not repaired by clipping charge or changing Q. A one-ulp negative result from endpoint arithmetic is handled by moving only the endpoint time toward zero with `nextafter`. A domain end above 2.5 V remains a named outcome with null physical-cutoff time. This rounding treatment does not repair the legacy low-current cutoff failure.

## Recorded numerical verification

The completed focused run records 17 passes in 1.14 seconds of pytest time / 1.625 seconds of harness time. After the preparation-temperature reporting change, its targeted check records one pass in 2.17 / 3.937 seconds. The final source snapshot records all 18 tests passing at 03:11:21.695705-03:11:24.556355 UTC, 1.94 / 2.859 seconds. I inspected its receipt and raw pass list. The final test source equals the retained executed-source snapshot.

The four predeclared full-history oracle cases use independent DOP853 state integration and voltage interpolation, including a signed negative gap input and positive initial stored polarization. Independent event detection compares the first downward threshold time. Recorded maxima are:

| Quantity | Recorded maximum absolute error |
| --- | ---: |
| Voltage | 8.544276397515205e-13 V |
| Temperature | 1.2505552149377763e-12 K |
| First cutoff time | 4.2895135266007856e-7 s |

All are below the frozen tolerances. The deliberately nonmonotonic control starts at 2.546388 V and ends at 2.565121 V, yet dips below 2.5 V; its first crossing is 5.652682303 seconds, with independent ODE error about 9.20e-8 seconds. This directly exercises the endpoint-only search trap. The passive RC and thermal energy checks record relative residuals 4.03e-13 and 1.47e-12. Other checks cover legacy zero-memory equivalence, equal thermal poles, signed charge continuity, current-jump cutoff, disabled-branch state, initial-energy, charge-domain and upper-voltage rejection.

These are errors between implementations of assumed equations. They are not measured prediction errors or empirical uncertainty coverage.

The initial combined check also invoked expensive archived-evidence replays and was interrupted after 322.094 seconds with exit 4294967295. Its stdout is partial; it is not a completed 27-pass run. That scope/control mistake, the incomplete run and early lint failures remain recorded. The focused and final complete runs provide the accepted new-model verification.

The primary receipt records one CPU, IDLE priority, single-thread settings, a 1800-second cap, no timeout, exit zero and 12.0 seconds of harness time. The driver records 11.688 seconds. The retained lease wrapper serializes the task's own FPV jobs. Its Lean/Lake observer records no initial matching process and no pause; this is observed-process evidence, not proof that the host had no other workload. I did not run another numerical job.

## Complete case accounting and thermal reporting

I independently compared every saved `(scenario_id,current)` pair with the frozen manifest: all 364 pairs are present in the original order, with zero sequence differences. Each of the four currents has 91 inputs, 56 numerically admissible outcomes and 35 invalid preparation inputs. Overall:

| Outcome | Count |
| --- | ---: |
| Model 2.5 V cutoff | 195 |
| Charge-domain end without physical cutoff | 29 |
| Invalid charge domain | 8 |
| Invalid history upper-voltage prior | 60 |
| Invalid initial RC energy prior | 72 |
| Total | 364 |

The 224 numeric outcomes and 140 invalid inputs are all retained. Feasible-range summaries exclude invalid profile truncations while retaining their statuses and traces if they occur; none occurs in this manifest. Domain-end values are explicitly separated from physical-cutoff times. All 936456 trace rows have the declared gap/rest/main phase schema and phase-current field; trace time is relative to each phase. I verified the compressed-file digest, not every trace row through a second numerical replay.

The initial draft had three reporting/verification defects: its event comparison shared the analytic voltage function, it omitted preparation traces, and numeric ranges could include invalid partial profiles. These were corrected before the primary run. A subsequent static review found that the extrapolation flag inspected only the main phase. Collection was corrected before the primary run to retain main, history and all-phase sampled peaks and flag any-phase exceedance; its targeted and final checks passed.

I checked all 224 numeric case records: the all-phase peak equals the maximum of main/history peaks and every extrapolation flag agrees with that peak, with zero mismatches. In `seeded_011`, the preparation peak is 55.029752 C even when later cooling reduces discharge temperature. At 5 A this case reaches 117.928598 C at the model stop and remains flagged. This exposes extrapolation under the assumed equations and priors; it is not a credible or safe operating bound. The model omits temperature-dependent parameters, phase changes and aging needed to qualify such a temperature.

Peak temperature is sampled at five seconds plus voltage partitions and endpoints. A certified continuous peak has not been established. The finite ranges cover only the saved design; they are neither guaranteed bounds on the full prior box nor confidence intervals. No best parameter set is selected, and rejection frequencies are not probabilities.

## Preservation, hashes and disposition

I inspected the baseline-integrity helper and its successful 10.297-second receipt. It reads all baseline Git blobs and compares file SHA256 values without numerical curve replay. Its saved result reports all 840 tracked baseline files byte-identical. This proof covers the Git baseline; it does not itself rehash separate task-root delivery directories. I did not repeat the full baseline audit.

I independently hashed the frozen inputs, current model/driver, retained executed sources, results and compressed trace. The model and driver match both their primary result digests and retained exact source snapshots. Reviewed SHA256 pins:

| Artifact | SHA256 |
| --- | --- |
| Protocol | `5012c44c5653f54eff96ac4a4fb917d7326227e721eb7b18789632c84e5e231c` |
| Scenario manifest | `86d5164106d58dc7700c5d008cf04f5c145125f949496b1ce3592b90e340c968` |
| Oracle cases | `d38076b7bf5c79ef63f7cbf2fccf11947fac7ede5d6e8b00b18a1f316e7d9789` |
| Primary model | `d1b834f0b8cb10fef30e267fe8a9a4dd3a68595edc2dac2bfa1619c3351d6262` |
| Primary driver | `ce021c58f55d588f808259d7f8cf8ad3b22cca3e7d31285f6af71265b9e0dc32` |
| Final test source | `8ec01694a40d416678356ade2996e76d973785c26a4c86145552f2180ab31741` |
| Primary results | `d4438ed36554f1fa4fd12e315ea5f540ce52ae48e2b3b335e5b54cf4f622a5c3` |
| Compressed traces | `3b769ec2b611541768cb1e50dca3764ba3ac9de13a91b0f1abb1eabc5b6d9a5d` |
| Baseline integrity result | `701e0edc45eb1bdaef6efa46e575e7581b2024c246da95433f72d335511a93ce` |
| Numerical verification | `aa1adb6914b249b7c58e596c6514f0b18eac705bb938eb8590d567856a514114` |

The final scientific report distinguishes conditional numerical accuracy from the archived measured results. The old eight curves remain known regression, with 6/8 passing, two low-current cutoff failures and aggregate scientific FAIL. Earlier ORegan/Chen/Stanford records and the original GUI Win10053 evidence remain preserved. HTTP lifecycle work is a separate engineering deliverable and supplies no battery-validation evidence.

There is no remaining implementation or presentation blocker for sealing this finite synthetic study. The plot footer initially overlapped its x-axis labels. A plot-only regeneration from saved results reserved a separate footer margin; I viewed the corrected image and confirmed legible, separated labels and unchanged range interpretation. No physics solve was repeated, and cosmetic figure bytes are not part of the primary hash pins above. The main report also clarifies that the 840-file proof covers tracked files and does not claim a new rehash of separate task-root packages.

Actual missing history, inventory/efficiency, slow-state parameters, temperature/reversible-heat laws and physical uniqueness remain unresolved. There is no newly unseen measured validation set and no justified new motor/ESC/propeller/thrust, dynamic-pack or flight-endurance error bound. The appropriate next step for this round is to seal the existing source, evidence and review, with no additional fit, scenario selection, public-data search or primary rerun.
