# k2 rest/charge compatibility screen, frozen saved-data recipe

This is a post-hoc, zero-new-source-data comparison of additional observable
types in the original k2 workbook. Its six phases and some endpoint values were
already inspected. It is not blinded validation. No new dynamic solve is
authorized by this protocol; no SOC, capacity, OCP, resistance or transport
parameter is fitted. The existing50mV discharge-RMSE gate remains unchanged.

## Fixed source and observable selection

Use every original row of the SHA25620ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086
workbook NMC_k2_1C_25degC.xlsx,1,802,458bytes. Record all six original phases:
initial rest, CC charge, CV charge, pre-discharge rest, discharge, final rest.
Preserve source Excel row numbers, naive dates, test/step clocks, voltage,
signed current and skin temperature. No cleaning, thinning, alignment or
extrapolated equilibrium voltage is allowed.

For each rest report first/last voltage and temperature, actual duration,
all recorded current extrema, and voltage/temperature change over the final
600seconds using the first actual sample at or after that boundary. Do not
fit a slope/asymptote or call flat voltage proof of equilibrium. Missing sensor
uncertainty and internal temperature are explicit, not silently assigned zero.
Report a second, separately named endpoint-minus-interpolated-value exactly600s
earlier to expose sensitivity to one sample of window placement; never choose
whichever drift better supports a hypothesis.

## Charge-accounting conventions, not fitted uncertainty bounds

Compute the charge between rested reference points three ways:

A. Sum trapezoids strictly within recorded CC/CV or discharge phases. Exclude
unobserved first intervals and interphase gaps.

B. Integrate piecewise-linear signed current across every adjacent sample from
the last initial-rest sample to the last pre-discharge-rest sample, and from
the last pre-discharge-rest sample to the last final-rest sample. Bridging
unobserved switching intervals is an explicit interpolation assumption.

C. Hold the previous phase's last current until the next inferred commanded
origin (Test_Time−Step_Time), then hold the next first current until its first
sample; use the unchanged sample trapezoids within phases. Report every gap and
added Ah. This is another declared switching assumption, not observed current.

Also retain the exact existing k2 discharge convention: observed discharge Ah
plus the already declared0–1.0003s first-current extension, with no added late
measurement. Do not optimize a convention to reduce voltage discrepancy.
Check only numerical bookkeeping at1e−12Ah; these alternatives are not rigorous
experimental uncertainty bounds.

## Fixed inventory/OCP predictions

Anchor the model at its published pre-discharge initial concentrations,
x_n0=28866/29583 and x_p0=13975/51765. Use the saved fixed active capacities,
negative5.203221458293159Ah and positive7.163230036439915Ah, independently checked
from Faraday constant, active fraction, geometry and maximum concentration.

For charge q removed from this published state, compute hypothetical uniform
means x_n=x_n0−q/Q_n and x_p=x_p0+q/Q_p. Backward through measured charging uses
the same formula with q equal to the charge supplied since initial rest.
Reject any state outside0<x<1. No inverse OCV→SOC step is permitted.

Evaluate the unchanged installed ORegan OCP functions at each measured rest-end
skin temperature (explicit uniform-temperature proxy) and separately at298.15K.
Compare with all three rest-end terminal voltages. These are static hypothetical
uniform-state potentials, not solved rest trajectories. Record function hashes,
charge-convention sensitivity, last-window drift and all applicability limits.
Constituent evaluation and geometry accounting tolerance1e−6 is computational
only; it is not a fabricated measurement-error or empirical acceptance bound.
Backward charge accounting assumes100% external-current-to-intercalation
efficiency, no side reactions, unchanged active material and conserved lithium
inventory. Those are frozen model assumptions, not findings from the workbook.
Unknown prior history and hysteresis remain explicit. Mark related kinetic
support-envelope exits and unqualified OCP transferability separately; a kinetic
sampling envelope is not an OCP validity interval.

## Hypotheses and what can actually be falsified

H_joint: published initial inventory, fixed active capacities, transferred
hysteresis-free OCPs and the approximation 'rest endpoint equals uniform-state
OCV at skin temperature' are jointly compatible with the observed charge/rest
history. Nonzero residuals quantify this joint incompatibility. Physical
falsification would additionally require bounds on residual relaxation,
thermal gradients, hysteresis and instrumentation. None is invented here.

H_loaded_only: all model-measurement discrepancy is confined to under-load
polarization, while the above rest/inventory/OCP approximation is correct.
Then zero-current rest anchors must also be compatible. Large rest discrepancies
surviving the declared charge conventions contradict that *combined approximation*;
they do not uniquely separate inventory, OCP, finite-rest dynamics or measurement.

H_constant_offset_only: a single constant voltage offset exactly explains all
three rested discrepancies. Unequal discrepancies reject this exact arithmetic
claim; no offset is estimated or applied, and no statistical claim follows
without instrumental uncertainty.

The screen cannot separately falsify 'inventory wrong' versus 'OCP law wrong':
terminal voltage is a difference of two electrode potentials, and charge only
constrains changes of inventory under assumed active capacities. Do not solve
for hidden electrode states using the same terminal voltages and relabel the
fit as independent evidence.

## New-solve decision, to be reviewed separately

If the existing rest data establish a compatible joint anchor, a future frozen
relaxation/loaded comparison could test dynamics at matched transferred charge.
If rest equality is unresolved or inconsistent, another decomposition of the
same discharge cannot independently discriminate initial inventory from OCP.
Do not launch an arbitrary rest-only solve from a fabricated state, extend past
the model's voltage event, or replay charging from an unqualified initial SOC.

The concrete missing constraints, if needed after this screen, are a rested
OCV-versus-passed-charge reference with quantified finite-rest/temperature and
sensor uncertainty, plus independent electrode/inventory or active-capacity
information to separate electrode OCP transfer from inventory. Requesting or
acquiring those measurements is outside this saved-data screen.

Deliver the actual source-backed table, charge ledger, reproducible script and
tests, and a scientific go/no-go recommendation for any next simulation.
