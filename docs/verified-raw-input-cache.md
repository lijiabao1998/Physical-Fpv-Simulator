# Verified raw-input cache for ordinary Battery CI

This change makes a successful official acquisition reusable without changing its source bytes, parsers, numerical checks or empirical thresholds. It cannot manufacture a cache seed while the upstream source is unavailable.

## Identity and trust

`scripts/verified_raw_cache.py key` hashes the canonical six-file specification and the exact bytes of the Chen, thermal and Stanford source manifests plus the Stanford acquisition protocol. The key has no broad restore prefixes. The bundle contains exactly six original payloads and one canonical manifest. It uses stored ZIP members and a 27,000,000-byte total transport limit; source lengths sum to 26,818,880 bytes. It includes no executable source or historical model code.

The six inputs are the three Chen cells 02/03/04 CSVs, the complete TEC validation archive, Stanford k1 1C / 25°C workbook and manufacturer workbook. Original sizes/SHA256 and Chen/TEC MD5 are checked. The bundle embeds all three original source manifests, including authors, source URLs and DOI/license information, plus manifest hashes and an explicit unmodified-payload statement. The original TEC archive retains its full license notice. Committed attribution documentation remains available as well. No alternative source URL or changed checksum is introduced.

The official GitHub `actions/cache/restore` and `actions/cache/save` actions are pinned to verified v4.3.0 commit 0057852bfaa89a56745cba8c7296529d2fc39830. A transport cache hit is not evidence acceptance. Every restored member is hashed again before any destination is changed. Missing, extra, duplicate, compressed, nonregular, oversized or mismatched members fail closed. Symlinked paths and hardlinked input files are rejected. A fresh staging directory and explicit six destinations replace generic archive extraction. Existing corrupt destination files are rejected rather than overwritten.

## Workflow behavior

- Exact cache hit: verify the entire bundle, install only verified payloads, then rehash all six files. A corrupt hit fails; it does not silently download replacements.
- Cache miss: invoke the existing official acquisition entrypoints once, with their existing timeouts, byte limits, checksum checks and failure behavior. No new retry or alternate endpoint is added.
- Only a complete six-file verification permits bundle creation and cache save. A partial acquisition cannot seed the cache.
- Original thermal/Stanford inspections, complete test suite, DFN numerical/empirical benchmark and materials check remain required. Cache preparation never changes a scientific verdict or makes skipped tests green.

The logging wrapper adds a Python audit hook that recognizes only the six existing request URLs and prints the associated repository file label before the request. The added audit diagnostics never print request URLs, query strings, headers, bodies or temporary redirect credentials. Original acquisition stdout remains unchanged and can contain the committed public source URLs in its checksum/provenance receipts. It does not replace the network implementation. Thus a later 504 can identify the last attempted input, unlike the prior batch-only logging.

This cache is best-effort CI transport, subject to GitHub cache scope and eviction. It is not the durable scientific source of truth; committed result artifacts retain that role. Tests cover exact manifest-key changes, round-trip integrity, every-input corruption, absent/duplicate/unsafe members, corrupt existing destinations, path/link rejection and safe source logging. All tests use local synthetic fixtures; no original input is reconstructed.

## Known initial state

Before this change, the read-only audit found only two exact Stanford workbooks. Three Chen CSVs and the complete TEC archive were absent. Battery runs 37961776296 and 37964363099 stopped on upstream HTTP 504 before tests. No unchanged-job rerun or denied local TEC request is part of this implementation. Until the existing official acquisition succeeds for all six inputs, a complete cache seed remains unavailable.

Validation: independent review approved the implementation and workflow. The complete local suite passed 718 tests with 7 skipped and 6 warnings in 166.05 seconds. After adding self-contained source-manifest attribution, all 16 focused cache tests passed again. Lint and format checks cover 153 Python files. No local source acquisition or battery solve was added.
