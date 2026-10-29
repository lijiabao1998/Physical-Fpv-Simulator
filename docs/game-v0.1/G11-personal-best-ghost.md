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

## Port receipt (2026-10-29, Claude)

Appended after the frozen lines 1–60, which are unchanged (sha256 2b3dbbb2…dc26). Owner decisions: 「Fpv baa g11」 (2026-10-28) and the release bar 「美術過得去，人可玩流暢玩狀態就行」 (2026-10-29). The release fixes are frozen in [G15](G15-pb-ghost-release-fixes.md).

**Base moved.** Lines 55–57 planned a Draft against G10 with no G12, no merge and no Pages. G10 and G12 have since been released on main (f30b3e1, fcc4c46), and G13 merged as 125f9fa. G11 is ported onto that main on purpose.

**Port.**
- `e780384` is a real merge, not a rebase, cherry-pick or squash. Its first parent is e0c6d87 (this card's head) and its second parent is main 125f9fa. The ancestry freeze 8c5c8fb → first red b00b68e → product b1c8283 stays in history.
- Conflicts in `web/src/main.ts` (3 hunks) and `web/src/ui/i18n.ts` (2 hunks) are resolved as statement-level unions by [`apply-g11.mjs`](evidence/g11/port/apply-g11.mjs). Every anchor must occur exactly once. Main's G12 and G13 code and G11's code are both kept, and G12's DEV `schoolTick` hook also calls `ghostRecorder.observe(game)`. `style.css` auto-merges.
- Gates: [`strip-check.cjs`](evidence/g11/port/strip-check.cjs) prints "stripped === ours: true"; 0 conflict markers; `tsc` exit 0; 247 unique i18n entries (239 on main); the diff against main lists exactly G11's 27 files of 02b2455..e0c6d87; `npm run reference`, then `npm test`: 18 files, 154 of 154 (main's 135 plus G11's 19). These are local checks; exact-head CI is the gate.
- `f793cd0` (test only) serves `web/e2e/g11.spec.ts` from /fpv/ on lines 3 and 58, as 2fbf85c and 150923d did for G10 and G12. The e0c6d87 spec with `/Physical-Fpv-Simulator/` replaced by `/fpv/` is byte-identical.

**Inherited files, restated for base 125f9fa.** The evidence README (lines 76–77) says "The 39 original … files are byte-identical to G10". That was written for 672bb2f against c1aed5d and no longer holds as written. The binding line 39 ('Keep every original G07–G10 test/threshold …') is unchanged. Restated:
1. At the port head, `git diff --name-only 125f9fa HEAD` lists only G11's 27 files. G15 may add the files its card names.
2. Every other tracked file is SHA256-identical to 125f9fa. The 39 files are listed with full hashes at c1aed5d, e0c6d87 and 125f9fa in [`inherited39-sha256.txt`](evidence/g11/port/inherited39-sha256.txt).
3. Against G10 c1aed5d, 34 of the 39 are identical. The other 5 changed only in released commits that are not G11's:
   - `g08.spec.ts`, `g09.spec.ts`, `g10.spec.ts` and `player.spec.ts` carry the `/Physical-Fpv-Simulator/` → `/fpv/` swap (8aae927, 2fbf85c). Applying that `sed` to the e0c6d87 file gives the 125f9fa file byte for byte.
   - `g09-race.test.ts`, `g09.spec.ts` and `g10.spec.ts` gained lines (85d15fa, 1601126). After the swap, numstat from c1aed5d is 27/0, 13/0 and 12/0: no line was removed, so no assertion or threshold was dropped.
4. `FIXED_DT` 1/240 and the 250 ms guard are unchanged: `timing.ts` and `config.ts` are among the identical files, and `planPhysicsSteps(0,.251,true).steps===0` passes.

**Runs missing from the earlier receipts.**
- e0c6d87, green: push run 40445940089 and PR run 40445946110, 142 unit and 61 Chromium tests each. The 1440 first pair was +28.16 % and +31.57 %; the reverse pair +1.90 % and +8.74 %.
- 709917a, red: runs 40439970023 and 40439975943.
- Across 7 runs of the same render code since 672bb2f, the 1440 first pair exceeded 20 % in 6. The cause is unresolved. The CPU reservation stays on record; under the owner's 2026-10-29 bar it ships as a known issue (G15).
