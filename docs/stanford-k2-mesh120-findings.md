# K2 low-rate mesh80/120 agreement at fixed 1e-8 tolerance

The prospectively bounded mesh120 run and the saved valid mesh80 trajectory pass the unchanged mesh-pair comparison: maximum voltage difference **0.045787 mV**, temperature difference **0.00001963 K**, and endpoint-charge difference **0.00019027%**, against the original 5 mV, 0.1 K and 1% limits. Both physical audits and 2.5 V cutoff events pass. Mesh120 voltage RMSE is **19.210536 mV**, below the unchanged 50 mV gate.

This establishes agreement of this mesh pair for this fixed tolerance and previously viewed low-rate record. It does not establish a convergence order, asymptotic error bound, independent physical validation or universal parameter validity. Historical high-rate k2 remains **55.003 mV FAIL**. The original mesh80/1e-7 charge-audit failure remains preserved; no threshold or physical parameter was adjusted.

[Protocol](stanford-k2-mesh120-protocol.md), [readiness](stanford-k2-mesh120-readiness.md), [full result](benchmarks/stanford-k2-mesh120-result.json), [artifact manifest](benchmarks/stanford-k2-mesh120-artifact.json).

## Execution and provenance

Exactly one new mesh120 DFN ran in [run37960046810](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37960046810), source `5655bda1527c0941f99717018dc06553a7283dea`. Scientific execution began 2026-10-09T16:34:44.694303+00:00. The worker used 260.935665681 s and 1291496 KiB peak RSS; the shared execution took 262.534263466 s under enforced 1200 s and 4,000,000,000-byte bounds. No retry, repeated mesh80 solve or third mesh followed.

The input artifact was uploaded and verified before solving: ID11629903259, 13,903,118 bytes, SHA256 `d47fc91fdc49a1116064573d14dcf1c93945066b5784c21d332621316643d4fc`. Independent verification checked all 62 source-file hashes against both the archive and the connected GitHub execution tree, four normalized input hashes, and eight exact mesh80 reference members. The complete original reference archive was verified before selecting those members; it remains unchanged in the repository. Avoiding recursive archive copies did not alter baseline arrays or model inputs.

Python 3.12.15 and all scientific dependencies exactly match the reference. Relative tolerance is 1e-8, and all 29,643 mesh120 expanded absolute tolerances are 1e-8, with no model-level override. Physics, ORegan2022 parameters, initial state, source forcing and output queries are frozen. Only spatial dimensions changed from 80/40/80/80/80 to 120/60/120/120/120 for negative electrode, separator, positive electrode and the two particles.

## Mesh comparison and cutoff conventions

| Observable | Mesh80 | Mesh120 |
| --- | ---: | ---: |
| True 2.5 V cutoff time, s | 70344.815737543 | 70344.693547432 |
| Observed-start delivered charge, Ah | 4.885410148 | 4.885400852 |
| Maximum sampled charge-closure error, µAh | 0.611277826 | 0.724848877 |
| Measured voltage RMSE, mV | 19.210369 | 19.210536 |
| Maximum measured voltage error, mV | 47.252734 | 47.250350 |
| Capacity error, % | 0.0356669 | 0.0358571 |
| Energy error, % | 0.0958819 | 0.0960647 |
| Observed time coverage, % | 99.9643279 | 99.9641543 |
| Physical audit / valid cutoff | PASS / yes | PASS / yes |

The original mesh criterion uses the union of saved times over common support, including its earlier true endpoint, with linear interpolation. Here this gives 70,355 comparison points through 70344.69354743241 s. The separate exact-query diagnostic uses 70,354 shared timestamps through 70344 s; its maximum voltage and temperature differences are identical in this case. Both conventions and true endpoints remain explicit.

Maximum |ΔV| is 4.5787162231025746e-5 V at 70343 s. Maximum |ΔT| is 1.9628564075446775e-5 K at 56978 s. Relative endpoint-charge difference is 1.9026535717476491e-6, normalized by the mesh120 observed-start charge. Mesh120 reaches cutoff 0.122190110 s earlier. There is no endpoint extrapolation or cropping of delivered charge to manufacture agreement.

## Independent charge and physical checks

The finer mesh's sampled capacity error is slightly larger than mesh80's, despite both passing the unchanged 1 µAh limit. Spatial refinement is not assumed to monotonically reduce this solver-state diagnostic. The independent rational integral gives mesh120 signed minimum −0.724848919 µAh at 63614 s, maximum +0.016779967 µAh at 364 s, and cutoff error −0.550438772 µAh. No prescribed sample violates the gate. These extrema cover the saved grid and true endpoint; unobserved continuous-time extrema are not established.

The analytic source integral agrees with the exact rational imposed-current integral to 4.53e-14 Ah. The compiled current agrees at all 137,313 source/query points; the capacity RHS agrees with I/3600 to 1.36e-20 Ah/s. All 21 native endpoint observables were reconstructed for each mesh, 42 checks in total, without solving again.

Mesh120 relative lithium drift is 2.827994105e-14. Electrolyte minimum is 982.440913 mol/m3; electrode bounds, positive heat capacity and finite spatial witnesses pass. Thermal-energy residual/generated heat is 7.380094246e-7. Original electrical and temperature-proxy gates pass together with the mesh-pair gate; the acceptance conjunction was not weakened.

## Physical scope and next saved-data question

The temperature proxy gives 0.667030 K RMSE and 0.977247 K maximum error. Predicted bulk temperature spans 24.345535–25.410893 C, while the surface measurement spans 24.191589–25.158491 C. Part of both trajectories remains below the 25 C lower support of the cited heat-capacity measurements. Skin-to-bulk comparison is not independent thermal validation. Missing prior history and the initial skin-temperature proxy are unchanged assumptions, and this record was already viewed during development. The ordinary core current domain is not expanded by this separate experimental low-rate driver.

The next useful step is the originally motivated, zero-new-solve comparison of this numerically checked low-rate trajectory with the saved historical high-rate trajectory at predeclared discharged-Ah queries. Numerical mesh sensitivity can be reported alongside that conditional rate-gap discrepancy; it is not a rigorous uncertainty bound. Equal discharged Ah does not establish equal absolute SOC, initial inventory, temperature or prior history, so that comparison must not uniquely attribute the high-rate failure to kinetics, diffusion or resistance. No such new analysis or simulation was automatically launched by this protocol.

## Durable reproduction

The full 22,462,499-byte GitHub evidence archive is preserved byte-for-byte in three ordered repository parts, SHA256 `a3b737252dd5893c4d2039ca9b049a4818b091cf5d771aa261a356f52cb66e2e`. It contains all 86 members: complete prepared scientific inputs and source copies, eight pinned reference members, both provenance chains, the one-stage ledger, effective-tolerance receipt, native final state, scalar arrays and reports.

Run `python scripts/verify_stanford_k2_mesh120_evidence.py` to reassemble and verify the archive, repeat baseline/fine endpoint, physical, empirical and mesh comparisons, and require agreement with both the archived and committed reports. It performs no battery solve or source download. The original ledger's pre-comparison status string is preserved; the separate comparison and terminal workflow establish completion.

Independent result review reproduced the archived-byte chain, its own rational-charge integration and physical/empirical arithmetic, and all 42 native endpoint checks. The final local suite passed 694 tests with 7 skips and 6 existing warnings in 128.74 s; lint and formatting passed across 148 Python files. The source launch commit's ordinary Battery CI separately encountered HTTP504 before tests; that upstream failure is preserved, and this results publication receives its own ordinary CI verification.
