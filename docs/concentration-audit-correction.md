# Concentration audit correction (2026-10-07)

During the ORegan2022 extension, a false-negative physical audit was diagnosed. Calling a spatial PyBaMM ProcessedVariable with only time uses plotting-oriented extrapolated ghost coordinates: a20×20 particle grid returned22×22 samples. At strong concentration gradients, those outside-domain points can be negative even when all actual finite-volume nodes and surface states remain physical.

A reproduced20-point ORegan2022 /25°C /1C example had minimum actual negative-particle node concentration1291 mol/m³ and actual surface concentration1110 mol/m³, while the plotting extrapolation returned−8524 mol/m³ outside the physical domain.

The audit now checks raw finite-volume entries and separate surface-state entries, at all retained output times. It also checks electrolyte entries without plotting extrapolation, and records node shape and node/surface extrema. Thresholds are unchanged; no negative physical state is permitted. A regression test explicitly demonstrates the ghost false negative and verifies the corrected physical audit.

The initial thermal exploratory run's concentration pass/fail flags must not be interpreted as material/model failures. Its voltage/temperature/capacity curves were unaffected. Final thermal reports are regenerated from the corrected implementation. Historical Chen reports are retained; their experimental outcomes are unchanged. A fresh Chen regression is required after this implementation fix.
