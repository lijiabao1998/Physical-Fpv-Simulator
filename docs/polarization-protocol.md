# Frozen single-case polarization diagnostic v1

Declared before the new solve. Scope: explain the already failing cell790, first 1C discharge at nominal25°C. This is an unchanged-model diagnostic, not calibration, independent validation or a new empirical acceptance gate.

## Fixed calculation

Use the committed cell790 grid120 diagnosis configuration exactly: ORegan2022 DFN, lumped thermal,5A, ambient298.15K, initial297.75K, h15W/m²/K, mesh120, tolerance1e−7,10s output samples, and the existing voltage/temperature events. The parameter fingerprint must match that diagnosis. Use the original pinned dependencies and unmodified core.simulate. One child process is limited to1200 wall seconds and4,000,000,000 bytes of address space. Timeout/resource failure means unverified, not physical divergence. No escalation, retry with larger budgets, fitting or full-cohort sweep is part of this run.

## Predeclared observables

Export each electrode's volume-weighted average and x-averaged surface stoichiometry, actual finite-volume radial/electrode profiles at initial/early/middle/late/end output times, bulk OCPs, split particle-concentration/reaction/solid-ohmic overpotentials, electrolyte concentration and ohmic terms, contact loss, terminal voltage and lumped cell temperature. Record raw PyBaMM names, units and signs. Do not use plotting ghost nodes. Distinguish particle surface from cell surface. A prescribed ambient/boundary temperature variable is not a predicted casing temperature; the experimental thermocouple remains only a surface proxy for lumped temperature.

## Accounting and repeatability checks

At every saved time, bulk positive minus negative OCP plus all signed overpotentials must reconstruct terminal voltage within1e−6V. Subtract negative-electrode and contact contributions and add positive-electrode and electrolyte contributions, following the installed PyBaMM voltage decomposition. Each directly exported electrode-average stoichiometry must match its initial concentration plus/minus discharged charge divided by Faraday constant, active volume and maximum concentration within1e−6 absolute stoichiometry. Check actual state bounds and the existing lithium/charge/heat audits.

Compare the full common time interval against the checksum-pinned previous grid120 curve, retaining both cutoff endpoints: maximum voltage difference≤0.001V, temperature difference≤0.01K, capacity relative difference≤0.001. These are repeatability checks, not replacements for any experimental or mesh-convergence target. Preserve failures if they occur; do not adjust these limits after inspecting the result.

## Stopping and interpretation

Stop after one complete solve with exported evidence and checks, or at the resource/time limit. Save input hashes, versions, parameter fingerprint, progress, outcome, full curves and endpoint summaries. Keep all30/36 empirical failures and the previous cell790 errors unchanged. The decomposition describes mechanisms inside this frozen model; dominance of one simulated loss is not proof that the same mechanism causes the real measurement mismatch. Electrode mean states are model observables, not measurements of actual cell SOC. No virtual material improvement claim follows from this diagnostic.
