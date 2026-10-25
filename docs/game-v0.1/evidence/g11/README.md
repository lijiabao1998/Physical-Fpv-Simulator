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
