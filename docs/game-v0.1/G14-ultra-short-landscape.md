# G14 ultra-short landscape school layout — follow-up card

Opened 2026-10-28 by Claude, from the owner's decision on G13.
- Option chosen: 「G13 先上，超矮橫向另開卡 (Recommended)」.
- Option text: 「G13 先照現在的範圍上線（凍結 8 個＋額外 11 個尺寸全過）。超矮橫向另開一張卡，做 2–3 種排法拍圖給您挑，例如把教學按鈕放到兩個搖桿中間，或教學時收起選單列。」

This card records the problem and the plan. It authorizes no implementation, merge or publication until the owner has picked an arrangement from the images.

Base: G13 as released (head 2da99c0 plus its docs when opened; updated at G13 round 3, 4f8fb33). Once merged, the base is main.

## Problem

Landscape touch screens less than 360 px tall. The 568x320 measurements below are Chromium touch emulation at G13 head 2da99c0. They are not physical-phone evidence.

Such heights are common in real browsers, not only on old phones. In landscape, the browser's own bars often leave a 300–355 px tall page, for example in Android Chrome with the address bar showing.

**568x320 at G13**, school open, all 16 states of the G12 fixture walk in each language:
- Safe stop and Close sit 0 px from `#right-stick`, against the 8 px rule. Safe stop stays 103–105 px from ARM, and its centre hits itself.
- At 2da99c0 the panel overlapped the header in every state: 9880 px² in zh-TW, 9500 px² in en. Since d504b67 the short-landscape header is one row from 481 px wide and this overlap is 0 in all 32 states.
- The panel overlaps the course gates in all 16 en states (up to 756 px²) and in 2 zh-TW states (602 px²).
- The panel is 49 px tall, so the 44 px buttons and the provisional-difficulty line are clipped.

**568x320 at main fcc4c46.** The school panel is off-screen, at y −172 to −37. Safe stop, Retry and Close cannot be seen or tapped.

**Why it does not fit.** The geometry at height H:
- With the height at most 550 px, the sticks sit 100 px above the bottom and are 118 px tall, so their top is at H − 218.
- The header ends at 45 px. (At 2da99c0 its menu wrapped to a second row at 568 px wide and it ended at 78 px; since d504b67 it stays one row from 481 px wide.)
- The panel starts at 53 px and must end 8 px above the sticks' top.
- That leaves a band of H − 279 px: 41 px at H = 320, while the panel needs about 80 px (about 73 px at 4f8fb33: a 48 px footer, 13 px of padding and a 12 px title line). The G13 rule `max-height: calc(100dvh - var(--ls-top) - 218px)` (271 px at the 53 px top) sized it for H ≥ 360.

**Added at G13 round 3: landscape up to 480 px wide.** A second G13 verification sweep (of d504b67) found that main's narrow-phone positions for the sticks (bottom 245 px, 100 px tall) and the actions (bottom 132 px) apply in landscape too, whatever the height. At 480x400 coarse:
- Close (Return to free flight) sits on the right stick and Safe stop 5.3 px from it. A tap on Close while armed in a lesson moves the roll/pitch stick.
- Enter is under ARM. In zh-TW, the course select's centre is under the left stick.
- Main is not usable there either: its school panel is mostly above the screen, and Enter is under the HUD.

**Added at G13 round 3: short landscape 481–640 px wide, school open.** The course strip's clock column collapses to 0–23 px and the gates are clipped; below about 582 px wide the panel covers part of the gates (568x400 en: 756 px²). Main clips both out of view.

**Related, not in this card's scope: short portrait phones.** Below about 560 px tall the G13 round-3 panel rises over the course strip and part of the header instead of reaching the sticks. Arrangement B or C below could serve these too, if the owner wants.

## Arrangements to prototype and show the owner

Each arrangement gets images at 568x320, 640x320, 740x304 and 844x340, plus 480x400 and 568x400, in zh-TW and en, school closed and open. Prototypes are scratch CSS only until the owner picks one. For widths up to 480 px an arrangement must also place the sticks and the actions for landscape.

- **A. Controls between the sticks.** The school panel sits in the band between the two sticks and above the notice: 276 px wide at 568, 79 px tall at H = 320. The course strip stays top-left. This covers the middle of the view while the school is open. Below about 320 px of height the course strip no longer fits above the left stick.
- **B. Menu row folded while the school is open.** At these heights the header keeps only the brand, language and Pause, so the panel can use the top band. This changes what the header offers during lessons.
- **C. Compact school bar.** Safe stop stays a full 44 px target in view; Retry, Close and the lesson text open from a small expander. This is a new interaction, so it needs its own acceptance.

## Acceptance (to freeze after the owner picks, before code)

- The G13 geometry rules hold at the heights the chosen arrangement covers. These are the 44 px targets, the 8 px clearance from ARM, Disarm and both sticks, and no overlap with the header, clock, gates or actions. They hold in every state of the G12 fixture walk, in both languages.
- The landscape native-touch test passes at those heights: a Safe stop tap never arms, its stop reason is Safe stop's own, and a 0.7 s hold never arms.
- The G13 viewports and the eleven extra sizes that pass at G13 stay passing.
- No change to physics, control law, input mapping, the 600 ms ARM hold, the 250 ms frame guard, lesson thresholds, scoring, storage or workflows.

## Status

Opened, not started. No code, test or workflow has changed for this card.
