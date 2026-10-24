# Demo rehearsal: Where are my keys?

Latest single run below; the five-run pass rate and the memory-path run follow.

Run 2026-10-24 01:40 PDT, cloud talker, ROUTER=on, Rewind on, TwelveLabs stand-in (nothing uploaded), real vision host for the frame check, headless Chromium with a synthetic camera clip and a `say` microphone. Times are seconds since the page opened; the camera clip started at 2.6 s and the keys go down 10 s into it.

| Check | Result |
|---|---|
| heard the question (server STT) | PASS |
| router labelled it past | PASS |
| find card arrived (rewind_hit or find_item) | PASS |
| card type | rewind_hit |
| search_past sure | PASS |
| hit time within 4 s of the keys going down | PASS |
| box on the hit frame | PASS |
| first audio after the question | PASS |
| forget: clip count 0 | PASS |
| forget: TwelveLabs delete called | PASS |
| no page errors | PASS |

| Moment | t (s) | after the question (s) |
|---|---|---|
| question heard (turn received) | 27.64 | 0.00 |
| first spoken text | 27.80 | 0.15 |
| first audio | 28.26 | 0.61 |
| rewind_hit card | 29.64 | 1.99 |
| forget done (clips 0) | 45.87 | 18.23 |

Whisper heard: Where are my keys?.
Router labels seen: ['past', 'now']. Draw and box messages after the question: 1 (1 ops or boxes). TwelveLabs deletes: 2.
Hit: {"type": "rewind_hit", "t_s": 10.4, "sure": true, "found": null, "place": null, "home": null, "alternatives": [1.4], "query": "Where are my keys?"}.
First spoken lines: ['Let me check the recording.', "That was about 10 seconds in. Here's the clip.", 'Done. I deleted 2 clips of this call.'].

Timeline:

- 2.02 s: Rewind on
- 2.05 s: camera on (synthetic clip starts at 0 s)
- 2.56 s: mic on (fake mic: question at about 24 s)
- 7.60 s: screenshot 1-cups.png
- 16.65 s: screenshot 2-keys-down.png
- 31.40 s: screenshot 3-rewind-hit.png
- 47.20 s: screenshot 4-forgotten.png
- 47.23 s: page sent: {'hello': 1, 'rewind': 1, 'camera': 1, 'frame': 44, 'audio_in': 14}

## Five runs after the fix (2026-10-24 about 01:15 to 01:25 PDT)

Keys go down 10 s into the camera clip (inside the first clip, the case that failed before). Times are seconds
after the server received the question.

| Run | All checks | Hit at (s into the call) | Sure, with box | First audio | rewind_hit card |
|---|---|---|---|---|---|
| 1 | PASS | 10.5 | yes | 0.48 | 1.76 |
| 2 | PASS | 10.4 | yes | 0.48 | 1.12 |
| 3 | FAIL | none | no | none | none |
| 4 | PASS | 10.4 | yes | 0.64 | 1.92 |
| 5 | PASS | 10.5 | yes | 0.39 | 1.05 |

Pass rate 4 of 5. Run 3 failed before the question: the page reconnected (a second hello), camera frames
stalled at 19 and no audio was sent, so nothing was heard; the find itself never ran. Cause not yet known
(no server log kept for that run); rerun with --keep to capture it.

What was wrong and what changed (before the fix every run was a best guess with no box):

- The keys moment never became a clip. Rewind opened clips only on the scene gate's "change" (a whole-frame
  mean difference tuned for scene cuts); a hand putting keys down changes only part of the view. Rewind now also
  watches local activity (keyframes.local_change: at least 12 of 32x32 cells change by more than 40), and a new
  event after 2.5 s of quiet starts its own clip instead of extending the open one.
- The frame check looked at one frame, often with the hand over the object. It now tries the moment of the
  change, the middle of the clip and the settled last frame, and uses the first where our vision finds it.
- Still open: the card's "Now" panel said "Not in view now" while the keys were visible (separate live check).
- Stage note: the first tap already turns the mic on; pressing Mic after that turns it off.

## Local memory path (`--memory`, 2026-10-24 about 01:55 PDT)

Both consents on in a temporary memory folder, items keys -> blue bowl, Rewind on. One run: FAIL. The question
was heard (0.63 s to first text, 1.01 s to first audio) and went through the ws2 regex memory path ("Let me think
back."), but find_item did not find the keys, so it fell back to Rewind, whose hit pointed at 1.3 s (not sure, no
box). Vision got 11 scene calls but the server logged no scene_scan events in this mode, so memory's scan path is
separate from the keyframe loop the Rewind fix uses. "Forget that" went to memory ("Forgotten. I no longer remember
your keys.") rather than deleting Rewind clips. Needs the local-memory builder; the plain Rewind path above passes.

## Router first, and ten more runs (2026-10-24 about 02:10 to 02:40 PDT)

With ROUTER=on, ws2 now asks the router first and logs its label; past questions go to memory (find_item) and
Rewind, spoken forget goes to memory when it is attached and otherwise to the Rewind clip delete; the regex
route is only the fallback when the router is off or unsure.

| Path | Runs | All checks | Sure with a box | Found at (keys at 10 s) | First audio | Card |
|---|---|---|---|---|---|---|
| Rewind (plain) | 5 | 5 of 5 | 5 of 5 | 10.5 to 10.6 s | 0.34 to 0.52 s | 1.02 to 1.70 s |
| Local memory (`--memory`) | 5 | 4 of 5 | 5 of 5 | 12.3 to 14.3 s | 0.48 to 2.26 s | 1.23 to 3.28 s |

The one memory miss was timing only: found at 14.3 s, past the 4 s window (memory stamps when the keys settled).
A first memory batch failed because the Mac lost its network (no route to PyPI or the box); not counted.

Connection-drop investigation (the earlier run 3): the harness now logs every mic and camera open, socket
open and close, a main-thread lag probe and CDN loads, and records a frozen page instead of crashing. In 25
runs since: no reconnect, one mic open per run, no CDN loads (server speech does not use the browser VAD), and
four page stalls of about 1 s (main thread blocked 968 to 1231 ms, 37 to 54 s into a run, after the find card).
Not reproduced: the full freeze (frames stopped, a second hello, a 30 s screenshot timeout) seen twice earlier
while the Mac was heavily loaded. Likely headless Chromium starved under load; the page's ~1 s stalls are worth
a look by the UI lead (they happen after the card renders).
