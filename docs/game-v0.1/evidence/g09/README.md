# G09 incremental evidence

G08 original browser test files are preserved byte-for-byte as .txt evidence before G09 storage semantics change. Their physics and completion criteria are not weakened. G09 reads configuration-class records; pre-G09 unclassified keys remain immutable legacy records and are explicitly tested unchanged. No old numerical fixtures or thresholds changed.

First local new-test failure retained: an exact floating-point equality expected 2 but interpolated 1.9999999999999998. Only this newly introduced test uses a 12-decimal numerical assertion now. Original 70 tests passed. Browser checks and screenshots are pending until an actual official Chromium run completes.

Hardware controllers/phones/battery measurements remain NOT VERIFIED. This independent Draft candidate has no publication approval. Existing G08 cloud display timing limits remain, without claims of physical-device frame-rate acceptance.

First official product run 40162228106 at 740aae9 passed all 77 unit/numerical and 25 actual Chromium cases. Artifact 12587455441 preserves all three viewport screenshots and raw reports. Visual inspection found the expanded race panel touches the right 360px edge; a bounded responsive width and explicit native bounding-box assertion are added, not a relaxed gate. Additional collision/no-write tests bring the pending revised candidate to 79 local tests and 26 browser cases. Completion PNGs use explicit synthetic gate placements to verify timing/UI, not claimed human-flown laps.
