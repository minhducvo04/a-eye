# client-track result

Implemented the standalone browser/Node ES module without dependencies or a build step.

Files changed:
- `client-web/track.js`: downscaled grayscale conversion; bounded, coarse-to-fine normalized cross-correlation tracker; seed/reseed/drop; conservative loss handling; 10% template refresh on strong matches; immutable anchor coordinate transforms. Usage and assumptions are in its opening comment.
- `client-web/track.test.mjs`: six synthetic tests covering grayscale, 30-frame motion sequences at three patch sizes, 2 px/frame pans and a 12 px jump, noise occlusion, replacement templates on reseed, drop, flat patches, lighting and gradual appearance changes, all requested drawing geometries, and speed.
- `RESULT.md`: this handoff and measured evidence.

Algorithm: share one averaged half-resolution frame among all objects, search within the configured radius using NCC, then refine the best eight candidates within 2 full-resolution pixels. Multiple candidates avoid a small-patch failure caused by downsampling phase. Template long sides are capped at 48 samples by default; coarse templates at 24. Strong matches refresh both levels. Weak matches retain the last accepted bbox and report lost.

Measured speed: **1.390 ms median** for four 48x48 objects on a 320x240 frame, Node v26.11.1 on this machine. The test timed only `update`, with 20 warmups followed by 80 measured updates, and checked every returned position. Synthetic frame creation was outside the timed region.

Final run output:
```text
Tracker median: 1.390 ms (4 objects, 320x240, 80 measured updates, 20 warmups)
Tests: 22; suites: 0; pass: 22; fail: 0; cancelled: 0; skipped: 0; todo: 0
Duration: 448.603042 ms
```

Test: node --test client-web/ - PASS (22 tests, 22 passed, 0 failed, 0 cancelled, 0 skipped, 0 todo; tracker median 1.390 ms)

Limits:
- No real camera or iPhone tested; the Node benchmark does not establish browser end-to-end or iPhone frame rate. Canvas readback, grayscale conversion and rendering are excluded from the update timing.
- Translation only: rotation, perspective and scale changes require fresh server boxes. Resolution changes report lost until reseeding. Large motion outside the search radius and ambiguous/repeated or low-texture regions may fail; this is local template matching, not object recognition.
- The module is not wired into the camera page because page integration is outside package ownership. Feed the seed/reseed frame corresponding to the server box, and use original server ops on each render.
- Anchor transforms support size changes from server boxes. Circles use the mean axis scale for their scalar radius. Arrow tails remain fixed by default; `moveFrom: true` is a documented local-only override, not a contract addition.
- No contracts, README, global settings or other package files changed. Files are left unstaged; no push or publication performed.
