# G14 ultra-short landscape school layout — follow-up card

Opened 2026-10-28 by Claude, from the owner's decision on G13.
- Option chosen: 「G13 先上，超矮橫向另開卡 (Recommended)」.
- Option text: 「G13 先照現在的範圍上線（凍結 8 個＋額外 11 個尺寸全過）。超矮橫向另開一張卡，做 2–3 種排法拍圖給您挑，例如把教學按鈕放到兩個搖桿中間，或教學時收起選單列。」

This card records the problem and the plan. It authorizes no implementation, merge or publication until the owner has picked an arrangement from the images.

Base: G13 as released (head 2da99c0 plus its docs). Once merged, the base is main.

## Problem

Landscape touch screens less than 360 px tall. The 568x320 measurements below are Chromium touch emulation at G13 head 2da99c0. They are not physical-phone evidence.

Such heights are common in real browsers, not only on old phones. In landscape, the browser's own bars often leave a 300–355 px tall page, for example in Android Chrome with the address bar showing.

**568x320 at G13**, school open, all 16 states of the G12 fixture walk in each language:
- Safe stop and Close sit 0 px from `#right-stick`, against the 8 px rule. Safe stop stays 103–105 px from ARM, and its centre hits itself.
- The panel overlaps the header in every state: 9880 px² in zh-TW, 9500 px² in en. The header's menu row is under it.
- The panel overlaps the course gates in all 16 en states (up to 756 px²) and in 2 zh-TW states (602 px²).
- The panel is 49 px tall, so the 44 px buttons and the provisional-difficulty line are clipped.

**568x320 at main fcc4c46.** The school panel is off-screen, at y −172 to −37. Safe stop, Retry and Close cannot be seen or tapped.

**Why it does not fit.** The geometry at height H:
- With the height at most 550 px, the sticks sit 100 px above the bottom and are 118 px tall, so their top is at H − 218.
- The header ends at 45 px when it fits on one row. At 568 px wide its menu wraps to a second row and it ends at 78 px.
- The panel starts at 53 px and must end 8 px above the sticks' top.
- That leaves a band of H − 279 px: 41 px at H = 320, while the panel needs about 80 px. The G13 rule `max-height: calc(100dvh - 271px)` sized it for H ≥ 360.

## Arrangements to prototype and show the owner

Each arrangement gets images at 568x320, 640x320, 740x304 and 844x340, in zh-TW and en, school closed and open. Prototypes are scratch CSS only until the owner picks one.

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
