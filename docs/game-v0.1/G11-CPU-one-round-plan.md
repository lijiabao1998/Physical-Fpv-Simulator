# G11 CPU root-cause convergence — frozen one-round plan

Frozen before diagnostic code: 2026-10-25 15:17 UTC.
Owner request: Sentinel_856937f39fd88191b5b3f04e7d9001dc (15:12:59 UTC).
Product anchor: 672bb2fe6b107aafbbb4286323b5de5d91a2556c.
This is a diagnostic-only branch, not a new release candidate. PR10 remains on672.

## Question and existing evidence
The two original1440 first OFF→ON CPU pairs were +21.52%/+30.51%, reverse
pairs -3.27%/+7.78%, balanced means +8.46%/+19.11%. Preserve every original
sample, first-red, image, ZIP and previous green result. Do not average away
the failing pairs. Original first pair follows two screenshots of an already
rendered Ghost; construction/material attachment must not be assumed causal.

## Immutable primary comparison
Use unchanged official player.yml: ubuntu-latest, Node24, locked dependencies,
Playwright Chromium, one worker, retries0, same settings/fixture/camera/120
sample blocks/120s original test limit. All128 unit and original40 browser
cases run unchanged before the additional zz-prefixed diagnostic file.
Original1440 OFF/ON/ON/OFF is the uninstrumented primary measurement. No source,
workflow, existing tests, thresholds, physics, safety, cache or warm-up changes.
Existing browser CI is explicitly the requested environment; no local browser
launch, desktop/saved-environment switch, forcedGC or browserflag changes.

## Separated observations in the same runner
Two new desktop1440x900 fresh-context observational cases, each120s budget:
A: original setup, then OFF/ON/ON/OFF (120frames per block).
B: same setup, then ON/OFF/OFF/ON (120frames per block).
No extra hidden warm-up. Preserve the existing two200ms camera waits/screenshots
as named setup, not discarded measurement samples. All120 frames retained.

Before page load, enable observational CDP V8 GC/user-timing trace and1ms JS
sampling profiler. After normal low-quality/diagnostics UI setup, dynamically
wrap the same Vite module prototypes only in these two fresh test contexts:
- createGhost total, LineBasicMaterial.setValues subtotal and scene-add subtotal;
- first/repeated renderer.render CPU, program/geometry/texture counts;
- GhostPlayback cache hit/miss and updatePose same/new-object counters;
- diagnostics.record's original per-frame CPU values, timestamps and heap value.
Store original per-frame samples, setup/firstGhost events and every block boundary.
Do not edit product modules or touch player state except original local-flight
fixture/pause/UI path. Assert frozen player position/time/splits and fixedLow.
Record browser version, runner CPU/OS/memory, workflow SHA, viewport and order.

Instrumentation overhead is real: wrapper/timer allocation, CDP trace/profiler
and module import can alter CPU, scheduling and GC. These observations are NOT
replacement acceptance numbers and are not directly pooled with primary data.
Heap API is approximate; absence of GC events is not proof of no GC if collection
fails. No forcedGC, exclusions, sample trimming or automatic retry.

## Evidence budget and stopping condition
One diagnostic commit and one official CI execution with the planned conditions;
no reruns for noise. Keep raw GC traces capped16MiB each (explicit incomplete flag
if exceeded), profiles8MiB each and4096 instrumented frame records per case.
Only final existing-40 primary screenshots and observation screenshots; no video.
Download one original CI ZIP, selectively extract small JSON/logs; stream4MiB;
check free disk before transfer and never delete original evidence.
If instrumentation fails, preserve failure and report limited/inconclusive result,
not a second tuning loop. If reproducible causal product fault is demonstrated,
only minimal G11 fix followed by all original tests and exact-head CI is allowed.
Otherwise stop this round, retain CPU reservation, and submit only cause/evidence/
repair-needed/reservation conclusion. No merge/deploy/researchPR1–3/G12.

## Decision rules
Report absolute per-block CPUms and%, both pair directions independently, rAFp95,
draw/program/geometry/texture/heap and execution order. Compare first-frame and
later-frame distributions descriptively WITHOUT removing them from120-frame means.
A constructor/material event absent from warmed blocks cannot explain their cost
as repeated initialization. A coincident GC pause is correlation unless timing
and stack evidence support attribution. Separate one-time event from persistent
ON work and environment/order effects. Unexplained >20% remains unresolved.
