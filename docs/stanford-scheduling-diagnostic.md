# Stanford k1 restart-scheduling diagnostic v1

Declared before the paired prefix solves. The full pilot at a8eb17134d5e70b94c8ddaaac1e31b65cf8fa0e5 exhausted its 1200-second budget inside native integration on mesh80; no curve completed and mesh120 never started. This is an execution-budget result, not an empirical or numerical validation result.

PyBaMM 26.9.0.0 documents that additional t_eval points stop and restart integration; t_interp requests output without forcing those stops. The existing full interpolant is continuous and piecewise linear. Investigate scheduling overhead without flattening, decimating or otherwise changing its 3393 supplied forcing knots.

Use the same preselected Stanford k1 source SHA256, current-profile digest, published ORegan parameters, initial state, chamber hypothesis and h=15 as the frozen full pilot. Fix mesh80, separator40, rtol=atol=1e-7, one thread, and the prefix 0–60 seconds. A uses all native current knots in that prefix as t_eval stops. B uses [0,60]. In both, request the identical union of those native knots and the five-second grid through t_interp. Thus the comparison and sampled heat audits have identical observation grids; output-density changes cannot masquerade as a scheduling effect.

Each arm has an independent 120-second wall limit and 4,000,000,000-byte address-space limit. Record setup and integration timing, available native solver statistics, peak process RSS, actual endpoint/termination, output-grid identity, forcing and parameter digests, exact analytic charge residual, lithium drift, physical-node and surface concentration bounds, electrolyte positivity and sampled heat balance. No arm may exceed its budget.

If A and B both complete with their physical audits passing and agree within 0.0001 V, 0.001 K and 1e-6 Ah on the common output grid, stop after A/B. Otherwise run one additional C arm with [0,60] and dt_max=1 second, under the same 120-second/4GB bound, retaining A/B failures. C changes only adaptive maximum step size relative to B. Maximum total worker budget is 360 seconds; no mesh120 or full discharge is part of this diagnostic.

Individual charge error must remain ≤1e-6 Ah against the exact unchanged piecewise-linear forcing integral; lithium relative drift ≤1e-6, positive finite electrolyte and bounded physical concentrations retain their existing requirements. Sampled heat residual relative to generated heat remains ≤1%. A prefix ends at its declared 60-second diagnostic horizon, not a claimed voltage cutoff. Prefix scheduling agreement does not establish full-discharge agreement, cutoff behavior, grid convergence or independent validation. Faster execution alone is not correctness. No parameters, source measurements or full-pilot empirical gates are fitted or relaxed.

Reference: https://docs.pybamm.org/en/pybamm-v26.9.0.0/source/examples/notebooks/performance/04-interpolation-points.html
