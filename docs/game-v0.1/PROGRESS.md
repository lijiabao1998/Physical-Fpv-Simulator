# Physical FPV v0.1 construction record

Authorized scope: browser flight game in this repository only; Draft PR first;
merge and public GitHub Pages only after required acceptance and repository rules.
No research PR merge, history rewrite, force push, paid service or combat content.

## Frozen intake (2026-10-24 UTC)

| Ref | Observed SHA | State |
| --- | --- | --- |
| main | 38a7db9edd103c3ae0a4c6cfaaa35a452c6b4f7c | Initial README |
| PR 1, battery/research-core-v1 | 1990e23ce35b16d73d2d65b0d9a586064963dd6a | Open Draft |
| PR 2, candidate/fpv-chain-20261011 | 839f775fd4c32563d3ee9fc2ed8967b2d9dbf9cc | Open Draft, base PR 1 |
| PR 3, reports/public-lab-synthetic-http-20261012 | 5628ce63a1424f7fbb337675de78c18566b7b653 | Open Draft |

All four refs were fetched. No AGENTS.md, checkout.agents or SKILL.md exists in
the target checkout or PR 2 tree; workspace .agents and .codex are empty.
Other five preloaded repositories are outside scope and are not modified.

Read PR 2 powertrain.py, flight.py, simulator.py, web/index.html, fpv-flight.md,
fpv-powertrain.md, fpv-completion.md and the evidence inventory. The original
Python candidate is a localhost server with 2D projected Canvas, angle control,
algebraic motors, energy-accounted synthetic cells and sphere/box contact. Gaps:
standalone browser runtime, full 3D scene, physical collision impulses, Acro,
console layouts/calibration, touch, course, assembly, and static release checks.

## Acceptance cards, established before implementation

| Card | Acceptance | Status |
| --- | --- | --- |
| FPV-G01 | Standalone TS/Vite, a single Rapier dynamic state, SI force/moment model; A/B analytical, conservation and Python comparison tests | In progress |
| FPV-G02 | Standard Xbox/DualSense layouts, Mode 2 throttle choices, calibration/save, zero-throttle confirmed ARM and tested fail-safe | Planned |
| FPV-G03 | Procedural low-poly field, visible quad/rotors, FPV/chase, responsive HUD, graphics controls, real Chromium screenshots | Planned |
| FPV-G04 | Attitude target Angle and body rate Acro; controller/mixer sign and recovery tests | Planned |
| FPV-G05 | Assembly affects mass/power, five ordered gates, clock/best, crash/retry, saved-input replay | Planned |
| FPV-G06 | Full QA, pinned dependencies, independent CI/build, Pages workflow, exact version provenance, HTTPS test or precise blocker | Planned |

## Design / architecture

Full-bleed training field, warm sunlight, sage grass, orange gates and cream/dark
quad, charcoal translucent chrome, orange actions, monospace telemetry. Top brand
and Aircraft/Controls/Physics/Pause, left course status/welcome, bottom telemetry.
Settings use the same typography and compact drawer. Mobile has two touch sticks.
The image concept is internal design evidence, never game/browser evidence.
Procedure-built 3D geometry is an intentional choice authorized by the brief;
no third-party raster scene, external font or unlicensed model is needed.

Rapier owns position, velocity and quaternion as the sole dynamic body state.
The Python RK4 source is an independent comparison reference, not a second runtime.
Browser code retains z-up, x-forward/y-left coordinates; Three camera up is z-up.
Pure TS/DOM is used for the small HUD so physics/render work does not trigger
component re-renders. Fixed 1/240 s steps, with explicitly tested refinement and
bounded catch-up: excessive frame gaps disarm and pause rather than enlarging dt.

## Scientific boundary

1. Equations: Newton-Euler, quaternion, passive ESC/DC motor/static propeller.
2. Numerical properties: analytical checks, energy closure and step refinement.
3. Parameters: invented fixtures, including all component/control values.
4. Hardware calibration: **not performed**. Software/API passes do not imply it.

Original Chen 6/12, ORegan 30/36, Stanford high-rate and other recorded research
failures remain in their original branches. No research gate is redefined.

## Failures and restrictions retained

- 2026-10-24: repository-rules read via `gh api repos/lijiabao1998/Physical-Fpv-Simulator/rules/branches/main`
  returned `Get "https://api.github.com/repos/lijiabao1998/Physical-Fpv-Simulator/rules/branches/main": Forbidden`.
  The denied action is not retried via another route. Rules cannot yet be confirmed;
  merge/release eligibility remains blocked. Git fetch and connector metadata/PR
  reads succeeded. Continue independent engineering; do not bypass the denial.
- npm default cache `/home/agent/.npm` was unwritable; use `/tmp/fpv-npm-cache`.
- No physical Xbox/DualSense attached: hardware acceptance NOT RUN; API tests will
  be reported separately and support labelled Beta.
- Browser plugin is not available. Use actual Playwright Chromium as the requested
  real-browser acceptance path and save reproducible screenshots.

Progress, test failures/fixes and final evidence are appended as work is verified.

## 2026-10-24 12:06 UTC: resumed existing player implementation

Fresh fetch found PR 4 still at efe60981, main unchanged. Existing local commits
6816b68 and 39d5ca8 were preserved, not rebuilt. The implementation described in
CONSTRUCTION.md now includes G01–G05 code and G06 workflow/tests; those cards are
not release-complete because browser/CI/public acceptance remains outstanding.

Re-ran 44 unit/API/numerical tests: all pass. Regenerated five Python trajectories
with source hashes verified, TypeScript/build/static Pages-path checks pass.
Expanded browser suite to 12 cases including 360/412 responsive production images
and coarse-pointer input controls; cases are discovered, NOT yet executed.
Official Chrome installation did not resolve this workspace's socket restriction.
No screenshots, measured FPS, real controller acceptance or release is claimed.

A normal fast-forward git push failed before updating the ref because the local
HTTPS git transport had no username/credential. The connected GitHub application's
existing authorization is the normal submission path; no credential is replaced
and the original rules API 403 is preserved. Main/research refs are out of scope.

## First real Chromium acceptance (head c1512e3)

Run 40092906142 produced real product PNGs and traces: 4 passed / 8 failed.
Production Pages-base rendering including 1440/360/412 images, synthetic Standard
Gamepad handling and both mobile-pointer cases passed. Flight/Acro ARM, gates,
replay, frame sampling, calibration duration and assembly timing failed.
Artifact: https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/40092906142/artifacts/12559951016
The desktop trace shows frames over 250 ms, causing the correct fail-safe to pause
before ARM or scenario steps; calibration operations took ~0.5–2.5 s each. The
original auto quality waited five accumulated, clamped render seconds before
turning off expensive shadows, which amplified cold-start cost on software GPUs.
Repair starts Auto in existing low tier and only tries High after >55 measured
FPS and ten render seconds. Explicit High remains available. The 250 ms guard,
fixed steps, tests and all acceptance thresholds are unchanged. Browser recheck
is necessary; this diagnosis does not count as a pass or playable release.

## Follow-up Chromium run (head c04201c)

Run 40093666254 improved to 11/12 passing without retries. Flight, gates, replay,
Acro, calibration and timing now execute; the 250 ms fail-safe is unchanged.
The remaining assembly assertion sampled wall-clock simulation time after two
protocol round trips (0.7125 s). Capture the actual product reset at the native
click event's end instead, preserving <0.5 s and strengthening it to exactly 0.
This changes the observation time, not reset behavior or an acceptance threshold.
Visual inspection also found clipped 360 px navigation and HUD labels missed by
the original limited assertions. Reflow mobile navigation/HUD and assert full
Pause-button visibility plus the mode label's right edge. Original PNGs retained.
