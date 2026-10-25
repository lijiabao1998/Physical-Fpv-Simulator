# Bounded HTTP lifecycle diagnosis: historical Win10053 unresolved

The original ten GUI integration and mocked-browser tests pass in the final authorized localhost run:10 passed in2.52 seconds, runner wall3.078 seconds, exit0. **There is no production or original-test change and no claimed fix.** Historical Win10053 remains UNRESOLVED: it was not reproduced in this permitted comparison, and its exact cause has not been established.

Work occurred only in `fpv-http-lifecycle`, branch `fix/public-lab-http-lifecycle-20261012`, based on `ee5ca8ada4542cb3ad985ba07971b9fe02b42cf5`. Main science work, parameters, gates and old results were not edited. No fourth GUI run, fit, new scientific solve, source acquisition, push, merge or deployment occurred.

## Evidence and the bounded amendment

The [original plan](public-lab-http-lifecycle-protocol.json) and copies of both old failures were committed as `d9ac41e9a6b92e473c3f9dbbeb57ed74ea05c67c` before new execution. [The amendment](public-lab-http-lifecycle-evidence/diagnostic-amendment.json) separately records the permission contrast and controlled counterexample; it retains the frozen original plan.

| Run | Actual result | Interpretation |
| --- | --- | --- |
| Historical GUI/browser final-r2 |9 pass,1 Win10053 failure on rejected cross-Origin `/reset` before status parsing | Preserved unresolved failure. |
| Historical GUI/browser recheck-r2 |9 pass,1 Win10053 failure | Preserved; not replaced by a later pass. |
| pre-01, restricted exec |9 pass,1 failure: Win10013 on initial GET `/state`; pytest4.86s, runner6.016s | Loopback permission blocked the request before the historical POST. Not a Win10053 reproduction or evidence of an application defect. |
| pre-02, authorized controlled split-send |1 diagnostic failure; pytest0.91s, runner1.312s. Client nevertheless received403 with correct JSON | Fails only the probe's body-consumption expectation0==2. The HTTP status/security result succeeds; no Win10053. |
| amended-03, authorized original-ten comparison |10 pass; pytest2.52s, runner3.078s | Original assertions pass under this declared condition. Not a causal proof or a code fix. |

Every started job used `run_fpv_serial.py` and its atomic lease around `run_bounded.py`: one core, IDLE priority, single-thread library settings,120-second test limits and observed Lean/Lake coordination. All three test receipts record no timeout, no initial observed CS process and no pause. Other normal-priority publishing work retained priority. This observer does not prove the absence of all other workloads.

The first restricted run demonstrated a command-permission problem. The subsequent two localhost commands used explicit execution permission already authorized for this bounded task. No Windows firewall, network policy, browser security or other system setting was changed. These execution conditions are disclosed because silently pooling the outcomes would be misleading.

## What the controlled request establishes

The baseline handler checks Origin before reading the body. Local CPython3.12.11 source also shows that its client sends headers and body separately, while `TCPServer.shutdown_request` shuts down writing and closes the accepted socket. That makes a timing-dependent unread/late-body closure a plausible hypothesis, but source inspection alone does not prove it caused Win10053.

The single controlled probe sends headers, waits until handler entry, sends body`{}`, and waits for server-side shutdown before parsing the response. Its observer confirms zero application body reads and two queued kernel bytes before the403 response. Nevertheless, the client successfully reads403 and `{"error":"Cross-origin requests are disabled"}` after shutdown. This is a counterexample to treating unread bytes alone as sufficient proof of the historical transport failure in that tested ordering.

The probe deliberately changes timing through finite event barriers and MSG_PEEK. It is distinct from ordinary-suite reproduction. The host's timestamp clock is coarse: the phase list supports event order, not nanosecond latency or packet timing. No packet-level reset trace was acquired. A different late-body ordering, transient execution condition or another cause remains untested and unassigned.

The probe's failed assertion expected the body to have been consumed. That expectation was part of the diagnostic hypothesis, not an original HTTP/security acceptance requirement. It cannot justify changing production to make an invented assertion pass. Its exact source, failed assertion, raw trace and XML are preserved as historical diagnostic artifacts; it is not introduced as a permanent CI gate. No assertion is relaxed to turn that result green.

## Disposition

There is insufficient causal evidence for a production fix, so the server was left unchanged. Original cross-Origin rejection,4096-byte request limit, JSON validation, loopback binding, transactional controls/reset behavior and all original assertions remain intact. The final ten-test pass does not identify the reason for the two old Win10053 failures or eliminate an intermittent risk.

This work delivers a bounded diagnosis and evidence, **not HTTP-fix acceptance or science acceptance**. Mocked DOM/Gamepad checks remain mocked; no real browser, device, flight or calibrated physical accuracy is claimed. Original calibration/cutoff FAILs, known-regression limits and pending external validation are unaffected.

The unresolved blocker is an attributable reproduction of historical Win10053 under a declared execution condition. The finite authorized comparison is complete; no further HTTP attempt or hypothetical production repair is performed in this round.

## Reviewable artifacts

[Evidence overview](public-lab-http-lifecycle-evidence/README.md), [exact prechange server](public-lab-http-lifecycle-evidence/prechange-server-source.py.txt), [exact executed probe](public-lab-http-lifecycle-evidence/prechange-test-source.py.txt), [amended XML](public-lab-http-lifecycle-evidence/gui-r5-amended-03.xml), and the complete [run receipts/output](public-lab-http-lifecycle-evidence/runs/) are retained. The original two raw failures are under `original-r2/`.

Final byte identity and hashes are recorded in [integrity.json](public-lab-http-lifecycle-evidence/integrity.json); [publication manifest](publication-manifest.json) seals the new evidence. Those checks and local submission also use the shared serial lease. The delivery contains no production diff.

The first metadata seal verified all840 baseline files exactly, source copies, old logs and all three XML outcomes, but its generic staged-whitespace check rejected the exact CRLF raw stdout. It stopped before calling Git commit. That helper and failure receipt remain. The corrected seal checks authored code/Markdown/JSON while preserving raw logs byte for byte; it does not rerun GUI or the full840-file computation. This bookkeeping failure is distinct from both Win10013 and historical Win10053.


Publication note: this is the completed local diagnosis; no GUI rerun or fix was performed for publication. Host paths are redacted, original hashes are retained, and large/redundant bookkeeping output is omitted.
