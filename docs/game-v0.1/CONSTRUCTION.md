# FPV-G02–G06 integration in the assistant cloud workspace

## Acceptance scope established before integration

Wire the existing single-state physical simulator into a browser game without
changing the original research branches. Preserve fail-closed input handling,
zero-throttle 600 ms ARM confirmation, synthetic-parameter disclosure, and
strictly separate software tests from hardware or visual acceptance.

## Implemented

- Full-viewport procedural outdoor field, hangar, trees, five ordered gates,
  quadrotor, chase/FPV camera, responsive instruments, quality/FOV controls.
- Rotor phase advances with each fixed physical step, using calculated angular
  velocity; pausing freezes it. Propeller visual diameter follows assembly.
  Static scenery is merged by material/shadow flags to reduce draw calls.
- Keyboard and captured-pointer touch input, Standard Gamepad layouts,
  calibration/axis direction/expo/rates, optional RPM audio, local settings.
- Assembly selection modifies mass and power; course/free-flight modes,
  local best, retry, replay export/import and same-build check.
- Focus/visibility/controller interruption safely pauses and disarms. Fixed
  240 Hz stepping does not scale force with frame rate; excessive gaps pause.
- Production assets use the repository Pages base. Version manifest marks dirty
  preview builds. Production bundle does not expose development test hooks.
- Isolated player workflow includes pinned Python comparison, tests, strict TS,
  production build, real Chromium tests, artifact upload and main-only Pages
  deployment after verification. Deploy job checks public HTTPS SHA manifest.

## Verified here

Dependency install from lockfile completed in the selected assistant workspace.
Python reference source hashes and five regenerated trajectories pass.
Unit/API/numerical tests and TypeScript/production-build/static-asset checks pass;
see evidence reports and final execution log for exact counts/commit.
The original freefall-tolerance failure and correction remain recorded.

The browser tests are implemented and discoverable, **not executed here**.
The latest integrated local run passed **44/44 tests** and strict TypeScript.
The environment's Chromium socket launch restriction and escalation-wrapper
failure were already established during migration. They were not bypassed.
Normal Vite dev/preview processes subsequently reported ready on loopback ports
4173/4174, but separate tool calls and the supported existing cloud browser could
not connect (connection refused). Thus server startup is not browser acceptance;
no network-isolation or security setting was changed to work around this.
No real gameplay screenshots or measured FPS are available. The generated UI
and scene have not been visually accepted. No Xbox/DualSense hardware test ran.

## Remaining release gates

1. Actual Chromium run, inspect screenshots and fix any rendered/interaction
   defects; collect actual desktop/mobile frame-time measurements.
2. Review the final PR and required checks for its exact SHA; branch-rule read
   was denied earlier and must not be assumed satisfied or bypassed.
3. Only after applicable acceptance and repository rules are satisfied, merge
   and deploy; verify the public site's exact artifact, assets, HTTPS and views.
4. Physical Xbox/DualSense testing remains clearly separate and Beta until run.

No research PR was merged, no history was rewritten, and no public release is
claimed by this construction record. The 4.9 MB uncompressed / 1.82 MB gzip
single JS bundle (including Rapier compatibility WASM) is a known startup-size
limitation; CPU/GPU performance is unmeasured, not inferred from build success.
