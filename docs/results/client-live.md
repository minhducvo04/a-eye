# RESULT: client-live

Safari live camera mode on the static call page. No build step and no npm packages. Messages follow `contracts/schema.json` v1. Contracts were not edited.

## Files changed

- `client-web/live.js` (new)
- `client-web/live.test.mjs` (new)
- `client-web/index.html`
- `client-web/call.js`
- `client-web/overlay.js`
- `client-web/overlay.test.mjs`
- `client-web/style.css`
- `client-web/README.md`
- `RESULT.md`

## What landed

- **Start camera** runs `getUserMedia` on the tap, with the back camera, ideal 1280×720, and `audio: false`. The video element is `playsinline`, `muted`, and `autoplay`. An insecure page (`window.isSecureContext` false) or a blocked camera shows a caption. **Upload photo** still sends one `photo`.
- `live.js` encodes JPEG frames (long side ≤ 640, quality 0.7) at 2 fps. It waits for any server message with `seq` ≥ the outstanding frame, or 1.5 s, and skips when `bufferedAmount` > 0. A hidden tab pauses sending. **Pause** / **Resume** toggles the same gate.
- The video uses `object-fit: cover`. `coverTransform` maps normalized boxes of the sent frame through that crop. The canvas bitmap uses `devicePixelRatio`. An older `seq` is dropped. The overlay clears 3 s after the last one.
- The HUD line shows frames sent in the last second, the last round-trip, and the socket state.
- Frames are not written to `localStorage`, not downloaded, and not logged.

## Limitations

- No real iPhone or browser camera was tested. `node --test` does not open Safari, call `getUserMedia`, or open a WebSocket.
- The page was not clicked through in a browser in this session. Layout at phone width was not measured on a device.
- If `screen.orientation` is missing, a wider window is reported as `landscape_left`. That fallback cannot tell left from right.
- `speak(text)` is still `speechSynthesis` only. Mic audio is not sent. The optional overlay `diagram` image is not drawn.
- A still **photo** is still scaled by width (max 640), not by long side. Live frames use the long side.

Test: node --test client-web/ - PASS (16 pass, 0 fail, 0 skipped)

Commit: not created. `git add` failed with `Unable to create '$HOME/Projects/a-eye/.git/worktrees/client-live/index.lock': Operation not permitted`. The files above are in the worktree and unstaged. Nothing was pushed.
