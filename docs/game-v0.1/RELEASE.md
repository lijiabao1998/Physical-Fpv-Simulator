# Player release and acceptance

## Publication gate

This is an isolated browser player, not a merge of research PRs 1–3. Draft PR 4
remains the delivery route. Merge only after required repository rules are known,
all required checks and browser acceptance pass, and authorized review approves.
The preserved rules API denial means merge eligibility is currently **unknown**.
Do not use this workflow as a reason to bypass that denial or required acceptance.

Expected public address (not proof of deployment):
https://lijiabao1998.github.io/Physical-Fpv-Simulator/

`Player verification and Pages` installs locked dependencies, regenerates pinned
Python fixtures, runs unit/numerical tests, strict TypeScript/build/static-path
checks, then actual Chromium tests. Failure blocks upload/deployment. Branch and PR
runs never deploy. Only a verified `main` build can enter `github-pages`, where any
repository environment approvals continue to apply. Pages must use GitHub Actions
as its source. No Pages settings have been changed by this implementation.

## Reproduce

From `web/` with Node 24, Python 3.12 and NumPy 2.3.5:

```
npm ci
npm run reference
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

The e2e suite uses real Chromium, not mocked screenshots. It creates development
physics scenarios through development-only `?test=1` hooks, separately checks the
production bundle with no hooks, and writes screenshots to test-results. Synthetic
state placement is test setup, never evidence that a human flew that trajectory.
No actual Chromium run or screenshot is claimed until that command succeeds.

## Provenance and rollback

Every build emits `version.json` with version, full Git SHA, source-dirty flag,
UTC build timestamp and Pages base. A dirty local build is a preview artifact,
not an immutable release. CI rejects dirty source; check generated reference files
remain byte-identical. Production publication uploads the exact verified dist,
never rebuilds between verification and deploy, and probes HTTPS version metadata
for the same SHA. HTTP metadata alone does not prove visual or controller quality.
Record the successful workflow URL, screenshot artifacts, exact SHA, public HTTPS
response and tested hardware alongside each release before calling it accepted.

Rollback is a normal reviewed revert commit on main, followed by the same complete
verification and deployment gates. Do not force-push, rewrite history, merge the
research branches or bypass checks. If a prior artifact is selected using GitHub's
supported deployment controls, verify its SHA and HTTPS result independently and
record the rollback. Never describe an expected URL as live without probing it.

## Physical-controller manual acceptance (not yet run)

Run each matrix row independently: Xbox One/Series USB; Xbox Bluetooth; DualSense
USB; DualSense Bluetooth. Record OS, browser/version, device identifier, mapping,
connection method, date and observed failures. Browser/OS support varies; the
label is Beta until the device is actually tested.

1. Connect, press a button to expose Gamepad API, check device/mapping and live axes.
2. Check Console defaults: RT/R2 throttle, left X yaw, right X roll, right Y pitch.
3. Hold A/Cross at nonzero throttle: must not ARM. Release throttle and hold for
   at least 600 ms: ARM. B/Circle disarms; Y/Triangle camera; Menu/Options pause.
4. Calibrate center/endpoints, invert axes, adjust deadzone/expo/rate, reload and
   confirm persistence. Test Mode 2 integrated versus absolute throttle, including
   the explicit self-centering warning and zero capture before ARM.
5. Take off, steer in Angle and Acro, cross gates, collide, retry and import/export
   replay. Check paused rotor animation, correct RPM response and optional sound.
6. Unplug and turn off Bluetooth while armed; blur/hide the tab; simulate long
   frames. Each must stop stale commands and disarm/pause rather than fly on.
7. Test keyboard and touch alone, multi-touch release/cancel, and switching devices.
8. Measure desktop and representative physical-phone frame timing over 60 seconds;
   report hardware, browser, resolution, quality, average/1% low FPS, draw calls,
   triangle count and dropped simulation time. Desktop 60/mobile 30 are targets,
   not achieved results inferred from automated headless software rendering.

## Known scientific limits

Physics-based flight simulation · Synthetic parameters · Not hardware validated.
基於物理方程的飛行模擬｜採用合成參數｜尚未通過真實飛行器驗證

The circuit, motor, propeller, drag, inertia and controller values are synthetic.
Static propeller and simplified rigid contacts are not CFD, elastic fracture,
real sensor/ESC timing or calibrated hardware. A game crash threshold is not a
material-damage model. Numerical, API and browser tests do not validate real
flight performance. Original research failures remain unchanged in their branches.
