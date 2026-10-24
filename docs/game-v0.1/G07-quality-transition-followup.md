# G07 quality transition regression, frozen before fix

Base b335968a80297d803de01d0be3103fffeac7c152.
Review https://github.com/lijiabao1998/Physical-Fpv-Simulator/pull/5#discussion_r4367281661
reports Auto-low and manual Low share the same boolean, so changing between them
does not call resize/setQuality and pixel ratio remains stale until a resize.

Acceptance: on1440x900, Auto-low stays at480k pixel cap; selecting manual Low
immediately uses native1x pixels; selecting Auto again immediately restores cap,
without resizing. Keep all17 Chromium cases,57 numerical/unit checks, physicsdt,
250ms safety, models and research untouched. No security or dependency changes.
Capture first-red actual Chromium before changing product code; retain failure.

## Actual first RED and minimal repair
Run40100964234/job120892835519: original17 browser tests passed; new18th failed
exactly as reported, expected manual Low width1440 but actual876 after selection,
withoutresize. Artifact12562981820, ZIP SHA256
f2065c693ffe672d39f7e24272e47be29ff9419b829b9bf7f94cc9e24a08fdb9.
Fix tracks last applied quality mode separately from shadow/low boolean and
applies mode change before rendering. Auto starts conservatively; subsequent
measured auto promotion remains unchanged. All original thresholds unchanged.
