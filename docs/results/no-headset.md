# No headset: Vision Pro code removed (2026-10-25)

Branch `pkg/no-headset`. The Vision Pro app and the headset web mode are gone. Phone pairing stays, because
"another device is the camera" is how a future camera device (for example glasses streaming through a phone) plugs in.

## Removed

- `visionos/` (the whole visionOS app, its PLAN and RESULT).
- `.visionOS(.v1)` from `ios/AEyeCore/Package.swift` (the iOS app does not reference visionOS).
- `client-web/headset.js`, `headset.test.mjs`, `headset_smoke.py`.
- `client-web/agent.js`: `isHeadset` boot branch, headset panel status, step card, typed composer, headset camera
  blocks, headset sound/pair buttons. `requestLocalMedia` was a plain `getUserMedia` call off the headset, so the
  three non-headset callers now call `getUserMedia` directly.
- `client-web/agent.html`: "Sink guide" headset button, headset panel, step card, composer, Vision Pro help line.
- `client-web/agent.css`: every `.headset` / `body.headset` / `.headset-only` / `.headset-panel` rule.
- `client-web/turn.test.mjs`: the two headset cases and the headset loop variable.
- `docs/headset-demo.md`, `docs/results/headset-web.md` and its pngs.
- Headset text in `docs/features.md` (Vision Pro column), `RESULT.md` (headset report section), `scripts/ready.py`
  (Vision Pro simulator build row), `scripts/browser_smoke.py` (headset leak checks), `scripts/export_public.py`.

## Kept, and why

- `server/pairing.py`, `paired_call` in `server/ws2.py`, the phone pair-camera page (`client-web/pair.js`): the
  external camera hook. `docs/device.md` now has an "External camera devices" section pointing at it.
- The host-side pairing block in Settings (`#pair-request`, QR). It was only visible on a headset, so it is now
  wrapped in `<div class="pair-host hidden">`: same desktop and phone UI as before, code ready to unhide.
- `.typed` CSS rules (lines ~690 to 725) are now unused (only the composer used them). Left in place; safe to delete.
- `router/data/train.jsonl`: the 3 "headset" rows are bicycle headsets (`bike_repair`), not Vision Pro. Unchanged.

## Intentional `git grep -i "headset|visionos|vision pro"` leftovers

- `docs/device.md:123`: "a headset" means headphones for barge-in audio.
- `router/data/train.jsonl` 774, 1867, 2420: bicycle headset.
- `docs/api.md:751`, `docs/results/gemini-vision.md:54`: "vision pro" inside "vision processing" / "vision processes".
- Dated history left as written: `docs/build-credits.md`, `docs/results/pair-vision.md`, `ready.md`, `rewind.md`,
  `scrub.md`, `docs/ui-polish/art-direction.md`.

## Also fixed

`check_public.py` failed on main (20 hits: absolute home paths to the venv in `RESULT.md` and
`docs/results/live-tools-async.md`). Those paths are now `.venv/bin/python`.

## Tests

- `.venv/bin/python -m pytest -q server`: 803 passed, 2 warnings.
- `node --test client-web/*.test.mjs` (Makefile `test-web`): tests 164, pass 164, fail 0.
- `.venv/bin/python scripts/check_public.py`: PASS (0 hits).
- `scripts/browser_smoke.py` against a mock server on a spare port: FAIL only on repeated `401 /api/trigger/client`;
  main at `38a18ae` fails the same way (14 identical 401s, no other problems), so it is pre-existing and not
  caused by this change.
- `swift build` in `ios/AEyeCore` after the platform line removal: Build complete. The iOS app (`ios/AEye`) Xcode build was not run.
