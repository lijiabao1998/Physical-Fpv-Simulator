# G15 Personal Best Ghost release fixes — pre-code card

Opened 2026-10-28 by Claude and revised 2026-10-29 after an adversarial review, before any G15 code. G15 finishes G11 (Personal Best Ghost: PR #10, head e0c6d87, written by GPT) on the released base and fixes what the G11 evaluation found. This card freezes acceptance before code.

## Owner decisions

- 2026-10-28, 「Fpv baa g11」. My message had numbered three G11 questions: 1 release path, 2 the Ghost in flight school, 3 storage. The answer reads, in order:
  - **1 (B)** 「整合到 main，先修完必修清單，再做一輪 A/A 對照，確認超標是測試順序造成的才上」;
  - **2 (a)** 「教學時不顯示」;
  - **3 (a)** 「約 2 MiB，滿了換掉最舊的其他設定鬼影」.
- The same message said that, without other instructions, I would apply my recommendations to the rest. These are: a lap finished in flight school still counts as the class PB and now also saves a Ghost; the landscape Ghost HUD ships as a known issue with its own layout card; the zh-TW name stays 「個人最佳 Ghost」.
- 2026-10-29, the release bar: 「美術過得去，人可玩流暢玩狀態就行」.
  - I read this as replacing the A/A round of answer 1. The CPU reservation is a 1440 desktop render-CPU excess of about 0.1 ms per frame, with rAF frame p95 unchanged. It does not affect how smoothly the game plays.
  - So G15 releases when the must-fix list is done and CI is green. The reservation stays recorded as a known issue, as option C described it.
  - I told the owner this reading the same day. If the owner still wants the A/A round, it runs before the merge.

## Base

The port follows the G11 evaluation's port plan. It is not yet pushed.
- `e780384`: a real merge, never a rebase, cherry-pick or squash. Its first parent is the G11 head e0c6d87. Its second parent is main at 125f9fa, after PR #13 (G13) merged; G10 and G12 were already released there.
  - The G11 card (lines 55–57) planned a Draft against G10 with no G12, no merge and no Pages. The base has moved on purpose.
  - Conflicts in main.ts (3 hunks) and i18n.ts (2 hunks) are resolved as statement-level unions by `apply-g11.mjs`. Neither side is taken whole and nothing is merged token by token. G12's DEV `schoolTick` hook also calls `ghostRecorder.observe(game)`.
  - Gates: strip-check true; 0 conflict markers; `tsc` exit 0; 247 unique i18n entries; the diff against main lists exactly G11's 27 files; `npm test` 154 of 154 (main's 135 plus G11's 19).
- `f793cd0` (test only) serves `web/e2e/g11.spec.ts` from /fpv/ (lines 3 and 58). The e0c6d87 spec with `/Physical-Fpv-Simulator/` replaced by `/fpv/` is byte-identical, and `git grep Physical-Fpv-Simulator -- web` prints nothing.
- A docs commit appends the port receipt and the restated inherited-file invariant to the G11 card, after its frozen line 60 (lines 1–60 keep sha256 2b3dbbb2…dc26). It stores `apply-g11.mjs`, `strip-check.cjs` and a full SHA256 table of the 39 inherited files under `docs/game-v0.1/evidence/g11/port/`.

## What G15 changes

1. **No Ghost in flight school (answer 2).**
   - While the school is open, `visibleGhost()` returns no pose, and the status says the Ghost is hidden during flight school (item 4).
   - Recording continues, so a lap finished in the school saves the PB and its Ghost.
   - The split table stays. Where the course card is not G13's strip (wider than 600 px), it still compares gates with the hidden Ghost.
2. **Store only the lap.**
   - The recorder samples from reset, but playback never reads a pose before the last 4-tick sample at or before the Gate 1 crossing (`startedAt`).
   - At completion, the returned record's poses start at tick `4*Math.floor(startedAt/FIXED_DT/4)`. That exact expression lives in one helper that the recorder and the validator share.
   - `completed()` trims only the record it returns. The recorder's own samples are untouched, and repeated calls return equal records.
   - The validator requires exactly that first tick instead of tick 0. G11 never shipped, so no stored Ghost needs migrating.
   - Why: the four G11 fixtures store 12.7–20.2 % of poses that are never played. Untrimmed, a Ghost reaches the 4 MiB cap about three minutes after reset. Probe P1 (175 s idle, then a 20.99 s lap) gave 4,668,148 bytes. saveGhost then returned false, and the status said only 'No matching Ghost for this configuration'. Flight school puts lessons before the lap, so this is likely in real play.
3. **A total budget (answer 3).**
   - Ghost entries are the keys starting `physical-fpv-pb-ghost-v1:`. They are counted at 2 bytes per UTF-16 code unit of key plus value, and total at most 2 MiB (2,097,152 bytes) when saveGhost returns.
   - The stored value is the record's JSON with `order` as its first member: `{"order":N,…}`.
     - N is valid only if `Number.isSafeInteger(N) && N >= 1`.
     - A new entry gets 1 plus the largest valid N stored, or 1 if there is none.
     - Totals and N are read from lengths and the `{"order":N,` prefix, without JSON.parse. Other entries are parsed only while the total exceeds 2 MiB.
   - `loadGhost` requires a valid N and returns the record without `order`. Its storage parameter stays getItem-only.
   - saveGhost keeps G11's checks: a valid record that matches the current PB, and an equal or faster stored Ghost is kept. It never mutates its argument. Then:
     1. An entry that alone exceeds 2 MiB is refused: no write, no removal.
     2. It writes the entry. If the write throws, it returns false and has removed nothing (G11 card lines 25–26: save failure retains old bytes).
     3. After a successful write, while the total exceeds 2 MiB, it removes other Ghost entries one at a time:
        - first, in ascending key order, entries that are unreadable, misfiled under another class's key, or stale (not the Ghost of their class's current PB);
        - then by ascending N, ties in ascending key order. An entry whose class this build cannot resolve ranks by N.
     4. If removeItem throws, it keeps the new entry, stops removing and returns true.
   - It never removes the entry just written, a PB record, or any key outside `physical-fpv-pb-ghost-v1:`.
   - The per-Ghost limits in ghost.ts line 9 (144,000 ticks, 36,002 samples, 4 MiB) stay unchanged.
   - With the trim a Ghost takes about 22 kB per second of lap, so a lap longer than about 95 s gets no Ghost. The status says so (item 4).
4. **Status line and displayed Ghost.**
   - Checked in this order; the first match wins:
     1. replay (not recordable): unchanged, 'Replay preview · PB protected';
     2. flight school open, Ghost loaded: `PB x s · hidden during flight school`, zh-TW 「個人最佳 x s · 飛行學校中不顯示」;
     3. free flight, Ghost loaded: `PB x s · not shown in free flight`, 「個人最佳 x s · 自由飛行時不顯示」;
     4. a class PB with no Ghost loaded: `PB x s · no Ghost stored for this PB`, 「個人最佳 x s · 未儲存 Ghost」. This covers a PB from before G11, a failed save, an evicted Ghost, a lap too long for the budget, and a PB set in another tab;
     5. no class PB: unchanged, 'No matching Ghost for this configuration';
     6. otherwise unchanged: `PB x s · waiting at Gate 1`, `chase your best` or `hidden`.
   - x is the class PB's total.
   - There are two records:
     - The displayed Ghost gives the pose and the status. It is tied to the PB it was loaded against (G11 card line 26: never display a Ghost that mismatches the current PB). When a lap sets a new PB, the same HUD update replaces it with the saved Ghost, or with none if saveGhost returned false. When the PB that the HUD reads changes for any other reason, such as another tab, it is reloaded.
     - The chased Ghost gives the split table. It changes only with the attempt, as at e0c6d87. So until Retry the table compares this lap with the Ghost it chased.
5. **Production loop test.** Every e2e that saves a Ghost goes through the `localInputFlight`, `tick` or `schoolTick` hooks, which call the recorder themselves. If the loop's own calls (main.ts lines 141–142) were lost, every real flight would be ineligible and the suite would stay green. E7 lets the real loop run instead. Mutation-red logs show it fails without either call.
6. **G11's ≤480 px CSS stays off the school strips.**
   - G11's rule (style.css line 20: `.course` 250 px wide, 22 px gate dots, 5 px gaps) also reaches G13's one-row strip while the school is open.
   - Each selector of that block gets the prefix `:where(#app:has(>#school-panel[hidden]))`. The block keeps its place, and its specificity does not rise. A bare `:has()` prefix would weigh (2,2,0) and override G13's short-landscape rules at 480x400.
7. **Course card on short portrait phones, school closed.**
   - Main already overlaps both sticks here, before any lap and without G11. This is from G13's round-3 measurements, where main and G13 were identical: 320x568, 360x640 and 375x667 coarse; at 360x640 and 375x667 zh-TW, Flight school's centre hits the left stick. G11's rows (about 100–150 px) make it larger.
   - The sticks are live flight controls, so this is fixed, not accepted, wherever the band above the sticks can hold the card's first rows:
     - CSS only, up to 480 px wide, coarse pointer, portrait, school closed, from 568 px of height;
     - the card is capped at the band between its top and the sticks' top minus 8 px, and scrolls inside, as G12's open panel does;
     - it may put course select and Flight school in row 1 and the clock and gates in row 2, as G13's short-landscape card does.
   - Below 568 px of height (320x480, 360x540, 360x560, 414x550) the band is 39–119 px. Nothing changes there; it ships as on main and goes to G14.
   - Before and after images go into the PR.
8. **Evidence.** The G11 docs and PR #10 stop at 672bb2f and 579909b. Dated receipts are appended, without deleting GPT's text: the green e0c6d87 runs (push 40445940089, PR 40445946110: 142 unit and 61 Chromium; 1440 first pair +28.16 % and +31.57 %), the red 709917a runs 40439970023 and 40439975943, the port, and the restated inherited-file invariant. The '39 files identical to G10' sentence no longer holds as written.

**Files G15 may change.**
- `web/src/game/ghost.ts`, `web/src/main.ts`, `web/src/ui/i18n.ts` and `web/src/style.css`.
- `web/tests/g11-ghost.test.ts`: the two wiring edits below only.
- New `web/tests/g15-ghost.test.ts`, `web/tests/g15-i18n.test.ts` and `web/e2e/g15.spec.ts`.
- This card, appended sections of the G11 card and its evidence README, and new files under `docs/game-v0.1/evidence/g11/port/` and `docs/game-v0.1/evidence/g15/`.

## Frozen acceptance

**Tests first.** One test-only commit adds the tests below before any fix. Its first-red run is local: unit and Chromium, each run on its own, because CI skips Chromium when unit tests fail. The logs are kept. Unit tests hard-code the frozen numbers (2,097,152 bytes; first tick `4*Math.floor(startedAt/FIXED_DT/4)`) and import nothing new. Each test below says whether it must be red at the port head; a test that does not match that is fixed first.

**Unit (vitest)**
- U1 trim (red), for the three course fixture laps:
  - the first pose tick follows the rule;
  - every stored pose equals the simulation pose at its tick, and nothing before the first is stored;
  - `ghostPoseAt` at lap time 0 and at the total equals the untrimmed timeline's;
  - `sampleCount` is unchanged by `completed()`, and a second call returns an equal record.
- U2 validator. Each negative changes one property of a record that a twin case accepts:
  - first tick 0 where the rule gives more (red);
  - the rule's tick plus 4;
  - a first tick that is not a multiple of 4;
  - `startedAt` and `finishedAt` both moved by +0.1/240 s with the poses unchanged (the rule tick moves by 4).
- U3 long idle (red): a training-straight lap after 175 s of disarmed idle from reset stores a Ghost, and it loads.
- U4 budget (red). The storage fake has a 5,242,880-code-unit quota and throws past it. It also holds foreign keys: GlimmerTown-lab-style saves with `_bak` copies, a DefendTaipei-style key, FPV settings and language, and PB records.
  - Saving other classes' Ghosts past 2 MiB removes the lowest N first.
  - A class saved again with a faster lap gets the highest N, so the next removal skips it.
  - Unreadable (bad JSON, another schema, no N, N = 1e300), misfiled and stale entries go before any live entry, in key order. Removal stops once the total fits.
  - A throwing removeItem keeps the new entry and returns true.
  - Every non-Ghost key and PB record stays byte-identical. The entry just written loads.
- U5 failed write (guard): a throwing setItem, and the quota fake when the new entry does not fit, both return false and leave every key byte-identical, including the class's old Ghost.
- U6 oversize (red): a valid record whose entry is between 2 and 4 MiB, built from the British Slalom lap scaled in time, is refused with no write or removal. Its twin under 2 MiB is written.
- U7 order (red): the raw value starts `{"order":N,`, with N = 1 first and max + 1 after, including a same-key replacement; loadGhost's result has no `order` and equals the saved record.
- U8 copy (red): `translate()` gives exactly the three zh-TW lines of item 4, and G11's lines keep theirs.

**Browser (Chromium; `web/e2e/g15.spec.ts`)**
- E1 school hiding (red): with a stored PB Ghost drawn at Gate 1, opening flight school gives `pose === null` and `loaded === true`. After a rendered frame, `render.visible === false`. Status rule 2, in zh-TW and en.
- E2 school lap (red). G12's full school path (g12.spec.ts lines 6–16), with `__FPV_TEST__.tick(0)` right after the `#school-retry` click: the 0-tick observe that `animate` makes before its first step.
  - It ends with the lesson complete, one PB record and one Ghost entry for the class, whose first pose tick follows the rule.
  - While the school is open there is no pose and rule 2 shows.
  - 'Return to free flight' gives rule 3 and no pose.
  - Aircraft → Five-gate course gives 'waiting at Gate 1' and a pose.
- E3 free flight (red): with a stored PB Ghost, Aircraft → Free flight gives rule 3 and no pose. With the school open, rule 2 shows instead.
- E4 new PB (red). Slow lap, Retry, then the fast lap, without Retry:
  - the status shows the fast lap's time;
  - the pose tick equals `(fast startedAt + fast total)*240` within 1e-6;
  - every row of `#ghost-splits` shows the fast split, the slow Ghost's split and their difference. A self-comparison would show 0.00.
- E4b failed Ghost save (red): as E4, with setItem throwing for Ghost keys during the fast lap. No pose, rule 4, and the slow Ghost's bytes are unchanged.
- E5 PB without a Ghost (red): with the class PB present and its Ghost entry removed, Retry gives rule 4 in zh-TW and en, and no pose.
- E6 replay lock (guard): after E2's school lap, 'Watch this flight' keeps rule 1 while replaying, paused and resumed, with no pose and the school blocked. A replay that finishes the course writes no PB or Ghost key.
- E7 real loop (guard; red by mutation). After a native Retry, disarmed on the pad:
  - the first read waits two animation frames;
  - reads repeat until at least 240 steps;
  - every read satisfies `samples === Math.floor(events/4) + 1`, with events = `Math.round(time*240)` from the same snapshot;
  - a stop by the 250 ms guard is resumed with the native Pause button, at most three times.
- E8 course card, school closed, coarse (red where main overlaps), in zh-TW and en, before any lap and after a completed 7-gate British Slalom lap:
  - Viewports: 320x568, 360x640, 360x800, 375x667, 390x844 and 412x915.
  - `.course` intersects none of `#left-stick`, `#right-stick`, `#arm`, `#disarm`, `.actions`, `.notice` and `.hud`.
  - At scrollTop 0, `#course-select`, `#course-clock`, `.course .gates` and `#school-open` are hit at their centres.
  - `#ghost-toggle` is hit at its centre at scrollTop 0, or once the card is scrolled to it.
  - The page itself never scrolls.
  - Fine 650x900 and 704x900, school closed after the lap and school open: `.course` intersects none of `#arm`, `#disarm`, `.actions`, `.notice`, `.hud` and the open panel.

**Scripted check (local Chromium)**
- V1 school strips (item 6), with the school open at every viewport up to 600 px wide in g13.spec.ts, in both languages. The rects of the header, `.course`, `#course-clock`, `.course .gates`, the panel and its controls, both sticks, `#arm`, `#disarm` and `.actions` equal main's within 0.5 px. It is red at the port head, then green. The school-closed card at 480x400 is unchanged against the port head.

**Unchanged, and green at the final head**
- `web/e2e/g11.spec.ts` is unchanged except the URL swap. `g12.spec.ts`, `g13.spec.ts`, every G07–G10 spec and the I18N spec are unchanged.
- In `g11-ghost.test.ts` there are only two test-wiring edits, each explained in its commit message:
  - the `storage()` helper gains `removeItem`, `key` and `length`;
  - the 60/20/5 Hz test (line 54) looks poses up by tick instead of by index `ceil((tick+1)/4)`. A compared tick before the first stored pose is compared with the fixture's own trace instead. The test compares as many ticks as before.
- No change to physics, control law, input mapping, the 240 Hz step, the 600 ms ARM hold, the 250 ms frame guard, lesson thresholds, scoring, PB records, settings, workflows, or the G11 card's first 60 lines.
- The render path is unchanged apart from item 1's school check: `scene.ts`, `ghost-outline.ts` and `diagnostics.ts` are byte-identical to e0c6d87, and so are `ghostPoseAt` and `GhostPlayback`.

**CPU (G11 card line 50)**
- The frozen method (G11 evidence README lines 142–146) is applied, unchanged, to the final head's runs. Per width: OFF1/ON2/ON3/OFF4, first and reverse pairs, rAF p95 and median, draws, triangles and memory. Every run is reported.
- The 1440 first-pair reservation ships as a known issue (owner bar of 2026-10-29). Any other pair, any width or frame p95 above +20 % in two runs of the final head stops the release and goes to the owner, because frame time is what players feel.

## Publication and release

- The port, the card, the tests and the fixes go to the session branch and one PR against main. PR #10 gets a dated note that points to it; GPT's text and branch stay as they are.
- A head's runs are its pull_request run and a workflow_dispatch run of the same SHA. player.yml has no push run for this branch.
- Before merge:
  - CI is green: unit, reference fixtures, strict build and every Chromium spec;
  - V1 passes;
  - I review the raw images by eye: G11's FPV/Chase, bilingual and other-course images; G12's completed-school images; G15's E1–E5 and E8 images.
- Merge with a merge commit pinned to the verified head. Then https://game.lijiabao.uk/fpv/version.json must report the merge commit, and the result is recorded on the PR.
- Rollback is a reviewed revert on main under the same gates.

## Known issues that ship

- The 1440 desktop render-CPU reservation (about 0.1 ms per frame; frame p95 unchanged).
- The landscape Ghost HUD (its own layout card), and any Ghost row that item 7 leaves in the card's scrolled part.
- Portrait phones under 568 px tall: the school-closed course card still overlaps the sticks, as on main (G14).
- One origin, one browser quota: other games on game.lijiabao.uk share it, so the 2 MiB budget lowers the risk but cannot remove it. Write-then-evict needs room for the new entry first; when the quota cannot hold it, the save fails, nothing is removed, and rule 4 shows.
- Two tabs saving at once can tie on N or remove each other's new Ghost.
- Ghost JSON work is synchronous at lap end and on course loads. Not measured on phones.
- In flight school the split table still compares with the hidden Ghost where the card is not G13's strip; after the school, its Ghost plays on the Five-gate course only.
- G14 will move the school and course layout again; the Ghost rows need another look then.
- Physical Xbox and DualSense over USB or Bluetooth, physical phones, aircraft and battery stay unverified.

## Status

Opened, not started. No code, test or workflow has changed for this card.

## Round 2: the split summary shows whole lines (2026-10-29, Claude)

Added before code, after the by-eye review of `85fe02f`'s CI images. Nothing above changes.

**Finding.** G11 (`b1c8283`) styles the sector summary `#race-splits` with `font-size:9px;max-height:28px;overflow:auto`. With main's line-height of 1.35, a line is 12.15 px, so the box shows 2.3 lines and cuts the third line through its glyphs. This happens in every zh-TW course card after a lap, and in en wherever the summary needs three lines. Main has no cap. The cut is new to players with G11 and is not on the known-issue list. An independent check of the images confirmed it as minor and cosmetic.

**Change.** The box becomes exactly two lines tall (`max-height:2.7em`, that is 2 × 1.35 at the box's own font size). G11's intent stays: the summary remains a scroll box, so it does not duplicate the Ghost table, which repeats the cumulative gate times. Nothing else changes.

**Acceptance.**
- E9 in `web/e2e/g15.spec.ts`, test first. After a 7-gate lap at 1440x900 (fine pointer) and at 412x915 (touch), in zh-TW and en:
  - the box height is a whole number of its own lines, within 0.05 line;
  - the zh-TW summary overflows the box, so the test cannot pass without checking anything.
- E9 is red at `85fe02f`: at both 1440 and 412, zh-TW gives 28 px against 12.15 px lines (2.30 lines). The log is `evidence/g15/e9-red.log`.
- Everything under "Frozen acceptance" stays green at the round-2 head, and the CPU rule applies to that head's two runs.
