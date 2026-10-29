# G11 bilingual integration / release decision

Owner wave source: Sentinel_7309337460b08191a08e3e0e41509211, uploaded instruction
SHA256 4ce681a3b714cf33d4950262f901e516f72ab7daa249f3acd0f17e90be9d7d0b.
Reuses candidate 672bb2fe6b107aafbbb4286323b5de5d91a2556c and bilingual G10
41b645e41371a9ce02fa8e4a5c9813ba57b1e075. Main remains d0e96da.

Read original frozen G11 card, PR10, prior cache and outline first reds/results,
and 579909b one-round plan and raw primary summary in PR10. No new causal evidence
in presentation integration warrants another performance investigation or a product
geometry/cache change. All ghost, scene, physics, input, reference and original
performance-test logic remains unchanged. Complete exact-head standard CI will
retain its ordinary primary measurements, not open a new diagnostic/noise campaign.

Historical immutable primary run 40206797578: CPU OFF/ON/ON/OFF
0.481667 / 0.636667 / 0.704167 / 0.492500 ms; first pair +32.18%, reverse +42.98%.
Both exceed frozen 20% requirement. rAF p95 50.1 ms does not waive CPU. Cache misses
stay 5, one Ghost/three programs/68 geometries/six textures stable. Secondary GC
correlation does not explain primary failures. Keep all originals and reservation.

## Decision choices
A (recommended): keep G11 Draft with CPU reservation. Review G09/G10 independently
for release only after their exact-head CI and raw visuals, while completing G12
on G10 without Ghost. No additional product or CPU risk; missing Ghost is explicit.
B: separately approve one bounded low-cost visual redesign with a new pre-code
acceptance card that preserves existing hard gates. Costs new implementation and
visual review; no promise the redesign will clear CPU.
C: retain current feature/evidence for owner technical judgment, but do not auto-
waive or pass the frozen requirement. Current uncertainty blocks formal release.

This integration is candidate work, NOT G11 performance acceptance, merge or Pages
authorization. All physical controllers, phones, aircraft and batteries untested.
G12 is a separate candidate, never silently included in G11.
