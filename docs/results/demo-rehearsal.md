# Demo rehearsal: Where are my keys?

Run 2026-10-24 01:19 PDT, cloud talker, ROUTER=on, Rewind on, TwelveLabs stand-in (nothing uploaded), real vision host for the frame check, headless Chromium with a synthetic camera clip and a `say` microphone. Times are seconds since the page opened; the camera clip started at 2.4 s and the keys go down 10 s into it.

| Check | Result |
|---|---|
| heard the question (server STT) | PASS |
| router labelled it past | PASS |
| rewind_hit arrived | PASS |
| search_past sure | PASS |
| hit time within 4 s of the keys going down | PASS |
| box on the hit frame | PASS |
| first audio after the question | PASS |
| forget: clip count 0 | PASS |
| forget: TwelveLabs delete called | PASS |
| no page errors | PASS |

| Moment | t (s) | after the question (s) |
|---|---|---|
| question heard (turn received) | 27.45 | 0.00 |
| first spoken text | 27.65 | 0.20 |
| first audio | 27.83 | 0.39 |
| rewind_hit card | 28.50 | 1.05 |
| forget done (clips 0) | 45.85 | 18.40 |

Whisper heard: Where are my keys?.
Router labels seen: ['past', 'now']. Draw and box messages after the question: 1 (1 ops or boxes). TwelveLabs deletes: 2.
Hit: {"t_s": 10.5, "sure": true, "alternatives": [1.5], "query": "Where are my keys?"}.
First spoken lines: ['Let me check the recording.', "That was about 10 seconds in. Here's the clip.", 'Done. I deleted 2 clips of this call.'].

Timeline:

- 1.85 s: Rewind on
- 1.88 s: camera on (synthetic clip starts at 0 s)
- 2.38 s: mic on (fake mic: question at about 24 s)
- 7.42 s: screenshot 1-cups.png
- 16.45 s: screenshot 2-keys-down.png
- 30.16 s: screenshot 3-rewind-hit.png
- 47.22 s: screenshot 4-forgotten.png
- 47.26 s: page sent: {'hello': 1, 'rewind': 1, 'camera': 1, 'frame': 45, 'audio_in': 14}

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
