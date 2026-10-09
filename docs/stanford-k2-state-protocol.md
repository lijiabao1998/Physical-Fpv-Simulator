# Frozen k2 internal-state diagnostic v1

Declared before one new grid120 diagnostic. Existing recovery run37871885149
completed both meshes; grid120 RMSE55.003054mV fails the unchanged50mV gate.
The following experiment probes the **frozen model's internal mechanisms**,
not a uniquely identified explanation of real-cell error. It is not calibration.

## Inputs and resource limits

Reuse only the original k2 workbook from persisted input artifact11590866548,
run37871885149. No new source acquisition and no k6 downloads. Verify exact
1,802,458 bytes and SHA25620ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086.
Preserve the k2 input contract, current waveform, initial state, ORegan2022/DFN
equations, lumped thermal boundary, mesh120, tolerance1e-7,5s output grid and all
native physical audits from the previous run. Unmodified core.simulate remains
the solver owner. An observer captures its actual Simulation.solve return value
without changing arguments, equations, solver options, time points or outputs.

One new scientific solve only, on free standard GitHub CPU:1200seconds total
for setup of the model, solve, internal-output export and checks;4,000,000,000
bytes per worker address space; one numerical thread. External timeout sends
TERM at1200seconds and KILL after5seconds for shutdown only. Preserve partial
results. No retry, budget escalation, parameter sweep, fitting, GUI or deployment.
Ordinary software tests use separate small synthetic/coarse model fixtures.

## Falsifiable accounting and repeatability

Export bulk positive and negative OCP, particle-concentration terms, electrode
reaction and solid-ohmic terms, electrolyte concentration and ohmic terms, and
contact term. Use the installed PyBaMM signed voltage identity, not rectified
loss magnitudes. Electrode potentials depend on the model's reference convention;
only their documented signed combination is compared with terminal voltage.
This algebra describes the model, not separately measured physical components.

At every native output time require reconstructed terminal voltage error≤1µV.
This accounting tolerance is ten times solver rtol/atol numerically but is not
a solver-error bound: it checks an algebraic identity at the same solved state.
Require each volume-average electrode stoichiometry to agree with initial c/cmax
plus/minus integrated discharge capacity divided by fixed active capacity within
1e-6 absolute stoichiometry. This assumes no side reactions or active-volume loss,
which the exporter checks. Retain existing physical audits and correct2.5V event.

Repeatability against the previous checksum-pinned grid120 native arrays must
meet maxΔV≤1mV, maxΔT≤0.01K and cutoff-capacity relative difference≤0.1%, preserving
both endpoints. These are the pre-existing diagnostic repeatability limits;
they are separate from mesh convergence and empirical acceptance. Re-score the
unchanged measured k2 window and retain all failed gates. Accounting/repeatability
failure means this diagnostic is not accepted; never tune tolerances afterward.

## Added evidence and bounded interpretations

Record electrode volume means, particle averages, x-averaged surface values and
native radial/electrode profiles. Use physical finite-volume nodes, no plotting
ghosts. Report when native surface min/max first leave the released negative
exchange-current envelope0.1585–1.0000 and positive0.2598–0.8499. Saved-time brackets
are available; continuous crossing times are not assumed exact. These sampled
envelopes are neither universal validity domains nor OCP calibration ranges.

At the fixed initial,10%,50%,90%,endpoint model times and previously established
residual sign change3152.943046s, report signed voltage contributions and inventory
states. Distinguish bulk-OCV evolution from surface/bulk gradients, reaction,
electrolyte and solid-ohmic effects. This can reject particular *model-accounting*
claims, such as a purported dominant loss that is actually small or identically
zero. It cannot independently prove which constituent law is wrong in the cell.

Record thermal state and the unchanged heating/cooling/balance traces. Crossing
25°C or35°C support boundaries is an applicability annotation, not evidence that
thermal physics caused a voltage error. Thermal causation is not isolated by this
single coupled solve; no isothermal/cooling counterfactual is included. Initial
inventory consistency is not independently measured initial SOC.

Persist input identities and this protocol before execution, then native arrays,
full exported trajectories, source attribution, supervisor/exit receipts and all
failed gates afterward. Stop after this diagnostic's result or stopping condition.
The original lost October8 execution remains unknown; this is a distinct run.
