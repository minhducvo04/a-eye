# Memory rehearsal: Where are my keys? (local memory path)

`scripts/demo_rehearsal.py --memory`, run 5 times on pkg/memory-rehearsal. All memory checks passed in 5 of 5 runs: find_item card, sure, hit time within 4 s of the keys going down (12.0 to 13.5 s against about 12.4 s), box on the hit frame, first audio, forget with clip count 0, and the TwelveLabs stand-in delete. The card came 1.5 to 2.6 s after the question. "Router labelled it past" fails in all 5 runs: the local memory turn is taken in ws2 (rewind_turn) before the router runs. That order is the lead's to change.

The run before these fixes, on main bff64e6, found the keys only at the next heartbeat, with no box and a time 12 s late. It also never cleared the call's clips.

Last of the 5 runs:

# Demo rehearsal: Where are my keys?

Run 2026-10-24 02:01 PDT, cloud talker, ROUTER=on, Rewind on, TwelveLabs stand-in (nothing uploaded), real vision host for the frame check, headless Chromium with a synthetic camera clip and a `say` microphone. Times are seconds since the page opened; the camera clip started at 2.4 s and the keys go down 10 s into it.

| Check | Result |
|---|---|
| heard the question (server STT) | PASS |
| router labelled it past | FAIL |
| find card arrived (rewind_hit or find_item) | PASS |
| card type | find_item |
| search_past sure | PASS |
| hit time within 4 s of the keys going down | PASS |
| box on the hit frame | PASS |
| first audio after the question | PASS |
| forget: clip count 0 | PASS |
| forget: TwelveLabs delete called | PASS |
| no page errors | PASS |

| Moment | t (s) | after the question (s) |
|---|---|---|
| question heard (turn received) | 27.40 | 0.00 |
| first spoken text | 28.32 | 0.92 |
| first audio | 28.61 | 1.21 |
| rewind_hit card | 29.32 | 1.91 |
| forget done (clips 0) | 45.38 | 17.97 |

Whisper heard: Where are my keys?.
Router labels seen: []. Draw and box messages after the question: 1 (2 ops or boxes). TwelveLabs deletes: 2.
Hit: {"type": "find_item", "t_s": 13.2, "sure": true, "found": true, "place": null, "home": "blue bowl", "alternatives": [], "query": null}.
First spoken lines: ['Let me think back.', "I last saw your keys just now. Their home is the blue bowl. I'm pointing at it now.", 'Forgotten. I no longer remember your keys.'].

Timeline:

- 1.84 s: Rewind on
- 1.88 s: camera on (synthetic clip starts at 0 s)
- 2.38 s: mic on (fake mic: question at about 24 s)
- 7.42 s: screenshot 1-cups.png
- 16.46 s: screenshot 2-keys-down.png
- 30.96 s: screenshot 3-rewind-hit.png
- 46.83 s: screenshot 4-forgotten.png
- 46.85 s: page sent: {'hello': 1, 'rewind': 1, 'camera': 1, 'frame': 44, 'audio_in': 14}
