# Physical-Fpv-Simulator
Physics-first FPV simulator built from real physical properties.

## Physical FPV v0.1 browser player (construction branch)

The isolated `web/` player uses physical equations with **synthetic parameters**.
It is **not hardware validated**. Passing numerical/software tests must not be
represented as real-aircraft or physical-controller certification.

```sh
cd web
npm ci
npm run reference
npm test
npm run build
npm run dev
```

Open the local URL printed by Vite, including `/Physical-Fpv-Simulator/`.
Requires WebGL2 and WebAssembly. A standard-mapped Xbox or DualSense controller
is Beta supported through the Gamepad API; keyboard and touch are alternatives.

- Keyboard: arrows change throttle; W/S pitch; A/D roll; Q/E yaw.
- Hold Space or the ARM button 0.6 seconds at zero throttle to arm.
- X disarms; C changes camera; P pauses/resumes; R retries; M changes mode.
- Controls drawer includes raw values, calibration, direction, curves and rates.
- Aircraft changes synthetic mass/propulsion; Physics explains limitations and
  provides local replay import/export. No account, telemetry backend or payment.

Real Chromium acceptance is `npm run test:e2e` after a production build and
`npx playwright install chromium`. The test suite contains both synthetic-input
fixtures and production rendering checks; neither replaces physical hardware QA.

[Construction status](docs/game-v0.1/CONSTRUCTION.md) ·
[Release gates and rollback](docs/game-v0.1/RELEASE.md) ·
[Numerical evidence](docs/game-v0.1/evidence/numerical-report.json)

The expected Pages URL is not proof of deployment. Do not treat this branch as
released until the documented browser, repository and publication gates pass.
Original research PRs remain separate and their failed scientific gates remain
unchanged. Python comparison provenance is pinned to the source commit recorded
under `reference/` and `docs/game-v0.1/PROGRESS.md`.
