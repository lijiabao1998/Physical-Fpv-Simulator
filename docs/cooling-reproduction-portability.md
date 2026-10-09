# Cooling prediction reproduction across CPU math implementations

Battery CI on onset commit `3d3aa1081e5fa6784657c5e2b2330c0242c0af77`
failed a byte-hash equality assertion for a regenerated cooling prediction CSV.
The archived evidence itself did not change, and the scientific metrics passed
an independently reviewed 64-binary64-epsilon comparison.

The exact CI hash was reproduced locally by disabling NumPy's AVX-512 dispatch:

```sh
NPY_DISABLE_CPU_FEATURES=X86_V4,AVX512_ICL,AVX512_SPR \
  python scripts/check_stanford_cooling_transfer.py --out results/cooling-portability
```

| CSV | SHA256 |
|---|---|
| Immutable archived/native output | `7d8d7ee64206573fd9ad693ea5ba16fef08baa47545b8b6d42570359a50375a2` |
| AVX-512-disabled and baseline output | `37c52b36d9d92fdea99cd2efa9cc1efa3debd0495be387822702da4a4ba531a4` |

Among 3,543 rows, exactly 19 generated prediction values differ, by at most
3.552713678800501e−15 K. Header, shape, time and measured-temperature columns are
identical. Both no-AVX-512 and baseline modes produce the exact failing CI hash.
This establishes floating-point implementation portability as the source of this
specific assertion failure, without changing the scientific interpretation.

The test now distinguishes artifact identity from numerical reproduction:

- The immutable archived CSV retains its exact pinned SHA256.
- Each generated CSV must match its own reported SHA256.
- Headers, shapes, finite values, time and measured-source columns remain exact.
- Only recomputed prediction columns allow 64 eps × max(1, |archived value|).
  At these temperature magnitudes this is about 4e−13 K, an arithmetic budget,
  not experimental uncertainty or a physical acceptance threshold.
- Negative checks reject material prediction changes, source-temperature or
  clock changes, nonfinite values, schema/row changes and incorrect hashes.

The earlier metric comparison continues to require exact metadata, types,
structures, flags and verdicts. Source/frozen-fit hashes, no-fit/no-solve/no-download
checks, quadrature criteria and all scientific gates remain unchanged. Native
and AVX-512-disabled focused tests both pass. This fix changes no physics
implementation, parameters or cached scientific receipts. Existing unit and CI
checks continue normally.
