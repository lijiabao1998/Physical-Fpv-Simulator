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
