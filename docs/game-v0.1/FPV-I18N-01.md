# FPV-I18N-01 — zh-TW / English UI

Frozen before implementation, 2026-10-26. Owner request Sentinel_2a29292f05688191b24e2c5ed42a99b9. Fresh main ce51a64a711b1c1760f87a5b9848b27ac5383a89 (released G08). All ten PRs and branches/issues checked: no identifier conflict; PRs 8–10 and research remain excluded. No AGENTS.md or repository skills in exact main tree.

Acceptance: full welcome/navigation/HUD/ARM/touch/Controls/Aircraft/Physics/training/errors/loading/accessibility localization; English retained; clear language selector; independent physical-fpv-ui-lang-v1, saved valid choice first, browser Chinese preference then English. Switch changes presentation only: no aircraft/physics/score/calibration reset or existing storage changes. Preserve settings pause/disarm, fixed-step/input mapping and scientific synthetic/unvalidated caveats, units/precision and 3D brand art. Original tests/thresholds stay unchanged. Add focused unit and actual official Chromium desktop/mobile tests, switch/reload/storage failures/interruption coverage and screenshots. Preserve first reds and exact-head evidence. Draft PR only; no Ready, merge, deploy or other features.

Local browser socket restriction is not bypassed. Normal existing GitHub CI is browser verification route. Disk scarce; dedicated /tmp snapshot with existing dependencies, no deletion of other work/evidence.

Status: acceptance frozen; implementation and verification pending.

## Implementation and observed verification

In-place bilingual text/ARIA/lang/title and metadata, no simulator/control reconstruction. Explicit original option IDs survive translation. Language is global and available with drawers open; original drawer pause/disarm and import-generation guards remain unchanged. Browser primary Chinese locale defaults to zh-TW. Browser/renderer-provided diagnostic details and user filenames remain verbatim under translated explanations; raw exported replay and identifiers are untouched.

First head 42b8720405797f8655f93fdf1ac9010fde3e6f2e: push 40297707559 and PR 40297766376 each passed 75 unit + 30 Chromium, deploy skipped. The local 70-test run preceded Python reference generation; all 75 cases ran after generation. PR merge 21918d416daaea5fea6ef6454479e4a5a2151da7 has identical tree 2587441ae8b0af36e28b1c46aea823085d3243ab. Official first artifact hashes: push aeb9f1ee537580893c79ac8022a884c4bbc52d16b52e73ebfc85758c99d508b5; PR b2fa4f2fef5a06e3d2d379e734d134e3ce6bf2afb1cf0c19d0175cacd65002f8.

Polish head c1eca082a66aecb0095f0da33ba86f24c627ab46: push 40298939796 and PR 40298948720 each passed 75 unit + 33 Chromium, deploy skipped. Production desktop/mobile zh/en screenshots and actual coarse-pointer emulation, native ARM, atomic language-change snapshot equality, settings/persistence/storage failure checks passed. Original ZIP hashes: push 9fff5b2c36b032bd77428647b89d21933cd45b71e2f5586e91c5d95c3fb4aeb5; PR 929e5563ea773dbc5d96e9eacad3ea6d03ca1b076081582083f340cf96a49c9d.

Visual review found and retained evidence of (1) redundant Chinese scientific caveat after translation, corrected in c1eca08; (2) virtual-stick captions overlapping safety notice/bright runway and (3) browser-owned English file-picker labels, addressed in the next UI-only patch with caption contrast/position and an accessible localized label that activates the same native file input. Expanded tests assert caption separation and native chooser/malformed-import behavior. Final-head recheck remains required; older greens are not final acceptance.

35 original physics/input/game/view/reference/test/workflow files are SHA256-identical; manifest in evidence/i18n/original-invariants.json. First local missing-module build red retained, no test threshold weakened. Actual physical controllers/phones/aircraft remain untested; viewport/touch emulation is not hardware acceptance. Existing 250 ms safety pauses on cloud rendering remain intentional and visible. No merge, release or deployment claim.
