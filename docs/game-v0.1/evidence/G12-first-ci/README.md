# G12 first official CI failure receipt

- PR run: https://github.com/lijiabao1998/Physical-Fpv-Simulator/actions/runs/40440812714
- Exact candidate: `e5e6084c1932b62e0e7c5a111e70a86c61c439cc`.
- Parent-retrieved original log summary: 129 unit tests passed; Chromium 47 passed / 7 failed. Three failures belong to inherited G10 settling/bilingual assertions; four G12 cases were blocked at initial `#school-open` because the original `#welcome` intercepted pointer events. Raw first-run log is retained separately by the parent; this note is not a substitute for that original log.
- Cause: G12 browser setup omitted the existing native Start action after loading. The welcome screen is expected product behavior, not a product defect or reason to remove its pointer protection.
- Minimal correction: invoke the existing `[data-testid=start]` by normal click before School for desktop and Replay cases, and normal tap for real coarse-pointer contexts. This covers all three setup forms (four existing desktop cases, three new touch cases, one new Replay case).
- No forced click, DOM removal, product/welcome change, physics change, threshold change, test deletion, or remote write. Original assertions remain. The three touch and one Replay additions were not present in the first official head and therefore are not counted as first-run passes or failures.
- Local TypeScript checking/test discovery only; corrected browser execution remains unverified until an authorized exact-head run. The first red result is retained, not relabelled green.
