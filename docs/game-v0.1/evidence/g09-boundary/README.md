# G09 boundary failure PB invalidation — bounded correction

Owner G09 acceptance requires collision/failure not produce a valid PB. The frozen G09 card preserves pause/resume, thresholds and original physics. This correction changes only the independently reproduced boundary-failure path, not general safety pause semantics or release authorization.

Original clean candidate `fa51264e2afd2b897b3ff3bfae7869c36afc1aad`:
- Native module/Rapier probe: Gate 1 → synthetic x=221 position → actual native boundary step → `paused`, reason `Training boundary reached — paused. Retry.`, but course valid → native Resume → remaining four gates → `finished`, valid record written.
- `boundary-probe-original-raw.log` is redirected original probe stdout; source identity in `boundary-probe-source.txt`. Synthetic pose setup is explicitly not a human flight or performance measurement. Reusable probe uses existing Vite SSR, not Chromium.
- Before correction, six new G07/G08 controls produced 2 boundary failures / 13 passes in the race file. Original assertions retained; no thresholds relaxed.

Minimal change: call `course.invalidate()` inside the unchanged boundary predicate before the existing `fail()` pause/disarm. Resume stays safe/disarmed but cannot finish or save the failed attempt. Retry restores eligibility. Manual Pause and the existing 250ms safeStop native call remain resumable and can finish a valid record, tested for both physical models. Tests invoke the exact native safeStop operation; they do not newly claim browser wall-clock qualification.

Validation:
- First full local default suite: 8 files / 85 tests passed; numerical-report worker SIGKILL, incomplete overall. Original error retained, no assertion failure reported.
- Focused single-worker diagnostic: all 15 race tests + numerical-report test passed (16/16). This is a process-resource diagnostic, not a workflow/config/threshold change or replacement for normal official CI.
- TypeScript `--noEmit` passed. Browser/official exact-head CI not run for this local correction; previous green head does not certify this changed source.
- Physics-guard/depletion paths were not independently reproduced and were NOT changed. No blanket `fail()` invalidation, control/ARM/240Hz/model changes, remote write, merge or deploy.

Reproduce the original probe only against the original source: from that checkout's `web/`, run `node /absolute/path/to/boundary-probe.mjs`. The script dynamically imports that working directory's existing Vite installation and loads its source. Do not mislabel fixed-source output as original-head evidence.
