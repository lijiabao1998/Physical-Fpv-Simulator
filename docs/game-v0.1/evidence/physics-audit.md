# Own-workspace physics audit, 2026-10-24

Run in the restored player checkout, not copied acceptance from the source environment:

- `npm run reference`: PASS. Five trajectories regenerated from hash-verified, pinned Python source commit `839f775fd4c32563d3ee9fc2ed8967b2d9dbf9cc`.
- `npm test`: 44/44 PASS, four test files.
- `npx tsc --noEmit`: PASS including integrated main runtime, after preserving the readonly production Gamepad API and giving only the synthetic test fixture mutable arrays.
- Browser rendering, public deployment and physical-controller tests: not performed by this audit.

`numerical-report.json` is regenerated on every test run by `web/tests/numerical-report.test.ts`. It contains all sampled errors, maxima and RMS values at 120/240/480 Hz for the five pinned Python trajectories. It also records analytical no-drag freefall, ten seconds of varying electrical load, and passive ground/wall contact energy. Acceptance thresholds are in the report and test source.

At 240 Hz, maximum errors across the trajectories were approximately 0.00413 m position, 0.00471 m/s velocity, 0.000483 rad attitude and 3.56e-15 V supply voltage. Non-hover position error and differential-thrust attitude error shrink below 0.7 of their previous values when dt halves. This is numerical refinement toward the fixed Python reference, not hardware validation or a proof of exact trajectories. Pure freefall position error at 120/240/480 Hz was 0.005117/0.002484/0.001301 m. Float32 velocity roundoff can increase at smaller dt even while position/energy error decreases; the full numbers are retained.

Electrical state-energy closure error was about -5.41e-11 J over 2946.9 J of chemical energy consumed. Ground and wall contact tests disabled gravity and external thrust, with peak kinetic energy equal to (not exceeding) initial energy; final energy decreased. These bounded cases do not prove every contact arrangement is passive.

Independent added checks verify torque-free anisotropic rotation follows Euler gyroscopic coupling and invalid rotor loads cannot mutate the body. The 1e-4-second gyroscopic check uses initial body rates (1,2,3) rad/s and inertias (0.005,0.005,0.009) kg m²; finite-difference rates match expected (-4.8,2.4,0) rad/s² within 0.03 rad/s². No duplicate gyroscopic force should be added on top of Rapier's integration.

Model boundaries: algebraic/quasi-steady motor speed, static propeller coefficients, synthetic homogeneous pack and component parameters, lumped thermal model, simplified rigid-body colliders, and gameplay crash threshold. No measured aircraft accuracy, blade aerodynamics, motor spool transient, structural fracture, physical Xbox/DualSense acceptance, screenshot or performance claim follows from these tests. Original research evidence and failed empirical gates are unchanged.

Input audit also fixed same-index/different-ID controller replacement detection and added fail-closed axis shaping for invalid direct UI calibration. Hostile persisted calibration bounds remain clamped and finite. Two new regression cases pass. Identical-ID devices reusing the same index require browser disconnect events; polling alone cannot distinguish them.

## Runtime integration audit

The integrated runtime passes strict TypeScript and 44 unit/API/numerical tests. Pure scheduling tests verify 30, 60 and 120 rendering frames schedule exactly 240 fixed physics steps per second, with substep carry, pause clearing and long-frame/catch-up guards. Rotor phases freeze on pause, reset, and reproduce exactly in same-runtime input replay.

Code-review fixes include touch-to-keyboard takeover, unexpected touch-capture loss fail-safe, clearing pending ARM holds on device failure, calibration-center revalidation, configured rate restoration after replay/retry, cancellation of stale asynchronous replay imports, and limiting local-best writes to once per completed course. These DOM paths are code-reviewed and compile-checked; they still require the separate actual-browser acceptance suite.
