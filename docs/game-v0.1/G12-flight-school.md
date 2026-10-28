# G12 flight school — pre-code candidate acceptance freeze

2026-10-27. Owner source: Sentinel_7309337460b08191a08e3e0e41509211,
Library libfile_dd89aa849d088191baa3bc1f4e584582, uploaded text SHA256
4ce681a3b714cf33d4950262f901e516f72ab7daa249f3acd0f17e90be9d7d0b.
Owner explicitly authorizes isolated G12 planning, design, implementation, testing,
and Draft PR, independently from G11. Base is G10 candidate
c1aed5d999988d0ff07cefde4bc6f36d18e6a19c, not a released G10 claim.
This separate card is committed before school product code. No main merge or
publication authorized; G11 CPU reservation and research PR1–3 stay unchanged.

## Read-only architecture
One bounded observer, no physics/control/score/storage writes, extra rigid body,
autopilot, RNG, asset or network dependency. Feed actual session observations after
each original 240 Hz tick. Observation identity includes course ID/version,
physics model and all four assembly IDs; an object token identifies an attempt.
Reset/retry/course/config change clears ALL school progress. Closing school clears
state. Opening school late cannot recover unobserved arming or completed gates.
Replay observation permanently locks this school attempt; UI also calls markReplay
at replay entry before pause/resume. Only a fresh explicit begin may unlock it.
Safety pause freezes time, cannot finish lessons or count as deliberate disarm.
Crash/invalid course clears progress and requires fresh retry. Duplicate/backward/
nonfinite time and gaps larger than one fixed tick never accumulate progress.

## Frozen provisional candidate lesson conditions
These are bounded TEST difficulty parameters, NOT an approved official game balance.
Owner difficulty/balance confirmation is required before release. Never relax them
after red to make acceptance pass. All existing flight/safety gates stay unchanged.
1. Safe takeoff: observe flying+disarmed throttle <=0.025, then native ARM at zero,
   then armed airborne height >=0.75m without contact; observe gentle throttle
   passage through (0.025,0.35] before liftoff. Finish only on later deliberate
   disarm while state remains flying (pause/safety/crash does not qualify).
2. Hover: armed, contact-free, height 1–3m; within 4m horizontally of school start;
   horizontal speed <=0.75m/s, vertical speed <=0.5m/s; body up within 20 degrees
   of world up; sustain 720 consecutive fixed ticks (3s). A non-qualifying flying
   tick clears that hold. Pause contributes zero ticks.
3. Axes in order throttle/pitch/roll/yaw: 60 qualifying ticks each (0.25s), armed
   and contact-free. Throttle >0.15 with native vertical speed >0.15m/s;
   pitch/roll/yaw absolute command >0.15 and corresponding native angular rate
   absolute >0.05rad/s. Readonly relationship observation, not a pilot certificate.
4. Precision gate: a NEW valid native ordered split after entering lesson4,
   course practice enabled. No independent geometric gate test or forced pass.
5. Course challenge: valid native finished state with exact expected number of
   ordered splits and gates. The same real attempt may complete the remaining
   gates; course switching is a new school attempt, not inherited qualification.

## Acceptance and UI integration gates
Before any release: original reference/unit/build/real Chromium workflow, exact
head; ordinary-control valid lap and full non-Ghost school path. Unit observer
fixtures are logic tests, NOT evidence of actual player flight. Negative controls:
unarmed/illegal throttle arm, insufficient height/hold, pause, crash, retry/config,
wrong/repeated gates, replay pause/resume, nonfinite/large time gaps, deep frozen
input nonmutation. Compare game+observer vs same-input game alone exactly, including
energy, contacts, replay and result. Language switch cannot reset observer.
UI must show all five objectives, current substep/hold, feedback and retry/exit/safe
stop in zh-TW/en. Preserve ARM 600ms, native throttle check, 250ms guard, focus and
controller disarm. Inspect actual 1440/412/390/360px FPV/Chase screenshots without
covering sticks, safety controls or HUD. Physical phones/controllers remain untested.
Retain first failures and raw results. No workflow/threshold changes or hidden
performance waivers; G11 remains independent and blocked until its gate resolves.

## Core-only implementation receipt (2026-10-27)
Card freeze: b529a56, before product code. First implementation/test commit:
89661e9. First focused test run: 9 pass / 1 fail; replay lock was inadvertently
cleared when an imported session replaced the attempt token. Corrected the
observer token-change path to keep replay locked until explicit fresh begin.
Also regression-tested pause → resume cannot impersonate deliberate safe disarm.
Focused rerun: 10/10. Full inherited + school suite: 115/115 (11 files), and
TypeScript noEmit pass. These are local numerical/unit checks, not Chromium/UI,
ordinary-input lesson completion, official CI or hardware acceptance.
Original first-red log SHA256:
68f20ec6ddf5815ec882cbacbc16762ca0253893b6d4d8802fe6cf802cdd7943.
Full unit log SHA256:
5363ef658e3304f3d402823b7e7daec4254c942025644dabd3691479144289aa.

### Integration contract
`FlightSchool` owns no language, storage, game or renderer object. UI supplies:
`{...game.snapshot(), controls:game.lastControls, contact:game.world.contact,
practice:game.practice, gateCount:getCourse(game.courseId).gates.length,
assemblyKey:JSON.stringify([game.assembly.frame,game.assembly.battery,
game.assembly.motor,game.assembly.propeller])}`.
Call `begin(game.course, observation)` on school start and explicit fresh Retry;
`observe(game.course, observation)` after EVERY native fixed tick and immediately
after native ARM/disarm/pause actions (including keyboard/gamepad). `markReplay()`
at replay entry; successful import must not call begin, even when its course token
changes. Call `stop()` when exiting school. Reset/reconfiguration auto clears on
new course token/identity, but a Replay-locked session requires explicit fresh
school retry; do not relabel imported playback as a local attempt. Language only
reads `snapshot()`. No need to translate internal lesson/axis/identity IDs.
All native controls, including 600ms hold and existing safeStop, remain in charge.

### Native input-only feasibility receipt
An additional test-only normal-control navigator completes ALL five lessons in
5622 commanded ticks plus the initial gentle-throttle tick (23.4291666667s native
simulation), Training Straight 5/5 gates, native finished state. No transform,
force, mass, physics, threshold or gate writes. Native disarm/rearm happens at
lesson1→2, and all later ticks go through the original motor mixer/Rapier world.
Stage tick counts: takeoff291, hover990, axes291, first gate799, challenge3251.
This establishes candidate conditions are reachable in the native model, NOT
human difficulty acceptance. Original command stream, transitions, endpoint and
school state are emitted as numerical-results/g12-school-flight.json. The helper
exists only in the unit test; it is not a player autopilot. Focused final suite
11/11 plus strict TypeScript passes. UI/Chromium and exact final candidate CI remain
integration gates; owner approval of provisional difficulty remains outstanding.

### Integration review before first official browser run
Independent review found free-flight entry retained practice=false and exit did
not enter free-flight mode. Both fixed through existing reset(assembly, practice),
not physics changes. School starts a fresh disarmed practice attempt; exit starts
fresh disarmed free-flight. Mobile panel now anchored above sticks and includes
explicit no-overlap assertions for sticks/actions/HUD/language. Real screenshots
must still verify layout; TypeScript is not visual acceptance. UI observes every
fixed tick without deep-cloning full snapshots; inactive school reads no world.
Native original 600ms ARM handler unchanged; development-only scripted fixture
uses normal controls/native actions and is not human flight or production autopilot.

### Mobile school/course overlap receipt (2026-10-27, Claude)
Defect (GPT real-image review; its unpushed CSS draft was not available): at phone
widths the open `#school-panel` covered `.course` (name, selector, title, clock, gates,
splits). The G12 e2e only checked sticks/actions/HUD/language, so CI 40447850363 stayed
green at 74ef387. Local real Chromium (pinned Playwright 1.64.1 driving the preinstalled
headless shell 153; CI uses 156), 70 views at 74ef387: fine 1440 and 412/390/360x900,
coarse touch 360/390/412x800, zh-TW/en, lesson 1 on all three courses, completed school,
completed + legacy record. 33/70 overlapped, only `.course` and its lines: every coarse
view (12454-40740 px²) and fine 412/390/360x900 at the longest zh-TW text (1680-1940 px²).

First red: 825a2bb, test only, appends `.course` to both existing overlap lists.
`npx playwright test e2e/g12.spec.ts`: 4 failed / 4 passed; coarse 360/390/412 `.course`
14879.25 px² (expected); 1440 failed earlier at the inherited 200 ms Space check
(armed=true), timing before the new assertion. One rerun: 6 failed / 2 passed (same
coarse red; 1440/412/390 same Space line). Log SHA256 9009c777..., 26974b5d....

Fix: 90c06e3, CSS only, max-width 600px. The panel keeps a band 357px above the bottom on
coarse pointers (unchanged, above sticks) and 275px on fine pointers (above notice/
actions). While it is open the course panel keeps its place, is capped to
`100dvh - course top - band - 135px - 8px` and scrolls inside. 1440 rects identical. No
markup, physics, input, ARM 600 ms, 250 ms guard, threshold or workflow change.

Results at 90c06e3: `npm run reference` pass; `npm test` 15 files / 135 tests pass;
`npm run build` pass (dirty=false); G12 spec 8/8 pass (log fbefdf4f...). After matrix
70/70: zero overlap with `.course` (visible lines), sticks, actions, HUD, language,
header; panel inside viewport; no horizontal overflow. Full `npm run test:e2e` once:
40 passed / 18 failed (log b6513e6f...) in G08/G10/I18N/player and G12 412 Space line,
while a sibling Chromium job held load near 7.8 on 4 CPUs; failed pages show the
product's own "Frame interruption over 250 ms" pause. Rerun of those 18: 3 passed / 15
failed (log 4a847277...). Control at unmodified 74ef387: player.spec:10 and g10.spec:27
fail the same way (log 7f14e0af...). Not green locally; exact-head official CI required.

Still open: on coarse 800px-tall phones the course panel shows name, selector, title,
clock, gates and best; class/splits/legacy/input status/school button scroll inside it
while school is open (owner visual review). Landscape coarse 800x360/844x390 (width >600
desktop rule) still overlaps right stick, actions and notice: pre-existing, outside the
frozen matrix, not fixed. 360x640 leaves the course panel 42px tall. Physical phones and
controllers remain untested; owner difficulty/balance review remains outstanding.

Independent verification of the receipt above (2026-10-27, separate Claude agent, not
external review): scope is exactly 3 files; the frozen text above is unchanged. Provenance
correction: the first-red log was produced on 74ef387 plus the then-uncommitted spec edit,
byte-identical to 825a2bb; rerun on a clean `git archive` of 825a2bb gives 3 failed /
5 passed with the same coarse `.course` 14879.25 px² (log d20162fa...). Its own probe over
17 viewports (153 states each side) reproduced the 30/63 before-overlaps in the frozen
matrix and found 0/63 after, with no new or larger overlap anywhere and identical 1440
rects. G12 spec at d72bd71: 7 passed / 1 failed twice, the inherited 412 Space 200 ms
line under load; 412 alone passes at head and fails at the base copy (timing, not this
change). Remaining risks it measured: (1) while school is open on coarse narrow screens
below about 746 px of visible height, clock and gates also scroll out of the course
panel (375x667 cap 71 px); at 320x568 the cap is 0 px and the panel still overlaps the
course 7696 px² (34040 px² before). (2) Pre-existing and safety-relevant: in landscape
800x360 the visible school Safe stop/Retry buttons sit under `#arm`, and Close under
`#disarm` or the right stick, so a tap on Safe stop presses Hold ARM. (3) Pre-existing:
widths 601-704 px still overlap the course panel under the desktop rule. (4) The fix
needs `:has()` and `dvh`; without them the cap is skipped and the old overlap returns.
Items (1)-(3) need an owner decision or a separate card before release.

## Release integration receipt (2026-10-28, Claude)
Owner decision 2026-10-28, relayed to this step by the orchestrating Claude session
(no owner message ID was available to this step): 「G10＋G12 一起上」. Option text:
also accept G12's provisional difficulty; integrate both, merge in order after CI is
green, and publish; the landscape "Safe stop under ARM" issue gets a separate card.

Difficulty: the owner accepts the five provisional lesson conditions, exactly as frozen
above, as the difficulty of this release. This is the owner difficulty/balance
confirmation the frozen section requires before release; no condition, threshold or
frozen sentence is changed. Item (2) above, landscape Safe stop/Retry under `#arm`, is
deferred to a separate card by the same decision and is not fixed here. Items (1) and
(3) above are not named in the relayed option text; they stay open and disclosed.
Physical phones and controllers remain untested.

Local branch g12-int: G12 head 0e4bb23 (PR #12) plus a real merge of g10-int 64fa242
(G10 02b2455 with main 8aae927's /fpv/ base; see the G10 card): merge commit d58ad51,
parents 0e4bb23 and 64fa242. Clean automatic merge, no textual conflict; main.ts
auto-merged with main's source link and every G10/G12 change; the tree is G12 plus
g10-int's delta over G10 exactly. Follow-up 150923d moves the G12-added g12.spec.ts
root from /Physical-Fpv-Simulator/ to /fpv/; no assertion, timeout or threshold
changed. No tracked file under web/ names the old base. No G11 commit, patch or file:
checked against origin/game/g11-personal-best-ghost and g11-cpu-one-round-20261025.

At 150923d (Linux cloud container, Node 22.22.0, Python 3.13.17, NumPy 2.3.5; CI uses
Node 24 and Python 3.12): npm ci pass; npm run reference pass, fixtures byte-identical;
npm test 15 files / 135 tests pass (twice); CI=true npm run build pass (strict tsc,
vite, check-build: base /fpv/, dirty=false, og.jpg in dist). Not run in this step: real
Chromium e2e including g12.spec.ts, exact-head official CI, Pages. Earlier official
results at 0e4bb23 do not carry over; the frozen exact-head workflow is still required.

## Owner release decision 2 (2026-10-28, Claude)
Owner decision 2026-10-28, the owner's answer to Claude's question, relayed to this step by
the orchestrating Claude session (no owner message ID was available to this step). Option
chosen: 「已知問題隨版上，文案一併改」. Option text: "(1)(3) 寫進卡面當已知問題，和橫向安全停止
一起另開卡；文案改成「教學課程 · 暫定難度」（英文 Lessons · provisional difficulty），推上去跑 CI，
綠了就合並發布". It follows 「G10＋G12 一起上」 above; frozen conditions stay unchanged.

Known issues shipped with this release, not fixed here; all three go to one separate
follow-up card (not opened in this step):
(1) Short coarse screens scroll clock/gates inside the course panel while school is open;
    320x568 still overlaps the course 7696 px² (34040 px² before the fix).
(3) Widths 601-704 px overlap the course panel under the desktop rule (pre-existing).
(2) Safety-relevant, pre-existing: in landscape (800x360) Safe stop/Retry sit under `#arm`,
    so a tap on Safe stop presses Hold ARM.
Item (4) above (`:has()`/`dvh`) is not named in the option text and stays disclosed above.

Copy change, the only product change: the school panel line in web/src/main.ts "Candidate
lessons · difficulty awaiting owner review" → "Lessons · provisional difficulty"; its
web/src/ui/i18n.ts entry → "Lessons · provisional difficulty|教學課程 · 暫定難度". grep of web/
(src, tests, e2e): no other occurrence; no test asserts this line or a dictionary count
(tests/i18n.test.ts round-trips every entry). No CSS, markup structure, physics, input,
ARM 600 ms, 250 ms guard, threshold, lesson, test or workflow change. The receipt label
`difficulty:'provisional owner review required'` in e2e/g12.spec.ts is test metadata, not
product text; unchanged.

Checks on 2e4b23b plus the copy edit, before this text (Node 22.22.0, Python 3.13.17, NumPy
2.3.5, Playwright 1.64.1 driving a preinstalled Chrome 153 headless shell; CI: Node 24,
Python 3.12, Chromium 156): `CI=true npm run reference` pass, fixtures byte-identical;
`CI=true npm test` 15 files / 135 tests pass (log 349e1cfd...); `CI=true npm run build`
strict tsc and vite pass, then check-build stopped at its CI clean-tree assertion
(dirty=true, edit uncommitted: expected); that bundle holds the new en/zh strings and
neither old one. Then `CI=true npx playwright test e2e/g12.spec.ts e2e/i18n.spec.ts` (dev
server + preview of that dist): 20 passed / 0 failed (G12 8, I18N 12), first run, 6.8 min,
no rerun (log 737418b5...).

Screenshots 360x800 hasTouch/isMobile on `npm run preview`, school open at lesson 1, zh-TW
and en switched in place; viewed. The new line shows once the panel is scrolled: at 360x800
and 320x568 the 135 px panel's sticky button row covers it at scrollTop 0 (zh-TW line y
408-422 under row 403-433; en all but 3 px), exactly like the old line at 2e4b23b; 27/17 px
of panel scroll reveals it. The 1440 e2e screenshot shows it unscrolled. Against a scratch build of 2e4b23b at 360x800 and
320x568, both languages: 0 of 124 element rects differ, same overlaps and scroll sizes;
360x800 pixels differ only inside the line's box (zh-TW 0 px unscrolled). 320x568: panel
overlaps the course 7696 px² in both languages and the header 296 px² in zh-TW, same at
2e4b23b.

Also seen, pre-existing (same at 2e4b23b), outside the frozen matrix, for the same
follow-up card: at 320x568 coarse in zh-TW the welcome Start button (y 378-425) lies under
the fixed `.actions` bar (y 369-436); a centered tap hits `.actions` (my first screenshot
run timed out there; log kept). en is unaffected.

Not run here: full `npm run test:e2e`, exact-head official CI, Pages. A card cannot record
its own commit's build; the post-commit `CI=true npm run build` (dirty=false) is in the
hand-off. Physical phones and controllers remain untested.

Follow-up card opened (2026-10-28, Claude): docs/game-v0.1/G13-mobile-school-layout.md
records (1), (2) and (3), the 320x568 zh-TW Start/`.actions` overlap, the copy line
covered at scrollTop 0 and the stale e2e label, with acceptance frozen before code. It
is not started; the owner sets its priority.
