# Demo rehearsal: Where are my keys?

Run 2026-10-24 01:10 PDT, cloud talker, ROUTER=on, Rewind on, TwelveLabs stand-in (nothing uploaded), real vision host for the frame check, headless Chromium with a synthetic camera clip and a `say` microphone. Times are seconds since the page opened; the camera clip started at 2.4 s and the keys go down 22 s into it.

| Check | Result |
|---|---|
| heard the question (server STT) | PASS |
| router labelled it past | PASS |
| rewind_hit arrived | PASS |
| search_past sure | FAIL |
| hit time within 4 s of the keys going down | FAIL |
| box on the hit frame | FAIL |
| first audio after the question | PASS |
| forget: clip count 0 | PASS |
| forget: TwelveLabs delete called | PASS |
| no page errors | PASS |

| Moment | t (s) | after the question (s) |
|---|---|---|
| question heard (turn received) | 39.54 | 0.00 |
| first spoken text | 39.77 | 0.23 |
| first audio | 40.00 | 0.45 |
| rewind_hit card | 41.13 | 1.58 |
| forget done (clips 0) | 57.82 | 18.28 |

Whisper heard: Where are my keys?.
Router labels seen: ['past', 'now']. Draw and box messages after the question: 1 (0 ops or boxes). TwelveLabs deletes: 1.
Hit: {"t_s": 1.5, "sure": false, "alternatives": [], "query": "Where are my keys?"}.
First spoken lines: ['Let me check the recording.', "I'm not sure I saw it. Maybe right at the start of the call. Here's my best guess.", 'Done. I deleted 1 clip of this call.'].

Timeline:

- 1.91 s: Rewind on
- 1.94 s: camera on (synthetic clip starts at 0 s)
- 2.44 s: mic on (fake mic: question at about 36 s)
- 7.48 s: screenshot 1-cups.png
- 28.53 s: screenshot 2-keys-down.png
- 42.88 s: screenshot 3-rewind-hit.png
- 59.35 s: screenshot 4-forgotten.png
- 59.38 s: page sent: {'hello': 1, 'rewind': 1, 'camera': 1, 'frame': 57, 'audio_in': 14}
