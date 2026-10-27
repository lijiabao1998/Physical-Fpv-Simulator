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
