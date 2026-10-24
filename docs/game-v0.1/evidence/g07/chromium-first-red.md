# G07 first real Chromium run

Head ec86e6b, PR run40097440683/job120882531726:56 unit/numerical
checks and clean build passed; Chromium10/17 passed,7 failed. Original tests
are unchanged. Artifact12561846098 ZIP SHA256
7f04a1b8ce65d1c501d813f67b0c35ddeee7fb7165837799fcf67bd5a27da06d retained.
Actual screenshot reports181.1ms mean frame interval,0.84ms render CPU submission,
physics0ms while paused,75calls/27164triangles. Multiple failure contexts report
250ms frame interruption. This does not isolate GPU time from runner scheduling,
nor establish hardware performance; pixel cost is a testable optimization hypothesis.

Auto low now conservatively caps render pixels at480k while preserving aspect,
MSAA, allgeometry and physics. Manual High/Low remain available; mobile360 native
resolution is unchanged. No simulationdt, fail-safe, test timeout or tolerance
changed. Actual follow-up Chromium comparison remains required, not claimed green.
