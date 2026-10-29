# G13 mobile school layout and landscape Safe stop — follow-up card

Opened 2026-10-28 by Claude. Source: the owner's G12 release decision, recorded in the G12 card under "Owner release decision 2".
- Option chosen: 「已知問題隨版上，文案一併改」.
- Option text: "(1)(3) 寫進卡面當已知問題，和橫向安全停止一起另開卡；文案改成「教學課程 · 暫定難度」（英文 Lessons · provisional difficulty），推上去跑 CI，綠了就合並發布".

This card records the issues that ship with G12 and freezes acceptance before any code. It authorizes no implementation, merge or publication; priority and go-ahead are the owner's. Item 2 is safety-relevant and is proposed first.

Base: G12 as released from PR #12 (head 1c65683 plus this card). Once merged, the base is main.

## Issues

Measured on the 1c65683 build in Chromium with touch emulation. None of this is physical-phone evidence.

1. **Short coarse screens, school open.** The clock and gates scroll inside the course panel.
   - At 320x568 the school panel still overlaps `.course` by 7696 px² in zh-TW and en. Before G12's fix it was 34040 px².
   - In zh-TW the panel also overlaps the header by 296 px².
2. **Landscape safety (pre-existing), 800x360 coarse.**
   - zh-TW: `#school-stop` {x 550, y 249, w 60, h 31} overlaps `#arm` {x 478.7, y 265, w 124.7, h 33} by 801.6 px².
     - A centre tap on Safe stop or Retry hits `#arm` (Hold ARM).
     - A centre tap on Close hits `#disarm`.
   - en: Safe stop sits directly on top of `#arm`, with 0 px² overlap and a 0 px gap.
     - Its centre tap hits `#school-stop`.
     - Close hits `#right-stick`.
3. **Widths 601–704 px, desktop rule.** The school panel overlaps the course panel.
   - At 650x900 in lesson 1: 649 px² in zh-TW, 598 px² in en.
   - 704x900 measured 0 in lesson 1, but the upper bound depends on panel state.
4. **Welcome Start button, 320x568 coarse, zh-TW.** The Start button (y 378–425) lies under the fixed `.actions` bar (y 369–436), so a centre tap hits `.actions`.
   - The same happens on main f30b3e1.
   - en is unaffected.
5. **Released copy line hidden at scrollTop 0.** On 360x800 and 320x568, the sticky button row of the school panel covers 「教學課程 · 暫定難度」 / "Lessons · provisional difficulty".
   - zh-TW is fully covered; en shows about 3 px.
   - Scrolling the panel 27 px (zh-TW) or 17 px (en) reveals it.
   - The previous copy sat in the same place.
6. **Stale test metadata.** `web/e2e/g12.spec.ts:35` still labels its attachment `difficulty:'provisional owner review required'`, which predates the owner accepting provisional difficulty.

## Frozen acceptance (before code)

**Scope**
- Layout only: CSS and markup placement of the school panel, course panel, header, welcome actions and school controls.
- No change to physics, control law, input mapping, the 600 ms ARM hold, the 250 ms frame guard, lesson thresholds, scoring, storage or workflows.

**Viewports.** Chromium geometry assertions in zh-TW and en at:
- 320x568, 360x800, 390x844 and 412x915 portrait, coarse.
- 650x900 and 704x900 fine, in every lesson state.
- 800x360 and 844x390 landscape, coarse.

**Geometry**
- 0 px² intersection between the school panel and each of:
  - the clock and gate rows of `.course`;
  - the header;
  - the `.actions` buttons.

  This holds in every lesson state. The panel may scroll only inside its own box.
- Safe stop, Retry, Close and the welcome Start button:
  - `elementFromPoint` at the centre returns the control itself;
  - each target is at least 44 px;
  - each sits at least 8 px from `#arm`, `#disarm` and both sticks.
- The provisional-difficulty line is visible at panel scrollTop 0.

**Native touch e2e.** In landscape, tapping Safe stop ends the school attempt and never arms.

**Regression and evidence**
- The existing G10, G12 and i18n e2e, unit, reference and build checks pass unchanged.
- The PR carries screenshots of every listed viewport in both languages.

**Test metadata.** Item 6's label is updated in the same PR; it is test metadata only.

## Status

Implemented 2026-10-28 by Claude. Owner go-ahead, verbatim: 「這個你自己來，安全清完盡可能覆蓋全部内容就行   ，拿不準的問我」.
- Safety item 2 came first, then items 1, 3, 4, 5 and 6, all within the frozen scope above.
- A coverage probe beyond the frozen list found landscape heights below 360 px still failing. I asked the owner, who chose the option labelled 「G13 先上，超矮橫向另開卡 (Recommended)」. That work is [G14](G14-ultra-short-landscape.md).

The receipt follows.

## Implementation receipt (2026-10-28, Claude)

**Test first: 253130f (test only).** `web/e2e/g13.spec.ts` encodes the frozen acceptance.
- **Eight layout tests**, one per frozen viewport. Each runs zh-TW and en in fresh browser contexts and audits two things:
  - the welcome Start button;
  - every distinct school state reached by replaying the G12 ordinary-control fixture (`numerical-results/g12-school-flight.json`) through the `?test=1` hooks: open, retry, armed, each lesson step and axis, pause, resume, and retry again.
- **A state passes** when all of these hold:
  - at scrollTop 0, the school panel intersects none of the header, the course clock, the course gates or the `.actions` buttons;
  - the clock and gates are hit at their own centres;
  - Safe stop, Retry and Close (and Start on the welcome) are hit at their own centres, are at least 44 px, and sit at least 8 px from `#arm`, `#disarm` and both sticks;
  - the provisional-difficulty line is inside the panel and is hit at its own centre;
  - the page itself does not scroll.
- **Four native-touch tests**, at 800x360 and 844x390 in both languages:
  - Start and Flight school are tapped with the touchscreen;
  - the quad is armed through the test hook, then the centre of Safe stop is tapped. Expected: disarmed, paused, no lesson completed, takeoff step back to zero;
  - after Retry, a 0.7 s CDP touch hold on Safe stop must never arm. The 0.6 s ARM hold must not start from Safe stop.
- **Item 6:** `web/e2e/g12.spec.ts:35` now reads `difficulty:'provisional, accepted for release by the owner 2026-10-28'`. Test metadata only.

**First red: 12 of 12 failed** (log sha256 012a9eb1…). It ran on a clean worktree of 253130f with its own dev server, so no source changed during the run. First failure per test:
- **320x568 welcome, zh-TW:** `#start` is hit as `.actions` at its centre, and sits 0.0 px from `#arm` and `#disarm` (item 4).
- **360x800, 390x844, 412x915, 800x360 and 844x390 welcome, zh-TW:** `#start` sits 0.0 px from `#left-stick`. The card had not listed this contact; the frozen 8 px rule catches it.
- **650x900 and 704x900:** Safe stop and Retry are 60x31 and Close is 82x31, all under 44 px.
- **320x568 school states, zh-TW:**
  - the panel covers the header (296 px²) and the course clock (1097 px²);
  - the clock is hit as the panel at its centre, and the gates as the field;
  - the buttons are 52x26;
  - the provisional line is hidden under Close.
- **800x360 zh-TW touch:** after the centre tap on Safe stop the quad is still armed. This is the safety bug.
- **844x390, both languages:** the Flight school tap times out because the HUD's metric subtree intercepts it.
- **800x360 en touch:** arming failed before the tap. The product's 250 ms frame guard had paused and disarmed the page ("Frame interruption over 250 ms — paused and disarmed."). This red is not a layout failure; the 800x360 layout audit is red in its own test.

**Fix: 5437ad4.**
- **Markup** (`web/src/main.ts`, two template lines). The school panel is split into `.school-body` (title, feedback, progress, help) and `.school-foot` (the provisional line and the three buttons). The welcome text moves into `.welcome-body`. No text, id, handler or attribute changes.
- **CSS:** one appended G13 block in `web/src/style.css`.
  - **The panel is two flex blocks.** The lesson text scrolls inside `.school-body`. The footer always stays in view, with 44 px buttons in a grid. No `position: sticky`: in Chromium at 844x390, a sticky footer inside the scrolling panel left a painted copy below the panel that could not be hit.
  - **601–850 px (item 3).** While the school is open, the course card is capped at 310 px and the panel starts to its right.
  - **Portrait up to 600 px, school open (item 1).** The course card becomes a 46 px strip with only the clock and gates. The panel hangs below it, sized to its content, and never reaches the sticks (coarse) or the notice and actions (fine). Up to 480x600 the strip sits at 83 px.
  - **Portrait welcome up to 600 px (item 4).** The card ends above the sticks or the actions. Its text scrolls inside `.welcome-body`; Start and the fine print stay in view.
  - **Height up to 550 px, landscape phones (item 2).** The header is compact.
    - School closed: the course card is a grid above the left stick, with the course and Flight school in row 1 and the clock and gates in row 2.
    - School open: a course strip sits top-left and the school panel top-right, both above the sticks.
    - The welcome card sits between the sticks.

**Green at 5437ad4: G13 spec 12 of 12** (4.1 min, log sha256 4c6c213b…).

**Full local verification at 5437ad4** (log sha256 a945e459…):
- `npm run reference` passes;
- `npm test`: 15 files, 135 tests pass;
- `npm run build` passes;
- `npm run test:e2e`: 61 passed, 9 failed in 25.2 min.

During that run, another task's Chromium held the load near 6 on 4 CPUs. The 9 failures are all timing-sensitive:
- G10 course timing and the G10 250 ms guard test;
- six player specs (`actual Chromium`, `deterministic browser physics`, `Acro yaw`, `replay export`, `mobile 412`, `production keyboard`);
- G13 touch 844x390 zh-TW.

Four of the failed pages show the product's own "Frame interruption over 250 ms" pause. The others failed waiting for the 750 ms ARM hold or for 480 replay events. The machine stayed loaded, so I did not rerun them locally on a quiet machine; official CI on the exact head is the gate, as it was for G12.

**Test hardening: 60dff62 (test only).** The G13 touch failure above was the 250 ms guard pausing and disarming the page before the tap. That exposed a weak spot: a guard stop also disarms and pauses, so it could have let the Safe stop assertions pass without the tap ever reaching Safe stop. The test now does three things:
- Before the tap, it accepts only that explicit guard condition and resumes as a player would, at most three times, as the G10 and I18N specs already do.
- After the tap, the stop reason must be Safe stop's own: `Paused and disarmed. Resume, then ARM again.`
- After the hold, the reason must be either the one Retry left or Safe stop's own. A guard stop or an ARM fails.

The attachment also records the snapshots taken before the tap and before the hold.

**Tablet welcome: 2da99c0.** The coverage probe below found one more Start contact: at 1024x768 coarse (zh-TW) Enter sat 0 px from the left stick; en had 8.1 px. main has the same layout.
- The fix: on touch screens wider than 600 px and taller than 550 px, the welcome card's bottom is anchored 8 px above the sticks. That is 126 px plus the 118 px stick, or 190 px plus the stick up to 850 px wide.
- Measured at 1024x768, 768x1024, 1280x800, 820x1180 and 1440x900 coarse: Enter sits 71–94 px above the left stick's top in both languages.
- Fine pointers and screens up to 600 px wide are unchanged.

**Results at 2da99c0.**
- G13 spec with the hardened touch tests: 12 of 12 pass (5.8 min, log sha256 da8e9797…).
- Scratch layout probe over the frozen eight viewports plus the G12 regression views (1440x900, 412x900, 390x900 and 360x900 fine; 360x800 coarse): 442 states, 0 violations (log sha256 940c0015…).
- Red control: the hardened spec on main's code (worktree of 253130f with the 60dff62 spec; `web/src` identical to main fcc4c46). 12 of 12 failed (log sha256 0eee24b3…):
  - the eight layout tests failed on layout;
  - 844x390, both languages: the Flight school tap was intercepted by the HUD until the 90 s timeout;
  - 800x360, both languages: the new reason check failed, receiving "Frame interruption over 250 ms — paused and disarmed." The guard had stopped the loaded page after arming. Without the 60dff62 check, that stop would have satisfied the old disarmed-and-paused assertions. The layout red for this test is the first red's: armed after the Safe stop tap.

**Beyond the frozen list** (Chromium emulation; coverage, not acceptance). The same probe ran at 360x640, 375x667, 414x896 and 430x932 portrait; 667x375, 740x360, 896x414, 915x412 and 932x430 landscape; and 768x1024 and 1024x768 coarse tablets (log sha256 981199d0…).
- Eleven sizes pass in both languages in every state.
- 568x320 fails in all 16 school states in each language:
  - Safe stop and Close sit 0 px from the right stick;
  - the panel covers the header and is clipped to 49 px.

  main is worse at that size: its school panel is off-screen, so Safe stop cannot be seen or tapped. Heights below 360 px go to G14.

**Known limits, not fixed**
- **Landscape heights below 360 px:** see G14.
- **320x568:** in the school, only the lesson title is visible at scrollTop 0; the instructions scroll inside `.school-body`. The welcome text also mostly scrolls, while Start and the fine print stay in view.
- **Browser features:** the layout needs `:has()` and `dvh`, as G12's did. Without them the school-open rules are skipped and the old overlaps return.
- **Emulation only:** all evidence is Chromium emulation. No physical phone, tablet or controller was tested.

## Codex P2 fix and second verification (2026-10-28, Claude)

**Codex review on PR #13 (P2, comment 4400999024).** At 568x400 in short landscape the header wraps its menu onto a second row, and the course card at 53 px took every tap on Aircraft, Controls, Physics and Pause.
- **55993cf (test only).** A new test runs five short-landscape sizes (480x400, 568x400, 600x400, 640x360, 900x400), coarse and fine, both languages, in the welcome, flying and school states. Every header menu button and the language select must be hit at its own centre, and no card may overlap the header or leave the viewport. Red on 67ac236's CSS: 6 failed (480x400, 568x400 and 600x400, coarse and fine), 4 passed.
- **d504b67 (fix).** From 481 px wide the short-landscape header does not wrap; the brand may shrink and ends in an ellipsis. `--ls-top` places the cards 8 px below the header: 77 px up to 480 px wide, 53 px in between, 61 px above 850 px. The landscape welcome card stays inside the viewport. On touch screens wider than 850 px and taller than 550 px the welcome card keeps main's vertical position and starts at max(146px, 7%), right of the left stick, so the course select above it stays reachable (2da99c0 had lifted it over the select at 1024x768).

**Second verification, of d504b67.** Five independent Chromium sweeps compared main (`web/src` identical to fcc4c46) with d504b67, on Chrome for Testing 153 headless shell.
- Gate: `tsc`, 130 unit tests and the build pass; the G13 spec passes 22 of 22 (5.6 min).
- Frozen probe: 442 states, 0 violations, with geometry identical to the 2da99c0 run. Extra probe (12 sizes): 408 states, 114 violations, all at 568x320 (G14). The 32 panel/header overlaps that 2da99c0 had at 568x320 are gone.
- Landscape sweep, 27 sizes: the Codex P2 class is gone everywhere. The header is one row from 481 px (44–45 px; 51–53 px above 850 px). A dense resize scan checked every width from 481 to 1300 px at heights 360, 400 and 540, coarse and fine, both languages, in three states: 29,520 states, 0 failures.

It also found four problems, fixed in round 3 below:
- **320x480 coarse, portrait, school open:** Close's centre was under the right stick and Safe stop sat 0 px from it. The same happened at 360x540 and 414x550. The short-landscape rules (height up to 550 px) also applied to short portrait phones, where the sticks are 100 px tall at bottom 245 px rather than 118 px at bottom 100 px. Present since 5437ad4.
- **800x360, a frozen view:** the lesson text kept a 4 px strip (4 of the title's 15 px). Present since 5437ad4. The frozen audit does not check the title, so the frozen test passed.
- **Fine-pointer portrait windows** (360x900, 412x900, 480x800, 600x900): the welcome card covered the course select, although these views have no sticks.
- **Landscape welcome card under the right stick** from 481 to 753 px wide (667x375: 10,005 px²). Not a regression: main's card covered the left stick instead.

The problems it found that G13 does not fix are listed under the updated known limits below.

## Round 3: short screens and touch tablets (2026-10-28, Claude)

**Test first: 0063d7c (test only).** Two tests in `web/e2e/g13.spec.ts` are extended or added.
- **Header (extended).** The 55993cf header test also runs 601x600 and 700x560, coarse and fine. It is renamed "G13 header stays reachable".
- **Short screens (new).** It covers 22 coarse screens, in both languages and in the welcome, open, armed and paused states:
  - portrait: 320x480, 360x540, 360x560, 414x550, 375x600, 481x520, 500x500 and 540x560;
  - landscape: 640x360, 667x375, 740x360, 780x360, 800x360, 900x360, 932x430 and 900x550;
  - touch tablets and windows: 601x560, 700x560, 850x600, 900x551, 640x632 and 800x700.

  It requires:
  - Enter and the three school controls to be whole, inside the viewport, hit at their own centres, and at least 8 px from ARM, Disarm and both sticks; the school controls also at least 44 px;
  - the provisional-difficulty line to be inside the panel;
  - in landscape, at least 12 px of the lesson title at scrollTop 0;
  - the header controls to be hit at their centres in the welcome state, and Pause and the language select in the school states;
  - the course select to be hit at its centre at 640x632, 800x700 and 900x550.

  One exception: below about 500 px of height on narrow phones (320x480), Enter may lie over the stick band, which does nothing before Start. It must still clear ARM and Disarm.

First red on d504b67's CSS: 19 of 36 failed (log sha256 ccea8c75…).
- Header: 601x600 coarse and fine, and 700x560 coarse.
- Short screens: 320x480, 360x540, 414x550, 540x560, 640x360, 740x360, 780x360, 800x360, 900x360, 900x550, 601x560, 700x560, 850x600, 900x551, 640x632 and 800x700.
- The other 17 passed, including the five original header views.

**Fix: 4f8fb33 (CSS only; each rule is commented in place).**
- **Landscape only.** The short-landscape rules now also require `orientation: landscape`. On short portrait phones the sticks are 100 px tall at bottom 245 px, not 118 px at bottom 100 px.
- **Narrow portrait school panel.** The panel never shrinks below 72 px, the height of the controls and the provisional line. Where the band below the course strip is shorter, it rises over the strip, and below about 490 px of height over part of the header, instead of reaching the sticks, which are live during lessons. Its top padding and footer gap are 4 px, so 320x568 shows the whole lesson title and 16 px of text (7 px at d504b67).
- **Narrow portrait welcome card.** It never shrinks below 131 px and its top stays below the header. Below about 500 px of height it extends over the stick band instead, which does nothing before Start and is drawn under the card.
- **Reserves from the real stick band.**
  - 481–600 px touch: 316 px instead of G12's 357 px (the narrow-phone band); 226 px up to 550 px tall, where the sticks move to bottom 100 px.
  - Taller than 550 px: the panel keeps main's position and stops 8 px above the sticks: `min(350px, 100dvh − 416px)` from 601 to 850 px wide, `min(350px, 100dvh − 352px)` above.
- **Touch-tablet welcome card, 601–850 px.** Its height is `max(100dvh − 514px, 131px)`, so its top stays below the course select.
- **Header, 601–850 px at any height.** It no longer wraps. Only en at 601–607 px changes: the menu had wrapped to a second row (117 px).
- **Short landscape.**
  - The panel's padding is 4 px at the top and 9 px at the bottom, which keeps the controls 10 px above the sticks. The footer gap is 2 px, with 3 px of padding.
  - Lesson text: 24 px at 800x360 and 16 px at 900x360 (4 px and 0 px at d504b67).
  - The course strip has no empty first row.
  - The welcome card is `min(470px, max(300px, 100vw − 292px))` wide and ends before the right stick. Above 850 px it starts at 212 px, clear of the en course select.
- **Brand.** d504b67's 13 px only ever applied above 850 px wide. It is removed, so main's sizes apply again (15 px up to 850 px, 20 px above). The 1 px letter spacing stays up to 850 px only.
- `a86f20c` is d504b67 with a corrected commit message; the tree is identical.

**Results at 4f8fb33.**
- Local Chromium emulation, web files identical to 4f8fb33 (style.css sha256 286a82eb…, g13.spec.ts 8b24f8e3…):
  - G13 spec 48 of 48 plus G12 spec 8 of 8: 56 passed in 10.5 min (log sha256 9427f7c7…).
  - Two earlier runs at the same files did not finish green. In one, a container restart stopped the run after 52 of 56 tests. In both that run and an earlier one at an intermediate CSS, G12's 1440 test failed once at "a 200 ms Space press does not arm": under heavy machine load the 200 ms wait outlasted the 600 ms ARM hold. That test uses a fine pointer at 1440x900 and keyboard timing; it passed on the quiet rerun and in CI.
  - `npm run reference`, then `npm test`: 135 of 135 (log sha256 d45b1c73…). `tsc` and `npm run build` pass.
- Official CI, PR run 40788118257 on the PR merge commit c5f5117 (head 4f8fb33): unit 135 of 135 in 15 files, strict build, Chromium 106 of 106 in 15.8 min; deploy skipped. Artifact `player-verification-c5f5117…`, id 12861560475, sha256 9b505a50….
- A final dense A/B sweep of 4f8fb33 against main was started and stopped unfinished on 2026-10-29, after the owner set the release bar: 「美術過得去，人可玩流暢玩狀態就行」. Its partial output is not used as evidence.

**Known limits (at 4f8fb33; Chromium emulation)**
- **Short portrait phones** (up to 480 px wide, below about 560 px tall), school open:
  - The 72 px panel overlaps the bottom of the course strip (360x540: 6 px) and, below about 490 px tall, the header (320x480: the panel starts at 63 px, the header ends at 77 px).
  - The lesson text keeps 2 px at 320x480 and 360x540; the HUD notice still shows the current instruction.
  - Safe stop, Retry and Close are hit at their centres, 10 px from the sticks; Pause and the language select are hit at their centres.
- **Narrow portrait welcome below about 500 px tall** (320x480): Enter lies over the stick band, which does nothing before Start. It is hit at its centre and at least 126 px from ARM and Disarm.
- **481–600 px wide, about 560 px tall** (540x560, zh-TW): the welcome card overlaps the bottom 2 px of the wrapped 120 px header; every header control is still hit at its centre.
- **320x568 (frozen view):** the school shows the whole lesson title and 16 px of text; the welcome card shows Enter and the fine print, and its text scrolls.
- **Moved to G14:** landscape heights below 360 px (568x320: Safe stop and Close 0 px from the right stick); landscape widths up to 480 px (480x400, where main's narrow-phone stick positions also apply); the collapsed course strip at 481–640 px short landscape with the school open.
- **zh-TW, pre-existing on main and unchanged:**
  - Disarm's centre is under the right stick on coarse screens wider than 850 px: 873x393 to 960x540 in short landscape, and 900x700 to 1440x900 on tablets. This is safety-relevant and is proposed as its own follow-up card.
  - Flight school is under the left stick at 360x640 and 375x667 coarse, and at 601x560 in the welcome state.
- **480x400 with a fine pointer:** the language control covers the top 5 px of Pause, which is still hit at its centre.
- The layout needs `:has()` and `dvh`, as G12's did. All evidence is Chromium emulation; no physical phone, tablet or controller was tested.
