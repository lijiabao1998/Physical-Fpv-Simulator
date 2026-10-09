# Verify a saved replay without running a model

The research CLI now verifies the saved k1 and representative-thermal replay
bundles locally. It needs the receipt JSON and its two original ZIPs; it does not
download missing files, extract or execute archived code, or launch a solver.
Use the existing pinned project environment; the verifier arithmetic itself uses
only the Python standard library, while the CLI retains its usual dependencies.

For the existing k1 artifacts:

```sh
physical-fpv verify-replay \
  --receipt docs/benchmarks/stanford-k1-current-source-20261009-evidence.json \
  --inputs /path/to/current-source-k1-inputs-37887926852.zip \
  --outputs /path/to/current-source-k1-evidence-37887926852.zip \
  --out results/k1-verification.json
```

Use the corresponding thermal receipt and ZIP filenames for the thermal case.
The original ZIPs are retained in Library and in
[run37887926852](https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/37887926852).
This command does not acquire them automatically.

## Results and exit codes

The JSON separates archive integrity, numerical gates and empirical gates.
- Exit0: the completed saved evidence is internally verified against the supplied
  receipt. This alone does not mean empirical acceptance.
- Exit1: unreadable, unsupported, inconsistent or incomplete evidence.
- Exit2: verification succeeded, but an explicitly requested gate did not pass.

Add `--require-numerical-pass` to require numerical acceptance. Add
`--require-empirical-pass` to require empirical acceptance. The latter exits2 for
k1's known191.473522mV RMSE failure and for thermal's unavailable empirical check.
The report is still emitted, so automation can inspect the reason. An optional
output path cannot overwrite either input ZIP or the receipt.

## What is checked

The verifier checks ZIP sizes and SHA256 values, exact member sets, staged-file
hashes, full source/recorded-analysis contracts, echoed manifests, commit/run/case
identities and launch/terminal records. It rejects duplicate JSON keys, ambiguous
or traversal-style member names, symlinks, encrypted/unsupported archives,
nonfinite data, malformed CSVs and nonincreasing clocks. Limits are32MiB per ZIP,
64MiB expanded,512 members and200000 CSV rows; archives are never extracted.

It independently interpolates both meshes on their shared union of time knots,
recomputes maximum voltage/temperature differences and cutoff-capacity ratio,
and checks the original5mV/0.1K/1% limits. For k1 it verifies the complete residual
knot union, compares residual columns with the saved measured/model exports,
and integrates squared piecewise-linear error exactly. Voltage RMSE and maximum
error are checked against the unchanged50mV and300mV gates.

A relative1e-11 / absolute1e-12 tolerance is used only to compare independently
reproduced floating-point metrics. It does not relax any scientific threshold.
Recorded physical-audit/cutoff flags participate in the numerical verdict, but
unavailable internal states are not reconstructed. Other empirical gates remain
explicitly recorded-only. Temperature-proxy results are not promoted to
independent thermal validation.

The caller-supplied receipt is the trust anchor. This tool checks consistency
against that receipt; it does not authenticate a signature, contact GitHub, or
prove that the caller's current checkout is the executed source. Keep the receipt
from a trusted reviewed commit. A coherent replacement of both receipt and data
is outside checksum authentication's claim.

## Reproduced examples

Both complete original saved bundles pass offline integrity and numerical checks:
- [k1 verification JSON](benchmarks/offline-replay-verification-k1.json):42 input
  files,22 output members,191.473522mV voltage RMSE, empiricalFAIL.
- [Thermal verification JSON](benchmarks/offline-replay-verification-thermal.json):
  34 input files,10 output members, empiricalnot evaluated.

Synthetic archive tests exercise corruption and gate behavior in ordinary CI.
Two additional tests verify the real saved ZIPs when already present and skip
when absent; tests never fetch them. This iteration adds reproducible verification
tooling without claiming to fix the empirical model error.
