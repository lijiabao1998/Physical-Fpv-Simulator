# Scientific evidence and limitations

## Primary data and equations

Chen, C.-H.; Brosa Planella, F.; O'Regan, K.; Gastol, D.; Widanage, W. D.; Kendrick, E. (2020). *Development of Experimental Techniques for Parameterization of Multi-scale Lithium-ion Battery Models*. Journal of The Electrochemical Society 167, 080534. DOI: https://doi.org/10.1149/1945-7111/ab9050

Original measurements: https://doi.org/10.5281/zenodo.4032561 . License CC-BY-4.0 confirmed in https://zenodo.org/api/records/4032561 on 2026-10-07. The three CSVs are unmodified. Our parser selects complete discharges and converts °C to K; it does not smooth, stretch, align or fit curves. Any generated comparison is an analysis derived from these data and is attributed to the authors above. CC-BY-4.0: https://creativecommons.org/licenses/by/4.0/ . The dataset license is distinct from the paper license.

PyBaMM: Sulzer, V. et al. (2021), *Python Battery Mathematical Modelling (PyBaMM)*, DOI https://doi.org/10.5334/jors.309 . Package https://pypi.org/project/pybamm/26.9.0.0/ , BSD-3-Clause. Equations and published parameter functions are used from the installed package, not silently reimplemented. Parameter fingerprints include function source and scalar values.

Original PyBaMM Chen parameter addition: https://github.com/pybamm-team/PyBaMM/pull/854 . Its patch labels electrode/separator thermal properties as defaults, and current-collector values as handbook values. This does not establish an LG-M50 thermal characterization.

## Data semantics

- Raw CSV header is line 14. Use column names including units rather than positional guessing.
- Current magnitude is positive during both charging and discharging. Use `Md == D` and known steps.
- Complete discharges are steps 7, 12, 17, 22 at 0.5, 2.5, 5 and 7.5 A. Initial partial-discharge step 2 is excluded.
- The selected discharge times must be strictly increasing. Duplicate timestamps in other phases are not silently repaired or used.
- The experiment has two-hour rests and nominal 25°C chamber conditions, but measured surface and chamber temperatures differ from 25°C. Expose both. In these files the charge is approximately 1.5 A, although the paper describes C/3; do not replace the raw values by 5/3 A.
- Preserve published initial concentrations (negative 29866, positive 17038 mol/m³). `initial_soc=1` would replace them and shift OCV from about 4.181 to 4.2 V; this implementation does not do that.
- Original authors tuned parameters on these cells and retuned diffusivity by rate. Our unchanged-parameter discharge-only metrics cannot be presented as their reported all-phase, three-cell-mean metrics.

## Supported and unsupported claims

Supported: reproducible numerical solutions and measured-data comparisons under the stated cell, initial state, constant-current and temperature assumptions. Report passing and failing targets independently of software CI.

Not established: independent generalization; accurate transient thermal behavior; high-C FPV pulsing; aging; internal shorts; plating; thermal runaway; mechanical damage; pack imbalance; material synthesis; safe hardware operating limits; flight performance. No instructions for manufacturing or abusing real cells are provided.

Numerical guards limit software scope only. Generic parameters, zero entropy terms and temperature-independent transport functions make the optional lumped temperature exploratory. Surface temperature is also not identical to a volume-average state. The test suite checks equations and reporting logic, not scientific certification.

## Next qualified thermal benchmark

O'Regan et al., *Thermal-electrochemical parametrisation of a lithium-ion battery: mapping Li concentration and temperature dependencies*, primary paper: https://wrap.warwick.ac.uk/id/eprint/196287/ . Parameter measurements: https://doi.org/10.5281/zenodo.5171874 (CC-BY-4.0). Validation archive: https://doi.org/10.5281/zenodo.4864437 (Zenodo `other-open`; repository v1.0 BSD-3-Clause https://github.com/brosaplanella/TEC-reduced-model/blob/v1.0/LICENSE).

The source contains 48 traces spanning 0, 10 and 25°C, four rates and four cells per condition. Cell IDs are reused across temperatures; do not claim 48 independent cells. Published adjustments to initial states, diffusion, entropy and cooling mean this is another public reproduction benchmark, not untouched independent validation. Review parameters/protocol, freeze targets and reserve implementation checks before importing it.

DLR/SINTEF MJ1 data are a later materials/electrode reproduction path. Its complete parameter file describes a third-reference-electrode cell with a replacement 260 µm separator and placeholder initial concentrations; it is not an intact-commercial-MJ1 drop-in. Source: https://doi.org/10.5281/zenodo.15496570 (CC-BY-4.0).
