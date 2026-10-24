# Local memory result (memory aid across calls)

The memory aid answers "where are my keys?" in a later call or on a later day. It keeps its data on the server machine. It is off until the caregiver page has both consents and Remembering is switched on (`PUT /api/memory/settings`).

## What is stored

Each person has a folder, `data/private/memory/<p-id>/`. The folder is gitignored, and the id comes from the signed-in identity (an Access email hash, the token, or local), never from the client.

- **`log.jsonl`:** one line per **changed** scene note. A heartbeat whose note and tagged items did not change is not stored. Each line holds:
  - the local Qwen caption, up to 15 words, and the object labels;
  - each tagged object with its box, the nearest object ("left red cup") and a box on its crop;
  - **one** EmbeddingGemma vector, stored as 768 dims int8.
- **`crops/`:** a 224 px JPEG crop per **tagged object** only, never a full frame, video or audio. No crop is written when the frame shows a person (the `person` class from YOLO on our own GPU box, or a person word in the scene), or when that check cannot run (fail closed). Tests: `test_face_skip_never_stores_a_crop_with_a_person` and `test_post_condition_no_stored_crop_came_from_a_person_frame`.
- **`tags.json`, `settings.json`:** caregiver tags ("keys" with home "blue bowl", a place "red cup"), the two consents, rooms (bedroom and bathroom refused with a 422), and kept days (1 to 30, default 7).
- **`videos.json`:** TwelveLabs video ids, only when Rewind cloud was on. While the memory is attached, Rewind uploads go to that person's own index `a-eye-<p-id>`.
- **At rest:** each line, crop and JSON file is encrypted with Fernet when `A_EYE_MEMORY_KEY` is set. Without the key, the data is protected by the file system only (FileVault), and status reports `encrypted: false`.

## Search, all local

1. **Exact tag, then label:** the newest line wins.
2. **Fuzzy:** the question is embedded with EmbeddingGemma on the Mac CPU (`router/embed_local.py`) and ranked by cosine similarity, with a floor of 0.45.
3. **Live arrow:** our vision host grounds the remembered place by side (for example "left red cup") in the current frame, so the arrow lands on the right cup. The item itself counts as in view only when the live caption mentions it, because grounding alone can invent a box for a hidden thing.
4. **The answer names the home** when one is tagged: "Your keys are in the blue bowl, where they live", or "... Their home is the blue bowl."

TwelveLabs is not used unless Rewind cloud is on for that call, and then only as a fallback when memory has nothing.

## Controls

- **Forget that:** the item just discussed (`scope: last`). It deletes that item's notes, crops and tag.
- **Forget today and Forget everything:** these also delete the person's TwelveLabs videos through `DELETE /indexes/{id}/videos/{id}`, which is allowed in Private mode because it only removes data. Ids are logged.
- **Retention:** older notes are purged on attach and hourly while writing.
- **Counts:** `count` is the notes kept today, and `count_item` is the notes left about the item.

## Real run (2026-10-24, `scripts/memory_two_calls.py`, two separate /ws2 calls)

Setup:
- Real vision: `qwen3.5:9b` through `VISION_URL` :8001.
- Real person check: the GPU box running YOLO.
- Real EmbeddingGemma int8 on the Mac CPU.
- Encryption on, with a fresh key for the run. Data went to a scratch folder.
- The frames were synthetic: a table with three red cups and a key ring (`scripts/memory_scene.py`), at 2 fps.

| Step | Result |
|---|---|
| Call 1 | 63 s; keys right, then middle, then left, then hidden. 5 notes and 2 crops kept, 14.6 KB encrypted |
| Storage | about 0.84 MB per hour at this rate (5 changed notes a minute). A real room changes less often, but adds crops |
| `/api/memory/find` "keys" (tag path) | 0.2 to 0.9 ms on the server, 2 to 5 ms over HTTP |
| Fuzzy path ("my passport", embeds the query) | 40 ms on the server, not found (correct) |
| Call 2, new session, keys hidden: "Where are my keys?" | `find_item` card in **751 ms**: crop with the keys boxed, "under the left red cup", home "blue bowl", plus an arrow on the left cup in the live frame (bbox x 0.14) |
| Spoken line | "I last saw your keys under the left red cup, just now. Their home is the blue bowl. I'm pointing at that spot." |
| "Forget that." | `memory_state` in 5 ms: `count_item` 0 and crops 0. The 3 untagged notes stay |

An earlier run, before the live caption gate, pointed at the middle cup as "the keys" because grounding invented a box for the hidden keys. The caption gate fixed this.

Limits:
- The frames were drawn, not filmed, and no person was in them.
- The 751 ms includes one live grounding call. On a busy GPU it is longer.
- "Just now" because call 2 followed call 1 within a minute. Multi-day wording ("yesterday at 3:02 PM") is unit-tested only.
- No caregiver interviews and no real users yet.

Test: .venv/bin/python -m pytest -q server/test_memory.py - PASS (15 passed)
Test: node --test client-web/ - PASS
Test: make browser-smoke URL=http://127.0.0.1:8438 - PASS (the web memory UI calls /api/memory/status for real)
