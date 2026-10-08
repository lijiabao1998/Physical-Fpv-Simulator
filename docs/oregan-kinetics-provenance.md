# Kinetic representation and sampled input support

The unchanged ORegan parameter functions were evaluated against all 80 released exchange-current points, without solving a battery model or fitting anything. [Original CSVs and source/license manifest](../data/oregan-kinetics-manifest.json) are pinned to version 1.0 of DOI [10.5281/zenodo.5171874](https://zenodo.org/records/5171874). The archive is 479,705 bytes, SHA256 `1c5052e8af198429c29b6784681e7b1b7d8a4e48dfca03c6fc23df639ce084de`; only 2,031 bytes of unchanged CSVs are vendored. Official record metadata confirms the four named creators and CC BY 4.0. This is a source check after the external-cell failure, not an independent or blind validation.

Run `python scripts/audit_oregan_parameter_support.py`. The [result](benchmarks/oregan-parameter-support.json) includes every point, source row/hash, exact units, the fixed parameter-source checksum and actual saved 120-point surface extrema. No experimental gate or parameter value changes.

## Sampled envelope versus simulated surface states

| Electrode | Released stoichiometry envelope | Saved surface envelope | Finding |
|---|---:|---:|---|
| Negative |0.1585–1.0000|0.038867–0.975763|Below sampled minimum|
| Positive |0.2598–0.8499|0.269970–0.995577|Above sampled maximum|

Both released envelopes occur at 15, 25, 35, 45°C. Initial negative stoichiometry 0.975763 is inside its sampled range. The complete saved surface extrema establish that some states leave each sampled envelope; crossing times and duration outside it are unavailable from extrema and remain null. Electrode stoichiometry is not full-cell SOC. Being inside the envelope would not prove the fitted function valid between measurement points or for another batch.

The existing temperature check covers only its listed diffusion, exchange-current and heat-capacity ranges. It cannot establish full parameter applicability: the stoichiometry limits above are different conditions. Positive electronic conductivity adds another limitation: the predicted maximum 36.48°C exceeds its nominal 15–35°C measurement range. The new report records this extra applicability annotation without changing earlier gates. The spatial 80→120 PASS, 191.474 mV empirical FAIL and all prior Chen/ORegan failures remain unchanged.

## Fixed functions do not interpolate the released points

Source units convert as 1 mA/cm² = 10 A/m². Comparisons use 1,000 mol/m³ electrolyte and temperature from the CSV filename plus 273.15 K. At 25°C, unweighted point RMSE is 0.465723 A/m² negative and 0.487243 A/m² positive. Examples:

| Electrode and stoichiometry | Released j0 (A/m²) | Installed j0 (A/m²) |
|---|---:|---:|
| Negative,x=0.926|0.684138|1.460636|
| Positive,x=0.8499|0.432460|1.590598|

These differences characterize a reduced fitted representation, not a newly fitted model, established transcription error or quantified cause of the external 191 mV residual. The release dates from 2021; exact correspondence between these points and the final 2022 supplementary coefficient table remains unresolved.

The installed concentration law is `iref*x**alpha*(1-x)**(1-alpha)*(ce/1000)**(1-alpha)*exp(E/R*(1/298.15-1/T))`. Negative coefficients are 2.668 A/m², .792, 40,000 J/mol; positive are 5.028 A/m², .430, 24,010 J/mol. Their concentration exponents do not replace the separate symmetric Butler–Volmer overpotential law. The code/source checksum, rather than a mutable branch name, fixes the inspected implementation.

## Provenance distinctions that remain unresolved

The [manuscript](https://wrap.warwick.ac.uk/id/eprint/196287/2/WRAP-Thermal-electrochemical-parameters-high-energy-22.pdf), §§1.2.3/1.3.3, infers j0 from half-cell EIS charge-transfer fits and estimated particle interface area. It separates SEI and charge-transfer circuit terms; these are not measured full-cell contact resistances. Applying its stated 11 mm disc diameter and Table 8 geometry does not reproduce the separately reported half-cell interface areas. Half-cell geometry correspondence remains unresolved; no area rescaling is applied.

Positive coating conductivity was measured near positive stoichiometry 0.9 at 15–35°C; its lithium-concentration dependence was not measured. Negative conductivity 215 S/m is inherited from Chen. These provenance distinctions do not establish a software bug.

The manuscript assumes EC:EMC 3:7 by volume, while the borrowed [Landesfeind data](https://mediatum.ub.tum.de/download/1538307/1538307.pdf), Eq. 15/Table II, are 3:7 by mass. The installed coefficients and mol/m³→mol/L and mS/cm→S/m conversions match that borrowed law; the composition convention remains an assumption discrepancy.

The installed core uses bulk electrode/electrolyte ohmic losses, symmetric kinetics, no explicit SEI film resistance and no active terminal contact-resistance term. No measured contact value was identified. Exact supplementary author configuration and Table S8 were not recovered, so no coefficient correction or assertion about every author-model loss is justified. Same commercial cell name does not establish matching batches, conditioning or sensing boundaries.

Source measurements: Kieran O'Regan, Ferran Brosa-Planella, W. Dhammika Widanage and Emma Kendrick; CC BY 4.0. Numerical functions remain under PyBaMM's own license. Original project-code licensing remains undecided.
