# client-realtime result

The agent page keeps drawings on the camera between slow server updates, speaks `say` parts in order, and shows a dev latency panel when the URL has `?dev=1`.

Files changed:
- `client-web/realtime.js`: speech queue, tracker seed/drop decisions, HUD fps and round-trip math, dev-panel placement.
- `client-web/realtime.test.mjs`: parts in order, old turns ignored, barge-in clears the queue, server boxes win, unreferenced trackers drop, fake-clock fps and round trip.
- `client-web/agent.js`: animation-frame loop draws the camera to a 320 px gray frame, updates the tracker at 30 Hz, and paints `applyAnchors` through the existing draw layer. Frame upload stays at 1 fps. Photo upload does not track.
- `client-web/agent.css`: small monospace dev panel.

Test: node --test client-web/ - PASS (49 tests, 49 passed, 0 failed, 0 cancelled, 0 skipped, 0 todo)

Limits:
- No real camera, microphone, browser window, or iPhone was tested. The fast loop is wired, but its frame rate on a phone is unmeasured.
- Seeds use the latest camera gray, not the exact frame the server measured. A resolution change reseeds from the last known boxes.
- Later sentences of one turn are queued on `speechSynthesis` because `voice.speak` cancels the current utterance. Echo detection still sees only the sentence `voice.speak` was given.
- Server audio is played in arrival order. A new utterance id still restarts playback inside `voice.playPcm`.
- The dev panel shows overlay paints in the last second, the last tracker update, frame round trip to the next `draw` or `track` with that seq or newer, the last metrics message, and client time from final words sent to the first sound.
