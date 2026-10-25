# G11 incremental evidence

Original authorization read completely from owner message
Sentinel_5361959d9e708191b8f36111bcc164d4. Own-cloud workspace only.
Exact remote PR #8/#9 heads and Draft/unmerged status were checked before branching.
Local freeze eb94de04 and identical published freeze 8c5c8fbb precede product code.
Remote test-only b00b68ef preserves real Chromium missing-control first red, with
all inherited G07–G10 source/tests unchanged. No product code is in that first-red
commit. No researcher branch, main merge, or Pages deployment was touched.

first-unit-red.log: two expected initial failures, missing sticky replay provenance
and absent Ghost module. Product reads uncovered a real inherited isolation gap:
HUD previously saved any course.finishedAt, including imported playback. A sticky
import flag now prohibits imported/watched replay from saving class PB/Ghost even
after pause/resume. Explicit retry starts a genuinely new local attempt. This does
not modify forces, integration, controls, collisions, gate math or replay results.

Initial expanded tests: 123/123 passed (all inherited 110 +13 G11). Strict build
then identified four unused imports in the new test file; removed, without changing
assertions. Focused 13 G11 checks and subsequent strict build pass locally. Browser
verification remains pending, not inferred from that result. Source files under
physics/, input/, course geometry, timing and all prior tests remain unchanged.

Pose observer samples the already-simulated player every four 240 Hz ticks plus
terminal tick, retaining float64 JSON positions/quaternions and integer sample
indices. Source duration bounded to 144000 ticks / 36002 samples; persisted UTF-16
budget 4 MiB. It never runs a second world. Gate 1 interpolation anchors playback to
lap time, not wall clock/render callbacks. Quaternion interpolation is visual-only
normalized shortest-arc lerp. Runtime import never upgrades a replay to local origin.

Records are a separate schema and are accepted only if total AND ordered splits
match the current G09 PB key with exact course ID/version, physics and all four
assembly fields. No legacy assembly is inferred. On storage quota/serialization
failure, normal PB semantics remain; mismatching old Ghost is rejected, not shown.
Replay/pose source build is informational; physics/course identity retains its
existing explicit version contract. No cross-platform bitwise promise is added.

G11 numerical-results fixtures are synthetic ordinary-input flights through the
unchanged motor mixer and Rapier, with no body/force corrections. Browser's dev-only
localInputFlight helper resets/arms using existing session methods then supplies
that input stream; it is not production autopilot and not human/controller proof.
Production build must expose no test API. Hardware Xbox/DualSense USB/Bluetooth,
physical phones, aircraft and battery remain unverified.

## Actual first browser evidence and bounded test-wiring repair

Test-only b00b68ef run 40193376307: inherited 110 unit and all 32 inherited real
Chromium cases passed; the sole new missing-Ghost-control test failed as intended.
Artifact 12599032235 SHA256 fc1be5b07fb91d799530be6dce3be606c11b585f77993ebfc40ce2ad795b7aa4
retains original screenshot/trace/logs. No product code was in that commit.

First product b1c8283 push run 40194075426: 124 unit and 37/40 actual Chromium
passed. All 32 inherited cases passed. Original artifact 12598549825 (74,439,601
bytes; SHA256 740bc6787b6bfff55d0d0b1e8f8c981bee67804d9556ec835b747b2cc24d8cb7)
is retained unchanged. New 1440 case ended OFF/ON A/B in OFF, then incorrectly read
null visual pose after retry. Explicit native ON before that assertion repairs
wiring, not the product. At 412/360, exact trace shows Auto promoted from Low to
High during the last OFF sample; shadow textures increased by two. The new test
now selects existing manual Low before measuring and asserts identical quality
for every sample. Texture/draw/geometry limits remain unchanged; no performance
regression is hidden by loosening a threshold. first-ab-quality-confound.json
contains the original trace's decoded metrics, including both quality labels.

Actual first images were inspected: HUD fits 360/412/1440, but a faster player left
its slower Ghost behind the camera. Revised screenshot setup first completes the
slower actual local lap (41.9962958223 s), improves it with the faster local lap
(35.9691254598 s), and then flies the slower ordinary input stream to chase that
faster PB. At lap 10.5 s, gate 2 delta is +1.0142589494 s and both camera frusta
contain the Ghost. A test-only camera reset matches native retry semantics.
No player body/force correction is used. New actual images still require review.

Replay verification was strengthened to compare every captured pose sample against
the replayed player's position and quaternion at 60/20/5 Hz batches. Fourteen G11
unit cases plus all original 110 pass. Added browser-native imported pause/resume
provenance check and raw A/B attachment before assertions, so later failures retain
measurements. The 39 original physics/input/reference/course/record/timing/test/
workflow files are byte-identical to G10; independent SHA256 receipt is delivered.

Independent review of the unchanged FlightDiagnostics implementation found its
render CPU mean covers a rolling 240-frame window. Ninety-frame A/B blocks produce
valid isolated rAF intervals but can mix the previous toggle state into CPU means.
The G11-only test now samples 300 frames per block and requires all 240 diagnostic
slots, so final CPU means contain only the current state. No physics/product code,
quality budget, threshold or inherited test changes. The earlier exact-head runs
are allowed to finish and retained rather than canceled or silently replaced.

8226613 push run 40195132895 passed 124 unit and all 40 actual Chromium cases;
Pages/deploy skipped. Artifact 12600260296 SHA256
39097623b4ff3b6d56677d38d065b36de0554f42dc4e107f0536150cd177506f retained.
Actual raw-image review (not just green assertions) found pale Ghost-on-sky
contrast and partial 360 Chase HUD occlusion: waiting for the asynchronous
Playwright pause click advanced the sampled lap from 10.5 to 10.78–11.28 s.
The screenshot fixture now invokes the existing native pause-button handler
in the same callback as the final supplied control, freezing the chosen node.
The unlit wireframe is a deeper cyan with tone mapping disabled for contrast;
no geometry/body/physics or alpha fade rule is added. New real images must still
be reviewed. Test-only synthetic inputs are not manual pilot/hardware proof.

ef630fe push 40196104180: 124 unit +40/40 Chromium passed, all six primary
images manually inspected with clear Ghost and exact 10.50s lap node. PR run
40196108961: 124 unit +39/40 Chromium; sole1440 test exhausted its unchanged
120-second whole-test budget at the final reload/course select, after all
1200 sampled frames, visual/PB/isolation assertions and A/B attachment completed.
Artifact12599663214 (78,930,132bytes), SHA256
1f2bedb964f63aad64dcf26048194f287b89cac9e6846c4f7b9cf689002221e2 retained.
Its complete same-condition desktop OFF/ON p95=66.8/66.7ms and CPU=.572/.584ms;
mobile p95=33.4/33.4ms. No repeated >20% Ghost regression in the two300-frame runs.
To remove redundant waiting rather than relax the timeout or rerun until lucky,
the G11-only harness now resets optional diagnostics through its existing native
checkbox change handler before each120-frame block, then returns metrics in that
last rAF callback. It asserts exactly120 diagnostic samples, isolating CPU without
waiting to evict240 old frames. This handler changes no player/physics/storage.
Same scene/quality/order, full native functional flow, every assertion, the
120-second timeout, all inherited tests and product source remain unchanged.

191aaf3 push40197785898 and PR40197789366 both passed124 unit and40/40
Chromium; each A/B block asserts exactly120 independent diagnostic samples.
All screenshots are real and retained. Short-window CPU1440 +21.9%/+19.1%
and360 +21.6%/-11.7% are noisy but near/exceed the frozen20% diagnostic line;
absolute ~0.1ms and unchanged p95 are context, NOT a waiver. Raw comparisons
are in pre-cache-120-frame-comparison.json and both immutable CI ZIPs.
Review found genuinely redundant work: every paused render searched/allocated
an identical Ghost pose and re-applied the same visual transform. A bounded
single-entry record-identity+simulation-time cache now reuses that pose; explicit
course/reset unload clears it, and the renderer updates the Ghost matrix only
when the pose changes. No physics, sample data, opacity/geometry or A/B method
changes. The new cache test's original missing-constructor red is retained, then
checks10000 repeated reads, time advance, replacement identity, reset/unload, and
no saved-record mutation. All15 G11 plus original110 unit tests pass. Exact-head
full Chromium and the unchanged20% performance review still remain required.
