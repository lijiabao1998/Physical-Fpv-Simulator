# Ordinary Battery CI: immutable-input persistence proposal

Status: proposal; no cache or workflow change has been made. Remote1ec4cdc8's Battery run37961776296 failed before tests in both permitted attempts with HTTP504 during the Chen acquisition batch. The log does not establish which cell request failed. Preserve both failures as source-service failures; stop reruns of that job. Stanford and Thermal specialized CI succeeded.

## Existing evidence audited

A read-only scan of32,540 files,180 ZIPs and7 tar archives across the authorized cloud workspace found only two of the six raw inputs required by ordinary Battery CI. The Stanford workbooks are inside authenticated artifact11597286705 from run37887926852/source744794b02d44bcbfc702ad8e5c403782128d11b0: archive2113875bytes, SHA256c777b934ed13ed02aac194c045e7582b8032820e2706867517aa92911d2477a9. Both raw members and all42 staged members reproduce the saved manifest. Artifact metadata was verified; expiration2027-01-07T05:18:06Z.

The required identities are:

| Payload | Bytes | SHA256 | Existing exact bytes |
|---|---:|---|---|
| LGM50_cell02.csv |597715|650e7f9ac5217b4db158047e50b6b464100b13f4859002421114edebca629b35|Absent|
| LGM50_cell03.csv |590794|fcc13423786d6044f3ec41b1b278fb1d42ff55018666be743243f7c34b1b98cb|Absent|
| LGM50_cell04.csv |595967|e1cbb60e79911824d5559f12db8e8ecdd4781d077a45f5b1ecbcf103aa271d9e|Absent|
| TEC validation.zip |23155564|3848d0eb1d70e4fc86cc77c272433053760b0bdfe25825ef652135edc43275b8|Absent|
| NMC_k1_1C_25degC.xlsx |1868963|b42a2ad343be13d6baba84ebf149ef79876ef719a067b8dcc8d4f7da9de124f6|Verified|
| manufactuer_specifications.xlsx |9877|7aa23d91f866ebdce4c0e9e0ebb485dcaac73cbc1ec691d86f7a0e0c317aa8c6|Verified|

The thermal replay input archive contains no raw files. Normal successful Battery artifacts persist results only. Derived curves cannot reconstruct or substitute for raw inputs. Missing entries above are expected manifest pins, not newly verified raw bytes. Chen and Stanford use recordedCC-BY4.0 provenance; TEC's archivedLICENSE is recordedBSD3-Clause, distinct from the O'Regan parameter-data license. Preserve full source notices.

## Proposed design, pending independent review

1. Add a pure offline preflight that checks exact six paths, sizes, SHA256, and original ChenMD5 before any parser or model consumes them. It must reject missing, corrupt, symlinked or out-of-scope files and never invoke acquisition. Manifest-content identity determines the cache identity; a cache hit alone is insufficient.
2. Future ordinary authorized CI acquisitions may persist fully verified raw inputs plus exact source URLs, license notices and hash receipts, separately from science outputs. Failed or partial acquisition must not seed a complete cache. Keep original source pins and original scientific tests/gates untouched. Do not change security permissions.
3. Restore only a reviewed complete archive whose repository/run/source/artifact ID, byte length, digest and exact safe member list are pinned. Reject duplicate normalized destinations, traversal, nonregular members, hardlinks, symlinks or symlinked parent directories, expired metadata and mismatches. Extract into a fresh staging directory under a fixed decompressed-byte budget before verification. No historical source code restoration. Rehash every raw member after extraction. Do not use broad cache prefixes or unchecked mutable artifacts.
4. Artifact-service transient retries, if implemented later, need a bounded same-endpoint policy with a fixed wall deadline. Authorization failures and integrity mismatches are terminal. No alternative source or denied-path fallback.
5. Distinguish complete offline-preflight success from scientific CI success. Acquisition failure must remain visible; no skip-as-green. The normal existing benchmark remains separately authorized ordinary CI, but a preparation-only invocation must not dispatch it.

## Current feasibility and stopping boundary

No complete seed exists. Therefore this proposal cannot presently make ordinary CI fully offline or close the Chen504 blocker. Persisting the two valid Stanford inputs alone would not repair the failed first stage. Do not retry denied direct TEC access, reconstruct the four missing inputs, alter hashes, or rerun the failed job again. A subsequent reviewed engineering change may improve future persistence; report the current external source blocker until a legitimate normal acquisition produces the exact missing bytes. Offline scientific analysis can proceed independently from already committed evidence.
