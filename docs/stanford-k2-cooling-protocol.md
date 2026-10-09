# Frozen k2 cooling characterization screen

Protocol frozen on 2026-10-09 before fitting, including an independent-review correction to use original
source knots at the calibration/check split. This is retrospective characterization
of an already viewed cell, not blind validation. A preliminary check viewed the
start, quarter, midpoint and final skin temperatures of rests 1, 4 and 6. Those
checks motivated the question; the independent reviewer also previewed fixed-window
temperature summaries through the full tail before the protocol was finalized.
No fitted result or alternative fitting window was tried. Later check data are
withheld from fitting, not unseen by the analysts.

Question: can one positive exponential decay rate predict the later zero-current
skin-temperature record from an early calibration interval? The nominal 25°C
chamber label and measured resting skin are different observables. Neither is a
measured ambient time series.

Use only the immutable archived k2 rows in
`benchmarks/stanford-k2-rest-records.csv.gz`, SHA256
`513ad1debdf3fcf7eb9d716a8b34651a39349f136d1a6b23e84ed609fa2c2d6f`,
previously checked row-for-row against workbook SHA256
`20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086`.
Require strictly increasing clocks and exactly zero recorded rest current.
No download, new electrochemical solve or physical parameter update is permitted
by this screen.

## Predeclared model, calibration and checks

For post-discharge rest step time t, use
T(t) = B + [T(60 s) - B] exp[-(t-60 s)/tau].
The amplitude is fixed by linear interpolation of measured skin at 60 s.
Estimate tau only from60 s through the last original source knot at or before600 s
(required in[599,600] s) by time-weighted least squares in temperature
space. Search a fixed 10–10000 s interval (numerical search bounds, not a prior
uncertainty interval): 65 log-spaced candidates and 80 golden-section refinements
around the best interior candidate. Boundary optima are flagged, not extrapolated.
No fitting of ambient, amplitude, offset, heat source or multiple exponential terms.

Keep both scenarios without selecting one as truth:

1. B = 25°C, the nominal chamber label.
2. B = time-weighted mean of the pre-discharge rest's final 600 s, a skin-based
   baseline proxy available before discharge, not a measured ambient value.

Report the calibration result, then forward-predict two disjoint checks:
first original source knot at or after600 s through1800 s, and1800–3600 s.
Report the sub-sample gap between calibration and checking; never interpolate
the calibration endpoint using a later observation. The effective intervals,
not the nominal600 s label, determine coverage.
Never re-anchor or refit on check data. These are temporal withheld fitting windows
within a previously inspected trace, not independent-cell validation.

Compare each fit with (a) persistence at T(60), and (b) a constant-heat-capacity,
zero-heat-source exponential using the existing Stanford h=15 W/m²/K prior,
ORegan2022 cooling area and effective heat capacity evaluated at 298.15 K.
This prior comparison is an analytic approximation, not a replay of the coupled
DFN or its temperature-dependent heat capacity.

Report time-weighted RMSE, maximum absolute error, mean error and valid coverage.
Integrate smooth exponential versus piecewise-linear source temperature with
8-point Gauss quadrature per source interval; independently verify using32 points
(maximum integral difference target1e-10 K²). Check endpoint and within-segment
stationary residuals for maximum error. Report existing thermal-proxy 2 K RMSE/
5 K maximum gates separately from scientific validation status; these inherited
broad gates do not establish measurement uncertainty or an acceptable cooling fit.
A candidate is eligible for *further study* only if it reduces RMSE against both
comparators in both check windows and has an interior optimum. This relative
screen is not a new physical acceptance gate or authorization to change the DFN.
Report all scenarios even if they fail.

## Identifiability and stopping condition

Only an effective skin decay time is estimated. Zero terminal current does not
eliminate internal relaxation heat or core-to-skin redistribution. Ambient drift,
fixture conduction, thermocouple offset/lag and internal gradients are unresolved.
Neither h nor heat capacity nor an intrinsic h/C is identified. No conversion of
tau into a measured convection coefficient, no voltage-error attribution and no
manufacturing improvement claim is allowed. A fitted scalar cannot resolve these
confounders. The later tail may refute the fixed-asymptote predictor descriptively;
without calibrated uncertainty this is not a statistical rejection of a unique
physical mechanism.

Budget: one cached-data analysis process, 60 s and 1 GB; deterministic fitting,
no adaptive experiment loops. Save input/protocol/code hashes, all parameters,
calibration/check metrics and the full prediction CSV plus readable SVG. Stop after
independent review, regression tests, publication and CI. Propose a distinct next
experiment only from these results.

## Scientific grounding

The [PyBaMM thermal-model equations](https://docs.pybamm.org/en/v26.6.0.0/source/examples/notebooks/models/thermal-models.html)
show that lumped temperature depends on heat generation, thermal capacity and
boundary heat transfer together. A surface thermocouple is not automatically the
volume average used in that equation. [Lu et al. (2020)](https://www.nature.com/articles/s41467-020-15811-x)
connect manufactured electrode microstructure, porosity and tortuosity to transport
and performance using measured microstructure. Our existing commercial-cell model
has no manufacturing-process measurements, so this screen addresses test-fixture
characterization, not simulation or optimization of cell manufacture.

Data and derived records: Catenaro and Onori,
[10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), CC BY4.0.
