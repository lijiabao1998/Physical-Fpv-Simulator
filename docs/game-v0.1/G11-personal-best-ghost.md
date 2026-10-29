# FPV-G11 — Personal Best Ghost: frozen acceptance

Frozen before product code, 2026-10-25. User request Sentinel_5361959d9e708191b8f36111bcc164d4.
Exact base: G10 c1aed5d999988d0ff07cefde4bc6f36d18e6a19c (PR #9, open Draft),
stacked on G09 956130a4a6c8b40f423fd754fc04212e23bdb3df (PR #8, open Draft).
Main remains released G08 ce51a64a711b1c1760f87a5b9848b27ac5383a89.
G10 exact-head evidence: 110 unit/numerical and 32 actual Chromium cases, both
push/PR evidence inspected. This is a candidate, not a G09/G10/G11 release.

## Single frozen product loop
Fly → finish a valid local lap → save PB → retry → see that PB Ghost → compare
ordered gate splits → improve PB. Me vs Me only, on all three existing courses.
ON/OFF, class PB time, per-gate player/PB elapsed and signed delta. No continuous
delta or nearest-path estimation. Gate 1 anchors both lap timelines; before Gate 1
the Ghost waits at its start gate. Pause freezes simulation time; retry resets it.

## Hard invariants
Ghost is a read-only pose timeline derived from the player's fixed-step simulation,
never a Rapier body, collider, control input, force, RNG consumer or scoring actor.
No second simulation in the render loop. Capture bounded samples independently of
render batching; interpolate visuals only. Strict course ID AND version, physics
version AND all four exact assembly identifiers; never infer legacy identity.
Only valid, completed, local attempts can create/replace a PB Ghost. Imported or
watched replays remain non-recordable even after pause/resume. Crashed, unfinished,
invalid and repeated completion cannot replace records. Save failure retains old
bytes and must not display a Ghost mismatching the current PB. Existing record keys
and legacy bytes remain unchanged. Existing PB without poses means no matching Ghost.

## Bounded schema/visual plan
Versioned local Ghost namespace stores explicit identity, total/splits, fixed dt,
source build, fixed-tick pose sample timestamps and position/quaternion. Maximum
10-minute source / 36,002 pose samples; maximum serialized size 4 MiB; quota errors
fail safely. Source inputs are the existing validated replay stream; pose observer
never writes player state. No external asset, particle, shadow or new texture.
At most two visual draw calls, 200 triangles, two geometries, zero textures for Ghost.
Transparent emissive/wire outline; near-overlap fades rather than obscuring FPV gates.

## Binding acceptance
Keep every original G07–G10 test/threshold, physics/config/reference fixture and
240 Hz dt. Keep 250 ms interruption guard. Add first-red unit and browser evidence,
strict identity negatives (96 classes plus version), malformed/legacy/oversize/quota
negatives, full input-only completed lap capture vs exact replay poses/results,
60/20/5 Hz alignment, pause/reset/retry/course switch, imported-replay nonpollution,
crash/unfinished/repeated completion, and Ghost ON/OFF exact player-result/energy/
contacts/events/splits/record equality. No test-only placement is a claimed real lap.
Actual Chromium 1440/412/360 in FPV and Chase; raw PNG inspection, HUD bounds, native
fly→PB→retry→Ghost loop, reload, toggle, configuration mismatch, import safety.
Same-condition Ghost OFF/ON CPU/frame intervals, draw calls, triangles and memory.
Retain inherited absolute performance limits; explain environmental variability.
If repeatable render CPU or frame p95 regression exceeds 20%, diagnose before review.

## Process and release boundary
Original source/evidence read first; freeze this card before product changes. Preserve
all first reds. Fix root cause or test wiring, never physics or acceptance thresholds.
Focused tests then complete exact-head unit/build/Chromium verification. Draft PR
against G10 only, immutable evidence/preview and explicit ancestry. No research PR
1–3, no G12, accounts/backend/multiplayer/sharing, no merge, no Pages deployment.
Physical Xbox/DualSense USB/Bluetooth, physical phone and real aircraft/battery remain
unverified. Software browser testing does not change those labels. Owner release
review is a later gate, never implied by implementation or passing CI.
