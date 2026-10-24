# Pinned comparison reference

`powertrain.py`, `flight.py`, and the three `fpv-*.md` documents are verbatim
copies from PR 2 commit `839f775fd4c32563d3ee9fc2ed8967b2d9dbf9cc`.
Original research is preserved in its original PRs; this independent player
branch does not merge or modify it. SHA256 source checks are recorded separately.

Only homogeneous 4S2P parameters are ported into the browser powertrain. Python's
heterogeneous model, thermal research and empirical claims are not imported.
Rapier collision/rigid-body integration replaces Python's RK4/contact at runtime.
Comparisons exclude contacts and use declared tolerances, not bit identity.

The repository's original code has no selected project-wide license. This does
not change that choice. Dependency licenses and notices are recorded for the
browser bundle; no external research dataset is included in the player bundle.
