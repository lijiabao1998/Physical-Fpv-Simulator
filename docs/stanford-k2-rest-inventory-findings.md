# Three rest anchors challenge the joint inventory/OCP approximation

**The available data constrain more than loaded polarization.** An audit of all
27826 original k2 rows, with no new solve, fit or source acquisition, compares
the measured charge history and three finite-rest voltages with the frozen
published-inventory/OCP mapping. Substantial discrepancies persist at zero
recorded current. They challenge the combined approximation; they do not identify
a unique wrong parameter or establish equilibrium voltage statistically.

The original discharge result remains55.003054mV, failing the unchanged50mV gate.

## Fixed, uncalibrated comparison

Published pre-discharge concentrations anchor the mean electrode states. Fixed
active capacities are5.203221458Ah negative and7.163230036Ah positive, checked
arithmetically from published geometry, active fractions and Faraday constant.
They are **not independently measured capacities for this specimen**.

The existing discharge convention adds its declared unmeasured initial interval
of0.001389412Ah. Charging in this primary table uses recorded CC/CV intervals
only, totaling4.897586415Ah. No SOC was inferred from voltage.

| Rest endpoint | Measured finite-rest voltage | Hypothetical uniform OCV at endpoint skin T | Static minus measured |
|---|---:|---:|---:|
| Initial rest, before charging | 2.956931V | 2.612558V | −344.372mV |
| Pre-discharge rest | 4.186752V | 4.180960V | −5.792mV |
| Final rest, after discharge | 3.019789V | 2.941418V | −78.371mV |

The first row is **backward charge accounting**, not a backward simulation:
subtract charge supplied since initial rest from the anchored negative inventory,
and add it to the positive inventory. This assumes100% intercalation coulombic
efficiency, no side reactions/lithium loss, fixed active volumes and unchanged
capacity. Unknown prior history and hysteresis are unresolved. The hypothetical
initial-rest means are x_n=0.034503,x_p=0.953682; final-rest values are
x_n=0.058589,x_p=0.936186. These lie inside mathematical0–1 bounds but outside
related exchange-current sampled envelopes. **Those kinetic envelopes are not
OCP validity limits.** OCP transferability at these states remains unqualified.

## Unobserved switching intervals do not get hidden

All three specified conventions are reported, without selecting one for agreement:

| Convention | Charge supplied | Charge removed | Initial-rest OCV discrepancy | Final-rest discrepancy |
|---|---:|---:|---:|---:|
| Recorded within-phase intervals only | 4.897586Ah | 4.770869Ah | −344.372mV | −76.092mV |
| Linear bridging of every sample gap | 4.898331Ah | 4.772388Ah | −347.339mV | −78.584mV |
| Previous-current hold to command origin, then first-current hold | 4.898540Ah | 4.772454Ah | −348.177mV | −78.692mV |

These are deterministic assumption scenarios, **not experimental uncertainty
bounds**. The script retains each gap, inferred command origin and added Ah.
The previously frozen discharge convention gives the primary−78.371mV value.
The discrepancies survive these particular boundary assumptions, but unknown
current calibration/efficiency is not thereby bounded.

Evaluating each hypothetical endpoint at298.15K rather than skin temperature
changes its static voltage by at most0.230mV among these scenarios. This directly
checks these new states; it does not reuse the earlier discharge-only thermal
bound or assume skin temperature equals internal equilibrium temperature.

## Finite rest is still not equilibrium

Every selected rest records zero external current for approximately one hour.
First-to-last voltage changes are+0.767mV,−11.614mV and+270.098mV for initial,
pre-discharge and final rests respectively.

Window placement matters at the sampling/noise scale. Both prespecified last-window
estimators are preserved:

| Rest | Endpoint minus first actual sample at/after t_end−600s | Endpoint minus linear interpolation exactly600s earlier |
|---|---:|---:|
| Initial | −0.001669mV,599.0014s window | +0.114255mV |
| Pre-discharge | −0.878334mV,599.0015s window | −0.737317mV |
| Final | +4.633665mV,599.0003s window | +4.768965mV |

The initial rest is stable relative to its344mV conditional discrepancy; its
small drift even changes sign with this one-sample definition. Neither estimator
bounds much slower relaxation or sensor bias. Final rest is still rising.
An isothermal monotonic approach from below would make the post-rest excess over
the predicted2.941V equilibrium persist or grow, but that assumption is not
established, so it is not used as a rigorous bound.

## Hypothesis outcomes

- **Loaded-polarization-only plus correct rest/inventory/OCP approximation:**
  the rest discrepancies challenge this combined explanation. A zero-current
  comparison is a different observable condition; do not dismiss it because
  the loaded-voltage decomposition closes mathematically.
- **One constant voltage offset alone:** the three differences are unequal,
  so a single offset cannot exactly reconcile them. No offset was estimated or
  applied; instrumental statistical significance remains unqualified.
- **Inventory versus OCP transfer versus finite-rest/measurement effects:**
  not uniquely identifiable here. Terminal voltage is a difference of electrode
  potentials; charge constrains inventory changes only under capacity/efficiency
  assumptions. Inverting these same voltages for SOC would be fitting.

The rest anchors are additional observations from an already viewed specimen,
not blinded validation. No new physical acceptance tolerance is invented without
instrumentation, relaxation and thermal uncertainty.

## Existing information and the exact missing constraint

The dataset already contains CC/CV charge, discharge current, full one-hour
rests and skin temperature. The preserved inspection of earlier same-cell
0.05C/25°C data also records4.887153Ah removed and final-rest2.760849V. Thus
low-rate information is not wholly absent. Its endpoint is at a different
passed charge/history; it cannot be treated as the same SOC or as equilibrium
merely because current was lower. This audit reads that prior qualified summary,
not a newly downloaded/re-read low-rate workbook.

These records do **not** supply a quantified bound on finite-rest equilibrium
error, internal temperature, voltage/current calibration, intercalation
efficiency, or independently measured electrode active capacities/inventory.
The nominal full-cell capacity is not either electrode's active capacity.

A genuinely discriminating next constraint is a rested OCV-versus-passed-charge
reference with quantified relaxation/thermal/instrument uncertainty, and an
independent electrode-capacity/inventory or electrode-resolved potential anchor
to separate inventory mapping from transferred OCP laws. Existing summaries do
not establish those independent quantities. No new acquisition is started.

## Scientific decision and reproducibility

**No arbitrary new dynamic solve is recommended from this screen.** A rest-only
solve from a fabricated spatial state or a charging replay from unqualified
initial SOC would add conditional model trajectories without independently
separating the candidate causes. Do not extend a simulation beyond its voltage
event merely to reach the measured charge. Any proposed new experiment must
freeze its new independent constraint, comparison and resource bounds first.

- [Comparison protocol](stanford-k2-rest-inventory-protocol.md)
- [All original source rows, with Excel-row indices](benchmarks/stanford-k2-rest-records.csv.gz)
- [Complete charge ledger and rest comparisons](benchmarks/stanford-k2-rest-inventory.json)
- Run `python scripts/audit_stanford_k2_rest_inventory.py`. Optional
  `--verify-workbook data/stanford/raw/NMC_k2_1C_25degC.xlsx` verifies every
  archived row against the already available original workbook; it downloads nothing.

Source: Edoardo Catenaro and Simona Onori, [DOI10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2),
[CC BY4.0](https://creativecommons.org/licenses/by/4.0/). Original workbook
SHA256`20ec90e107e228515a95346dc3159d08df62e78bb0f371d10161e62de49e8086`.
All values and naive dates are retained; only format conversion and Excel-row
indexing are applied. Model-derived hypothetical states are clearly separate.
