# Demo rehearsal: Where are my keys?

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

## Local memory path (`--memory`, 2026-10-24 about 01:55 PDT)

Both consents on in a temporary memory folder, items keys -> blue bowl, Rewind on. One run: FAIL. The question
was heard (0.63 s to first text, 1.01 s to first audio) and went through the ws2 regex memory path ("Let me think
back."), but find_item did not find the keys, so it fell back to Rewind, whose hit pointed at 1.3 s (not sure, no
box). Vision got 11 scene calls but the server logged no scene_scan events in this mode, so memory's scan path is
separate from the keyframe loop the Rewind fix uses. "Forget that" went to memory ("Forgotten. I no longer remember
your keys.") rather than deleting Rewind clips. Needs the local-memory builder; the plain Rewind path above passes.
