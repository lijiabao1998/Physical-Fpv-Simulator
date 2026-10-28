# G10 Three-dimensional courses 1.0

Base: verified G09 956130a4a6c8b40f423fd754fc04212e23bdb3df, 79 unit/numerical and 26 actual Chromium passes in run 40162791773. Independent stacked Draft. Owner explicitly authorizes candidate research, implementation, tests and evidence, not main merge or Pages.

## Frozen product scope
Preserve Training Straight's exact five gates, original crossing semantics, legacy records/replay and all G07/G08 physics/safety. First implement and verify British Slalom: turns, climb/dive, varied 3D gate orientations. Then Industrial Run: original procedural British warehouses, beams, columns, narrow passages, low obstacles; visible structural boxes and Rapier colliders share geometry. Stable course IDs/versions; course switch disarms/resets. Missing replay course means Training Straight. G09 splits and records isolate course/version/physics/exact assembly. Native selection, progress, splits, PB and retry.

## Gates before release review
Directional continuous segment-plane crossing, local aperture intersection and aircraft collider projection, ordered gates. Positive/negative tests: forward/reverse/oblique/outside/edge/missed/repeated/wrong-order, oriented mesh/collider parity. Same-input replay and fixed 240Hz at normal/low FPS; 250ms interruption guard unchanged. Preserve original reference/energy/build/input/control/assembly tests. Real Chromium 1440/412/360, FPV and Chase. Compare courses for render CPU, frame intervals/FPS, draw calls, triangles, load time and memory, with source and scope stated. Do not infer physical-phone or hardware validation from cloud measurements; disclose ~20FPS cloud baseline and investigate repeatable major regression. Preserve first reds and raw screenshots. No force push, history rewriting, reduced thresholds, research PR changes or unapproved external assets. G11 Ghost Racing only feasibility/dependencies after G10.

## Release integration receipt (2026-10-28, Claude)
Owner decision 2026-10-28, relayed to this step by the orchestrating Claude session
(no owner message ID was available to this step): 「G10＋G12 一起上」. Option text:
also accept G12's provisional difficulty; integrate both, merge in order after CI is
green, and publish; the landscape "Safe stop under ARM" issue gets a separate card.
This is the main-merge and Pages authorization the base line above withheld, only
after green CI and in order G10 then G12. Frozen scope and gates above are unchanged.

Local branch g10-int: G10 head 02b2455 (PR #9) plus a real merge of main 8aae927
(/fpv/ base, zh-TW SEO/OG meta, og.jpg, check-build base): merge commit 6dc3840,
parents 02b2455 and 8aae927. Clean automatic merge, no textual conflict; main.ts
auto-merged with main's source link and every G10 course change. The tree is G10 plus
main's 8aae927 delta exactly. Follow-up 2fbf85c moves the G10-added g10.spec.ts from
/Physical-Fpv-Simulator/ to /fpv/ (4 page URLs, 2 module imports), the substitution
main made in the g08/g09/i18n/player specs; no assertion, timeout or threshold
changed. No tracked file under web/ names the old base. README.md and RELEASE.md still
name the old address; main 8aae927 left them, so this does too. No G11 commit.

At 2fbf85c (Linux cloud container, Node 22.22.0, Python 3.13.17, NumPy 2.3.5; CI uses
Node 24 and Python 3.12): npm ci pass; npm run reference pass, fixtures byte-identical;
npm test 13 files / 123 tests pass (twice); CI=true npm run build pass (strict tsc,
vite, check-build: base /fpv/, dirty=false, og.jpg in dist). Not run in this step:
real Chromium e2e, exact-head official CI, Pages. Main merge still needs the
exact-head official workflow green (RELEASE.md).
