# Recent memory for an electronics guide

Implemented on the classic `/ws2` turn path; changes are uncommitted. The 20-question synthetic fixture selected the right source **20/20 (100%)**, with 20/20 answer-content checks. A real loopback WebSocket returned a recent answer in **3.78 ms**. No real camera or fresh TwelveLabs call was used.

## Behavior

- Each session owns a bounded, RAM-only deque covering the last 120 seconds. A scene entry contains the observation's monotonic timestamp, call-relative seconds, caption, object/tool/part labels, and current numbered guide step. No frame, crop, audio, embedding or file is added by this log.
- The existing vision scan supplies the text. No additional vision or language-model request is needed for recent recall. Repeated sightings retain their own timestamps so an earlier location remains retrievable.
- `Step N:` guide speech establishes the current step and is separately recorded as an instruction. Recall says “the guide said,” not that the user completed it. A step is unknown until a numbered instruction is available; no completion is inferred.
- Entries expire while the call runs, including when the camera is off; queries also prune immediately. Disconnect and replacement hello clear the log and the existing scene-history deque. Sessions do not share this log.
- Safety refusals and fixed guide flows retain precedence. Explicit time scope runs before the optional trained intent router, avoiding its cold start and any model call for recent recall.

| Question scope | First source | Availability behavior |
|---|---|---|
| Just now, a minute ago, up to 120 seconds ago, “what was step 3?” | Recent RAM log | Honest no-evidence answer if missing; never substitutes yesterday |
| Earlier in this call | Rewind when enabled; recent otherwise | Rewind miss/unavailable falls through to local cross-day memory, explicitly labelled as an earlier call |
| More than 120 seconds ago | Rewind | Same explicitly labelled cross-day fallback |
| Yesterday / last time / last call | Local cross-day memory | Yesterday filters to that local calendar day; last-call queries exclude this call's records; unavailable is stated |

Rewind queries from this route require the switch on, cloud allowed, and Private mode off. Only ready clips ending at least 20 seconds ago are submitted in the current-call video filter; returned moments are checked again against the cutoff. Existing local vision confirmation still decides whether a Rewind hit is sure. Uncertain hits do not become asserted answers. Long-term recall requires the existing remembering/consent settings and preserves its result card and crop safeguards.

The existing unqualified model-tool and recap paths remain in place. This package adds deterministic temporal source selection, not a retrained classifier. Gemini Live now uses the same answer function through `recent_memory(question)`; see the Live integration note below.

## Measurement

Run from the worktree:

```sh
$HOME/Projects/a-eye/.venv/bin/python -m scripts.recent_memory_bench
```

The complete 20 questions, expected sources, returned sources, content checks and timings are in [recent-memory-bench.json](recent-memory-bench.json). Fixtures describe a multimeter, resistor, breadboard, red wire and soldering iron. Cross-day data is written only to a temporary directory and removed afterward.

| Source | Questions | Median / maximum latency |
|---|---:|---:|
| Recent RAM lookup | 10 | 0.013 / 0.070 ms |
| Rewind routing + stub adapter | 5 | 0.004 / 0.005 ms |
| Local cross-day file lookup | 5 | 0.483 / 0.938 ms |

**Rewind numbers above are not service latency.** The fixture stubs the Rewind answer boundary. Its age filter is independently exercised against `Rewind.search` with a fake TwelveLabs transport. No upload, indexing, network, live vision confirmation or TTS time is included. Previously measured live Rewind search was about 0.3–1.1 seconds, with indexing 7–15 seconds after upload; see [rewind.md](rewind.md). Those are prior measurements, not results from this run.

Real transport proof: uvicorn serving `server.test_ws2:app` on loopback, `LOCAL_ONLY=1`, scratch memory directory, synthetic vision response, browser TTS selected. A synthetic frame was sent over a real WebSocket; the subsequent question returned:

```json
{"result":"PASS","first_answer_ms":3.78,"answer":"At 0:00 in this call, the scene note was: A pan and a screw.","boundary":"real loopback WebSocket; synthetic vision; browser TTS not measured"}
```

The temporary server was stopped. This proves question-to-text delivery, not microphone/STT latency, audible speech start, physical EE recognition, or all possible phrasing. The small scripted set is an acceptance fixture, not an independent accuracy benchmark.

## Checks and limits

Regression coverage: expiry, call isolation/cleanup, no image retention, timestamp-specific location, numbered step vs completed action, no cloud for recent/off/Private, ready-clip age filtering, yesterday vs current-call records, disabled memory, cross-day fallback provenance, WebSocket delivery without the brain, and long-term result cards surviving voice failures.

The initial regression failed because `server.recent_memory` did not exist. Targeted checks now pass. The full suite initially encountered sandbox loopback restrictions and exposed a missing long-term result card; that card was restored. The full suite was rerun with loopback access. No `.env` was read and no contracts or dependencies were changed.

Recent matching is conservative lexical matching over already-produced notes, not semantic event reconstruction. A numeric age uses a ±20-second observation tolerance. Unseen actions, synonyms without matching words, unnumbered steps, and unsupported dates can abstain. A camera scene is evidence of what the vision model described, not proof of successful assembly. The recent route adds no crops; existing cross-day crops remain under their existing policy.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_recent_memory.py server/test_keyframes.py server/test_rewind.py server/test_memory.py server/test_ws2.py server/test_proof_wall.py` - PASS (77 passed in 5.69s).

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q` - FAIL (1 failed, 1033 passed, 2 warnings in 93.39s; loopback access enabled).

The remaining failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: `vision/fixtures/gemini_payment_required.json` is absent. `git ls-tree -r HEAD vision/fixtures` is empty. The missing recorded-response fixture is outside this package; no response was fabricated and no vision files were changed. The warnings concern short synthetic JWT test keys.

Test: `node --test client-web/` - PASS (153 tests, 153 pass, 0 fail, 0 skipped; 1274.043417 ms).

Test: `$HOME/Projects/a-eye/.venv/bin/python -m scripts.recent_memory_bench` - PASS (20/20 right source; 20/20 content checks; fixture timings only).

Test: synthetic real loopback `/ws2` probe - PASS (first answer 3.78 ms).

Test: `git diff --check` - PASS.

## Gemini Live integration — 2026-10-24

Live declares `recent_memory(question)` in the supported Gemini schema subset and validates required strings, lengths and extra keys in code. It calls the same `answer()` function as classic recall, preserving recent/Rewind/long-term routing, consent checks, abstention, and earlier-call provenance. Local long-term result cards remain on the client connection; only the bounded `say` text is returned to Google.

Completed, safety-checked Live input/output transcripts enter the existing 120-second log as user/helper entries. Numbered helper instructions establish a step; “what step was I just on?” retrieves the last numbered instruction without asserting completion. Transcript entries are not scene evidence. The existing scene loop runs during Live calls and supplies scene notes; no extra vision request is added. Live marks this log RAM-only, preventing memory-settings refreshes from binding it to persistent storage. Classic storage settings are unchanged. Existing call teardown and expiry apply.

The synthetic fake Live server sends a split numbered instruction, receives a recent-memory tool call, and speaks the returned recent-log answer. This uses real loopback WebSockets and the real scene loop with synthetic vision. It is not a real Google tool-selection or physical-device playback test. Test summaries are in the current `RESULT.md` entry.
