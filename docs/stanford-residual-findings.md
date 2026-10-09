# Stanford k1 residual and measurement-boundary diagnostic

This exploratory analysis uses the existing, authenticated mesh80 curve and the original k1 workbook. No new battery model is solved, no parameter is fitted, and no acceptance gate is changed. The 190.899 mV voltage RMSE remains a failure. These diagnostics do not themselves establish spatial convergence; the separately recorded mesh120 result governs that status.

Run `python scripts/diagnose_stanford_residuals.py`. The [machine-readable result](benchmarks/stanford-k1-residual-diagnostic.json) records source hashes, workbook row numbers, adjacent rests, exact time-integrated residuals, and conditional charge-conservation calculations. Missing measurements and the unmatched tail remain visible.

## The error begins under load

The measured pre-discharge rest ends at 4.186448 V. The unchanged ORegan initial concentrations and temperature give a uniform-state OCV of 4.181049 V, a difference of −5.399 mV. At the first recorded discharge time, 1.0006 s, the measured voltage is 3.879938 V and the mesh80 prediction is 4.100792 V: an error of +220.855 mV. At that same point the predicted average temperature is 25.19058°C, just 0.00264 K above its initial value; the measured skin temperature is 25.18794°C. A large accumulated heating error is therefore not needed for this early discrepancy to appear. This does not isolate which electrochemical or measurement assumption is responsible.

| Requested observed-duration portion | Signed mean voltage error | RMSE | Available fraction |
|---|---:|---:|---:|
| First third | +201.949 mV | 202.109 mV | 100% |
| Middle third | +204.561 mV | 204.607 mV | 100% |
| Last third | +156.155 mV | 161.532 mV | 94.946% |

The full common interval has a signed mean error of +188.093 mV. The final available residual changes sign and reaches −113.940 mV. Thus neither the initial rest-voltage difference nor the cutoff tail alone describes the failure. No voltage offset is subtracted and the missing final 57.105 s is not extrapolated.

## What the source says about the load drop

The last zero-current rest sample and first loaded sample are separated by 1.04558 s on the source test clock. Their voltage difference is 306.510 mV. Dividing by the recorded current change gives 61.299 mΩ. This is an apparent transition ratio containing unresolved fast dynamics, early polarization, finite-rest effects and the measurement boundary. It is not an isolated ohmic or contact-resistance measurement. The frozen model's uniform initial OCV minus its loaded voltage at 1.0006 s is 80.257 mV.

The authors' [Applied Energy paper](https://pangea.stanford.edu/ERE/pdf/OnoriPDF/Journals/60.pdf), Table 7, p.11, reports an NMC pulse-derived resistance of 0.059 Ω, averaged over SOC and six cells. Their pulse experiment uses 1C, 150-second pulses every 15 minutes, and estimates resistance from voltage changes at pulse fronts (pp.10–11). The corresponding 5 A drop, 0.295 V, supports the scale of the observed transition within the same campaign. It does not calibrate this k1 fixture or establish the cause of the DFN discrepancy.

The [data paper](https://pangea.stanford.edu/ERE/pdf/OnoriPDF/Journals/57.pdf) identifies an Arbin LBT21024, an IncuMax IC-500R chamber, a cylindrical holder and a central surface type-T thermocouple (pp.2, 6–7). It gives approximately one-second sampling and the original V/A/°C columns, and states that acquired data were not filtered (pp.5, 7). Neither paper describes sense pickup locations, contact resistance, contact pressure, air velocity, thermal contact conductance, an identified cooling coefficient, or per-channel calibration results. No voltage correction or iR subtraction is documented; this silence does not prove every instrument option was disabled.

Arbin's [later LBT brochure](https://arbin.com/wp-content/uploads/2022/06/LBT_Cell-Testing_rev04.pdf), p.5, describes four-point Kelvin capability for its later listed models. It does not verify this experiment's 2019 wiring. The paper's 24-bit resolution in Table 2 also differs from the current [Stanford equipment page](https://onorilab.stanford.edu/research/facilities-and-equipment/1-battery-testing-system-arbin), which says 18-bit. Neither is a campaign calibration certificate or a measured voltage uncertainty.

The papers identify six fresh INR21700-M50 cells, but no production-lot match to the ORegan cells is established. The referenced [LG-authored tentative specification](https://www.dnkpower.com/wp-content/uploads/2019/02/LG-INR21700-M50-Datasheet.pdf), dated 2016-08-23, uses a different DC-resistance definition: 30 ± 6 mΩ at 50% SOC, 0.5C for 30 s and 25 ± 2°C, without PTC. Its 1 kHz impedance specification is different again. These values cannot be subtracted from the Stanford transition ratio to identify fixture resistance.

## Rest and inventory limits

Both adjacent one-hour rests have recorded zero current. The pre-rest voltage still falls 0.844 mV in its final 600 s; the post-rest voltage rises 4.123 mV in that interval. Equilibrium is not established. The measured post-rest endpoint is 3.061777 V.

Applying the observed discharge charge, 4.707801 Ah, plus the explicitly assumed unobserved initial charge, 0.001389789 Ah, to the published active volumes and initial concentrations conserves total solid lithium. Evaluating the fixed OCP/entropy expressions at the resulting uniform electrode-average stoichiometries and measured post-rest temperature gives 3.026836 V, 34.942 mV below the measured rest endpoint. This is a conditional uniform-redistribution calculation, not a relaxation simulation, measured cell SOC or proof that the inventory parameters are correct. Unknown residual gradients, parasitic losses, cell history and parameter transfer remain relevant.

The useful next discriminator is a separately specified comparison of load/pulse behavior and parameter provenance. The present evidence does not justify adding a fitted series resistor, correcting measured voltage, changing initial SOC, or fitting all six reserved cells. The previous Chen 6/12 and ORegan 30/36 empirical failures remain unchanged.

Source measurements and derived summaries: Edoardo Catenaro and Simona Onori, DOI [10.17632/kxsbr4x3j2.2](https://data.mendeley.com/datasets/kxsbr4x3j2/2), CC BY 4.0. ORegan parameter attribution and dependency notices remain in the repository's source notices. Changes here are diagnostic scalar summaries and conditional parameter-function evaluation; no institutional endorsement is implied.
