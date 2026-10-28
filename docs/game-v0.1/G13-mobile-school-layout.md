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

Opened, not started. No code, test or workflow has changed for this card.
