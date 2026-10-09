# Evidence-gated roadmap

1. **Single-cell electrochemical baseline (implemented):** reproducible Chen2020 benchmark, unchanged parameters, numerical convergence, all discrepancies retained. Acceptance is separate from a program running successfully.
2. **Thermal-electrochemical baseline:** qualify ORegan2022 input provenance and raw multi-temperature validation; fix initial states and split before optimization; compare voltage, delivered energy, capacity and measured surface temperature; document volume/surface-temperature mismatch and identifiable cooling assumptions.
3. **Electrode research:** parameter sensitivity with dimensional constraints, uncertainty propagation, identifiability and repeat-cell variability. Calibration uses a designated development partition; independent verification must come from new cells/studies. Do not modify microscopic density as though it were effective electrode density.
4. **Atomic/molecular methods:** controlled small DFT/NEB or MD reference calculations using qualified potentials, convergence studies and cited input structures; retain method/version/structure hashes and uncertainty. Validate equilibrium structures and known migration barriers before exporting transport estimates. A simple analytical jump-network method test is available now, but ab-initio calculation is not yet implemented.
5. **Multiscale mapping:** distinguish tracer versus chemical diffusion, thermodynamic/correlation factors, defect populations, orientation, porosity, tortuosity and composite-electrode transport. No unsupported automatic links from atomic coordinates to capacity or conductivity.
6. **Pack and FPV integration:** conservation across series/parallel cells, harness resistance and cooling; then measured pulse-load profiles, transient voltages and cell variability; only then coupled flight-load evaluation. Do not extrapolate a 1.5C single-cell benchmark to racing-drone loads.

Every stage needs a reproducible executable example, tests, data/parameter provenance, declared range, uncertainty and failed-case behavior. Expensive compute, new accounts/credentials, paid services and physical equipment require separate authorization. First software work stays CPU-bounded and uses no physical battery experiments.

Implemented reproducibility tooling: the [offline replay verifier](offline-replay-verification.md) checks saved inputs, output integrity and selected scientific metrics independently of a solver run. Known empirical failures remain explicit.

Implemented characterization: the [k2 cooling screen](stanford-k2-cooling-findings.md)
fits only an effective skin decay on an early rest window, checks later windows,
and separates improved observable prediction from unidentified physical parameters.

The [fixed-rate k1 transfer check](stanford-cooling-transfer-findings.md) preserves
a negative result: the k2 cooling improvement does not generalize across all
predeclared k1 windows, so no universal thermal-prior replacement is adopted.

The [shared series-like voltage-term screen](stanford-series-loss-findings.md)
finds disjoint50 mV feasible sets for archived k1/k2 trajectories. No resistor
is selected and no physical correction is promoted from the algebraic screen.

### Conditional k2 low-rate reference (2026-10-09)

The [frozen low-rate comparison](stanford-k2-low-rate-findings.md) adds a separately
measured 0.05C waveform to the saved 1C evidence. It constrains voltage differences
on a conditional discharged-Ah alignment; temperature and inventory equivalence
are unestablished. No parameters were fitted or promoted. The 50 mV terminal gate
continues to fail. Next discriminating work should constrain initial inventory and
thermal comparability before attributing the between-record gap to kinetics.

### Near-start rest-referenced response (2026-10-09)

The [cached onset comparison](stanford-k2-onset-findings.md) shows that the model’s
−5.792 mV initial bulk-OCV/rest-endpoint offset cannot algebraically reconcile
the +60–70 mV early terminal residual. Finite-time observed voltage fall/current
is reported without identifying ohmic resistance. Timing/latency and internal
state constraints remain necessary before assigning a unique physical cause.

### k1/k2 near-start transfer (2026-10-09)

The [fixed-query transfer](stanford-onset-transfer-findings.md) locates the
~150 mV early residual contrast mainly in the measured loaded-fall contrast
(~148 mV), with only a −0.304 mV rest-anchor contrast. This is an observed
between-record constraint, not an identified resistance or latent-state cause.

### Two-rate early-response scaling (2026-10-09)

The [frozen cross-rate screen](stanford-cross-rate-onset-findings.md) predicts
the low-rate specimen contrast from the prior 1C response with discrepancies
−0.042/+0.212/+0.010/−0.117 mV at fixed nominal queries. It supports a
current-proportional descriptor, with no identified contact resistance or physical
PASS and no change to the model or its empirical gates.

### Persistence of the frozen specimen contrast (2026-10-09)

The [later-window development test](stanford-contrast-persistence-findings.md)
uses the frozen low-rate onset descriptors to predict the 1C specimen contrast
over 10–3333 s, with maximum discrepancy 8.252 mV. Large individual errors cancel;
this is no single-cell model repair. Full low-rate capacity/voltage-shape
compatibility is the next cached-data discriminant before assuming common SOC.

### Full measured rate-shape characterization (2026-10-09)

The [four-record characterization](stanford-full-rate-shape-findings.md) retains
complete observed charge and cutoff evidence. Frozen onset offsets reduce the
specimen contrast while similar 64.8–125.2 mV measured low/high-rate gaps remain.
These are measured rate differences, not model errors or identified physics.
A frozen model rate-response comparison is the next discriminant requiring its
own bounded protocol; common-Ah state and thermal/history equivalence remain open.

### Experimental low-rate model comparison: implementation only (2026-10-09)

The [frozen proposal](stanford-k2-low-rate-model-protocol.md) and separate low-rate
driver reuse the pinned complete k2 record with unchanged physical parameters.
Scalar-output storage preserves sampled spatial/energy audits within a hard
4 GB worker cap. A shared 1200-second budget covers at most two sequential mesh
solves, with durable inputs required first. The workflow is an inert review
template outside the executable workflow directory. No scientific execution or
low-rate validation is claimed by this implementation. Independent review accepted
the bounded approach; explicit launch coordination remains required. The ordinary
core current domain stays unchanged.

The first managed attempt subsequently stopped before either solve because its
immediate uploaded-artifact metadata lookup returned HTTP404. The preserved
receipt and bounded visibility-check amendment are linked from the protocol.
A separately reviewed replacement retains the original scientific limits;
no low-rate trajectory or empirical improvement has yet been established.
