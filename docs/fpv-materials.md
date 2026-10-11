# Materials, parameters and multiscale boundaries

## What now executes

1. `fpv.material_bridge.solve_material_spm` creates a fresh bounded PyBaMM SPM
   using the published Chen2020 reconstruction, optional existing `PropertyEstimate`
   contracts, and explicitly recorded parameter fingerprints/sources. It solves
   <=60 simulated seconds at 0.5–7.5 A; it does not alter `core.simulate` or its
   cached templates. Material overrides only map supported intrinsic-particle
   chemical diffusivity at 298.15 K, matching phase and full stoichiometry domain.
   Unknown or partial support is rejected. A caller's evidence label is retained,
   never independently certified by the software.
2. `ElectrodeMapping` transforms electrolyte transport using epsilon/tortuosity
   and computes active solid volume fraction. Geometry must obey volume closure.
   This is theoretical homogenization with supplied assumptions, not qualified
   microstructural identification. The tracer-to-chemical formula requires both
   thermodynamic and correlation factors with their own source; it never feeds
   the battery solver automatically or promotes an analytical method benchmark.
3. `fpv.atomistic.aluminum_eos` performs an actual ASE 3.26 EMT empirical-potential
   calculation on periodic fcc Al, 7/9/11 volume points and <=108 atoms, then fits
   a Birch–Murnaghan EOS. It reports raw volume/energy arrays, structure hash, ASE
   version, equilibrium density and bulk modulus. No external structure was
   fetched: fcc Al at initial a=4.05 Å is an explicitly constructed reference.
4. `--emt-frame` on the GUI server connects the resulting perfect-crystal density
   to a hypothetical 50 cm³ solid frame mass plus 0.585 kg synthetic components.
   Inertia is scaled for unchanged synthetic geometry, so the material result
   changes the actual hover trim/dynamics. This demonstrates a mass mapping,
   not a measured aircraft construction or battery-electrode parameter.

## Sources and units

- [Chen et al. 2020 parameterization](https://doi.org/10.1149/1945-7111/ab9050),
  accessed through pinned PyBaMM Chen2020. Diffusion m²/s, concentration mol/m³,
  voltage V, current A, time s, capacity Ah. This is reconstruction of a published
  parameter model, not a claim every coefficient is a directly measured constant.
- [PyBaMM parameter interface](https://docs.pybamm.org/en/latest/source/examples/notebooks/getting_started/tutorial-4-setting-parameter-values.html)
  supplies the software mapping convention.
- [ASE EMT documentation](https://docs.ase-lib.org/ase/calculators/emt.html) and
  [bulk/EOS example](https://ase-lib.org/examples_generated/tutorials/bulk.html).
  EMT is explicitly an empirical model suited to small method demonstrations;
  it is not DFT or an electrode-transport calculator. Energy eV/atom, volume
  Å³/atom, force eV/Å, bulk modulus GPa and mass density kg/m³ are converted
  explicitly. 1 eV/Å³ = 160.2176634 GPa.

## New numerical result and its retained failure

For the same 30-second, 1-A SPM material-bridge example, the fixed 1-mV maximum
voltage-difference gate **fails for mesh20→40** (1.623532 mV) and **passes for
mesh40→80** (0.830176 mV). No threshold changed. Charge and lithium checks pass
for each curve. This is a bounded numerical comparison, not empirical validation,
full discharge convergence or proof of asymptotic order. Raw results are in
`results/material-mesh-evidence.json`; reproduce with `python -m physical_fpv.fpv
material --out results/material-mesh-evidence.json`.

The 9-point, 32-atom EMT reference predicts density approximately 2813.085 kg/m³
and bulk modulus 38.740 GPa. These are model outputs with **no measured agreement
gate asserted**. The 7-point/4-atom versus 11-point/32-atom checks agree within
1e-4 relative density and 0.5% bulk modulus. Symmetry forces are below 1e-9 eV/Å.
Those checks test sampling/replication consistency, not potential accuracy.

## Still scientifically open

No lithium electrode DFT, NEB migration barriers, defects, correlations,
thermodynamic factors, phase stability, disorder or composite-electrode
qualification is produced. No arbitrary structure→capacity shortcut exists.
The user would need cited structures and a justified electronic-structure method
or potential, convergence budget and independent reference properties before a
battery-material calculation is meaningful. No data fitting or new measurement
has been carried out. All original battery empirical failures remain unchanged.

The material-SPM bridge and synthetic interactive pack remain distinct models.
The separately documented homogeneous electrochemical pack bridge may connect
supported cell equations to synthetic downstream loads; none of these routes
qualifies a racing pack or replaces independent validation.
