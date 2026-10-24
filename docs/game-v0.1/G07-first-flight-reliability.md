# FPV-G07 First Flight Reliability 1.0

Frozen acceptance before implementation, 2026-10-24. Base main
29fae8e218896f3987bcda0031e22f9e7cc044a9. Scope input reliability,
optional measurement and first-flight instructions only; no physics, map or
research changes. Hardware Xbox/DualSense NOT TESTED, retain Beta.

W3C https://www.w3.org/TR/gamepad/#dom-gamepad-timestamp defines timestamp
as input update time, not a connection heartbeat. Use fresh API presence,
connected flag and valid mapping/data for availability. An unchanged timestamp
alone must not stop a valid controller.

Required regressions: 60 s fixed controls and 10 min continuous input for Xbox
and DualSense API fixtures; held ARM across connect/reconnect, replacement and
clear must require release then a new 600 ms hold at zero throttle. Preserve
disconnect, invalid mapping/data, blur/hidden, pause/retry, device index changes,
calibration/deadzone/sign/storage and the 250 ms frame interruption safety gate.

Diagnostics must be optional and bounded: render FPS/frame time, measured physics
step cost, catch-up count, API-exposed renderer information, calls/triangles and
actual stop reason. No inferred hardware measurements or hidden lift.

Retain the existing 49 unit/numerical tests except explicitly superseding the
incorrect timestamp-staleness expectation with stronger connection regressions.
Retain all 13 published Chromium cases and add real browser API input and
desktop/mobile diagnostics coverage. Python references, fixed dt, replay,
numerical tolerances, clean-source build and physical parameters are unchanged.

Draft PR, exact-head full CI, visual QA, then authorized merge/Pages and public
artifact verification. First-red evidence retained separately before code edits.
