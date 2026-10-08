Build it from physical properties. Test it. Fly it. Break it. Build it better.

# Physical-Fpv-Simulator

Physics-first FPV simulator built from real physical properties.

**Physics fidelity first.** Adjustable engineering variables must act through explicit physical models, units and evidence. No arbitrary performance buffs.

## Battery research core: first executable slice

A CPU-only Python research tool built around **PyBaMM 26.9.0.0**, with SPM, SPMe and Doyle–Fuller–Newman (DFN) models. The first benchmark uses the published **Chen2020 LG M50** parameters and **three real cells at four discharge rates**. It downloads the original measurements, checks their checksums, runs unchanged parameters, and reports every error and failed gate.

This is public-benchmark reconstruction, **not independent validation**, a battery safety tool, or a flight-ready simulator. The original study used these cells during parameterization and adjusted diffusivity by rate. This implementation does not fit to the traces. Cell03/04 are reserved implementation checks only.

The initial 20-point mesh failed the predeclared numerical target at high rates. We retain that result and audit a refined 40-point grid against 80 points. Experimental acceptance thresholds are unchanged. See [the frozen protocol](docs/validation-protocol.md), [numerical refinement](docs/numerical-refinement.md), and [initial results](docs/benchmarks/initial-mesh20.md).

## Run it

Python 3.12, Linux CPU is the tested environment. No account, API key, GPU or paid service is needed.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
physical-fpv fetch-data
physical-fpv simulate --model DFN --current 5 --out results/example
physical-fpv benchmark --out results/dfn
pytest -q
ruff check src tests
```

The benchmark writes `report.json`, `report.md`, a report checksum, and voltage/capacity/temperature/lithium time-series CSVs. Current is amperes, time seconds, voltage volts, capacity ampere-hours and temperature kelvin. Use `--require-pass` to return exit code 2 when any frozen research gate fails. A normal completed report command can exit zero while its scientific gates fail; **read the report**. `--skip-numerics` is exploration only and can never produce a passing research gate.

```sh
physical-fpv benchmark --model SPMe --out results/spme
physical-fpv simulate --thermal lumped --out results/exploratory-thermal
physical-fpv material-method-check
```

Lumped thermal simulation is explicitly **unvalidated**: several built-in Chen2020 thermal properties are generic defaults, entropy terms are zero, and some transport laws lack temperature dependence. Isothermal temperature is an imposed assumption, not a predicted temperature. Numerical heat-balance checks do not establish agreement with measured temperature.

## Current results

Software checks pass (85 tests). On the refined DFN grid, the **experimental gate passes 6 of 12 traces and fails 6 of 12**; overall research acceptance is **FAIL**. Numerical convergence passes. Thermal validity is **not established**. See [the complete refined report](docs/benchmarks/refined-mesh40.md). CI separately enforces software/numerical checks and uploads the empirical failures without treating them as a scientific pass.

## Thermal reconstruction: inspect the second cohort

The ORegan2022 extension covers **36 first-discharge traces from12 LG M50 cells**, at0/10/25°C and0.5/1/2C. Published diffusion corrections and h=15 W/m²/K are declared; no new fit or initial-voltage alignment is performed.

On grid40, **6/36 empirical targets pass and30/36 fail**. Voltage RMSE ranges24.51–88.00mV; surface-proxy temperature RMSE0.35–14.68K, including the retained cell791 anomaly. All36 actual-node/surface, lithium, charge and heat-balance audits pass. These are separate findings: **this is not a mature, qualified battery model**.

The 1C/25°C representative40→80 mesh check actually completed in187 seconds but **failed convergence targets**: maximum voltage difference14.33mV versus5mV, and temperature difference0.207K versus0.1K. Peaks occur at340s and970s, not at the slightly different cutoff endpoints. The same-case80→120 check has now passed:3.321mV maximum voltage difference,0.0180K temperature difference and0.00345% capacity difference, within the20-minute/4GB budget. The exact source run is [37681264082](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37681264082) at f746e0e. Packaging-only changes reuse this recorded result after checking calculation fingerprints; CI explicitly labels reuse rather than claiming a new solve. Whole-cohort numerical verification remains open. Cold conditions and some hot endpoints extrapolate measured parameter ranges.

- [Full36-case thermal report](docs/benchmarks/thermal-grid40.md) and [machine-readable summary](docs/benchmarks/thermal-summary.json)
- Raw-data inspection, duplicate counts and sensor flags: run physical-fpv thermal-inspect
- [Representative numerical comparison](docs/benchmarks/thermal-representative-grid-comparison.json) and [solver statistics](docs/benchmarks/thermal-solver-statistics.txt)
- [Frozen thermal protocol](docs/thermal-protocol.md), [numerical status](docs/thermal-numerical-status.md), and [ghost-point audit correction](docs/concentration-audit-correction.md)

```sh
physical-fpv thermal-fetch-data
physical-fpv thermal-inspect
physical-fpv thermal-benchmark --skip-numerics --out results/thermal-final
python scripts/render_thermal_evidence.py
python scripts/verify_thermal_grid.py --timeout 600
```

The36-case grid40 report intentionally marks numerical stages NOT RUN. The separate representative result does not establish convergence for the remaining conditions. Running thermal-benchmark without --skip-numerics requests all frozen numerical checks and is computationally heavier.

See [the first no-fit causal diagnosis](docs/causal-diagnosis.md) for grouped failures, the original TEC implementation differences, and the unchanged-parameter cell790 check. Standalone evidence exports now carry authors, DOI, source-license distinctions and required notices; this does not select a license for original project code.

## What is implemented

- Published porous-electrode electrochemistry, bounded solver settings and version-pinned dependencies
- Attributed, checksum-pinned CC-BY-4.0 experimental data retrieval (about 1.8 MB; not vendored)
- Correct discharge selection, current-sign semantics, units and initial concentrations
- Time-weighted voltage RMSE, maximum error, cutoff capacity error, overlap coverage and correct-termination gates
- Mesh/tolerance convergence, lithium inventory, current integration, sampled concentration bounds and exploratory heat balance
- Input-range rejection and temperature-event termination; no claim that these guards certify safe batteries
- A provenance/uncertainty-aware materials interface and an analytical atomic-hop method check
- Tests that reject passing claims for truncated traces, unqualified material mappings and temperature-triggered stops

## Materials and scale boundaries

The analytical jump-network tool evaluates a prescribed, balanced random walk using migration barriers and rates. It does **not** compute those barriers from atomic coordinates or discover a material. Tracer diffusion cannot be silently used as chemical diffusivity; formation energy cannot be used as migration energy or conductivity. The materials interface rejects unsupported mappings and records structure hashes, method, source, temperature support and uncertainty.

The intended chain is:

`atomic structure -> qualified property calculation -> electrode effective parameters -> cell -> pack -> FPV load`

Each arrow requires a validated method and a declared domain. Missing physics stays unsupported, rather than being filled with invented data. See [the roadmap](docs/roadmap.md).

## Evidence and licensing

- [Data manifest, sources and attribution](data/manifest.json)
- [Scientific scope and source licenses](docs/evidence.md)
- [Dependency license inventory](docs/dependency-licenses.json)

This project is not affiliated with or endorsed by the laboratories, authors, manufacturers or software projects cited. Dependency and dataset licenses remain their own. No open-source license for this repository's original code has been selected yet.

The unchanged-state cell790 polarization diagnostic completed in780.04seconds within its frozen1200-second/4GB budget. Voltage decomposition and electrode-inventory checks passed, and the previous120-point curve was reproduced within5.64e−8V. The largest modeled cutoff loss is338.65mV from negative-particle concentration polarization. This explains the frozen model’s behavior; it does not identify the real cell’s unique failure mechanism or repair the30/36 experimental failures. See [the findings](docs/polarization-findings.md), [exact evidence](docs/benchmarks/polarization-grid120-summary.json) and [predeclared protocol](docs/polarization-protocol.md).
