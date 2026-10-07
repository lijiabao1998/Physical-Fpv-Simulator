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

Software checks pass (49 tests). On the refined DFN grid, the **experimental gate passes 6 of 12 traces and fails 6 of 12**; overall research acceptance is **FAIL**. Numerical convergence passes. Thermal validity is **not established**. See [the complete refined report](docs/benchmarks/refined-mesh40.md). CI separately enforces software/numerical checks and uploads the empirical failures without treating them as a scientific pass.

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
