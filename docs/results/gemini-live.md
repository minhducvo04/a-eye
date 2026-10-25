# Gemini Live — lead reviewer handoff

The camera-input fix is uncommitted. Three real Google Live probes now identify the synthetic blue image and return audio; see current verification below. Physical-device playback remains unverified. Earlier implementation results are retained as historical evidence.

## Selection and configuration

Enable **Gemini Live (Google)** in Settings, leave Private mode off, then pick **Gemini Live** in the mode ring. Selecting it without consent opens Settings without connecting. Camera remains under the existing camera control. Live forces server mic/audio transport for that call and restores the previous audio preferences when it ends.

- `GEMINI_API_KEY`: server environment, loaded by Make for the probe. No key or `.env` contents were printed; no credential file was changed.
- `GEMINI_LIVE_MODEL`: optional override, with or without the `models/` prefix. It must appear in the runtime catalogue with `bidiGenerateContent`; an invalid override fails closed into the normal pipeline.
- `LOCAL_ONLY=1`, `hello.private=true`, or Google off prevents discovery and Live connections. Consent is checked again before every outbound message.
- `VISION_BACKEND` remains the existing grounding choice: Qwen/local or configured Gemini/cloud fallback. No new dependency or contract-schema changes.

The official [Gemini WebSocket quickstart](https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket), checked during this task on 2026-10-24, names `gemini-3.8-live`. This is only a preference: the bridge first calls `GET https://generativelanguage.googleapis.com/v1beta/models`, follows pagination, and filters `supportedGenerationMethods` for `bidiGenerateContent`. An available documented model wins; otherwise a conversational model ID returned by that API is selected. IDs are never synthesized. See also [Models API](https://ai.google.dev/api/models) and [Live wire protocol](https://ai.google.dev/api/live).

## Wire and behavior

To preserve the frozen v2 schema, mode and explicit Google consent are connection query parameters:

```text
/ws2?mode=gemini-live&google=1
hello: pack="general", tts="server", stt="server"
```

Append the query fields alongside existing access/owner parameters. `hello.pack="gemini-live"` is not valid and is not sent. The default `/ws2` does not construct a Live bridge.

One Live socket is opened per selected call, using setup/audio transcription/function declarations from the official protocol. Existing `audio_in` carries mono 16 kHz little-endian PCM. Fresh camera frames are resized to at most 320 pixels on either side, JPEG encoded in memory, and sent at most once per second. Camera off and frames older than 1.5 seconds send nothing. Existing paired-phone ingress uses the same session frame and audio path.

Input transcripts use existing `turn` caption messages. Output uses `say` plus existing `audio` messages, resampling Google's 24 kHz PCM to the contract's 16 kHz. It bypasses TTS synthesis for Live replies. Client playback owns completion; the bridge does not send a premature listening event that would cancel paired-phone audio.

On a connection drop, the old socket is closed and one reconnect is attempted. A second drop or failed reconnect disables Live and speaks: “Gemini Live is unavailable. I am switching to the normal pipeline.” Subsequent input follows the normal pipeline. Initial setup/discovery failure uses the same fallback. Reconnect starts a fresh provider conversation; it does not restore provider context or replay the lost utterance.

## Tools, safety, and privacy

- `point_at(label)` uses the configured vision client and the existing pointer grounding checks. It draws a box and arrow only for one matching object, confidence at least 0.7, a fresh frame, and an independent caption consistent with the label. Fake, stale, uncertain, blurred/glared, or absent targets abstain. The original pointer caller still defaults to local-only grounding.
- `find_item(name)`, `tag_item(name, place)`, and `forget_memory(name)` call existing local-memory functions. Local client cards keep their existing path; only the textual `say` result goes back to Google, never a memory crop, embedding, or the memory log.
- `rewind_search(query)` maps to existing `search_past` only while Rewind and its TwelveLabs consent are on. It is omitted from setup while off and rechecked at execution. A Rewind toggle replaces the Live session to refresh its fixed tool declarations; sockets never overlap.
- Every input/output transcript fragment is checked cumulatively through the pack's coded refusal/guard functions. Tool arguments receive the same refusal and PC power checks. A stop clears pending audio, interrupts the provider turn, and speaks the existing fixed line through normal server speech.
- **Latency tradeoff:** provider audio may arrive before its transcript. Live PCM is therefore buffered in memory until the complete reply transcript has passed the code checks. Playback is per completed turn, not immediate provider audio streaming. The buffer is capped at 60 seconds of 24 kHz PCM and cleared on completion, interruption, reconnect, and close. This protects the safety boundary but adds latency; it needs real-device evaluation before calling the experience production ready.
- Transport debug logging is disabled because WebSocket handshake/debug logs can contain the key or media. Errors do not print provider URLs, payloads, or exceptions.
- Existing cloud transport accounting counts discovery and outbound Live messages in Cloud AI calls and Bytes to cloud. These are transport attempts/payload bytes, not billable session counts or network-overhead bytes. Each successful Live camera send increments the new Pictures sent counter. Pictures saved remains separate. No Live raw media is written to disk.
- Settings disclose that microphone audio and downscaled camera video go to Google during Live calls. Private mode and Google revocation close the active bridge. Changing consent starts a new call configuration rather than allowing an old socket to retain consent.

## iOS handoff

Mode ID: **`gemini-live`**. Use the URL/hello fields above, then the existing `audio_in`, `frame`, `say`, `turn`, and `audio` contracts. There is no new playback format.

The current shipping Swift app is not a one-line mode addition: `ios/AEyeCore/Sources/AEyeCore/ClientMessage.swift` sends `tts:"browser"`; `ServerMessage` tests explicitly ignore `audio`; `ios/AEye/App/Call/SpeechOut.swift` speaks captions with a system voice. `ios/Reference/AEyeSocket.swift` has server PCM structures, but that is not proof the shipping app plays them. Native mode selection needs explicit Google/Private consent, server PCM capture/playback, and URL selection wired by the iOS owner. No iOS files were changed. The browser-on-iPhone/paired-phone server transport is reused, but physical iPhone playback was not tested.

## Camera-input correction — 2026-10-24

The reported prior reply was “I don't have eyes, so I can't see anything.” Inspection found no camera instruction in the probe, no frame lead time, and a question sent using `clientContent` immediately after `realtimeInput.video`. The bridge also relied on its background reader to send a frame before a typed question.

The [official wire reference](https://ai.google.dev/api/live) warns that realtime modalities have no cross-stream ordering guarantee and mixing realtime input with client content has no guarantee either. Its `turnCoverage` setting can explicitly retain input outside speech activity. The [capabilities guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities#sending-video) confirms the existing format: `realtimeInput.video` is a Blob with `mimeType: "image/jpeg"` and base64 `data`, up to one frame per second. No switch to deprecated `mediaChunks` is needed.

- Bridge and probe share camera-aware setup: describe supplied live-camera frames, admit missing frames, and do not invent details. Response modality remains `AUDIO`, with output transcription; input transcription stays enabled. `TURN_INCLUDES_ALL_INPUT` explicitly keeps pre-speech video in the turn.
- Typed questions now use `realtimeInput.text`. The bridge first awaits a fresh eligible camera send and gives a newly sent frame 300 ms of lead. A video lock prevents the background loop racing that send; rate/sequence bookkeeping advances only after successful send and resets on reconnect. Existing camera-off, freshness, consent, resizing, and one-frame-per-second limits remain.
- The probe waits for `setupComplete`, sends one in-memory blue 320×240 JPEG, waits one second, then sends exactly “what do you see?”. Neither setup nor question supplies the expected color. Its exit status requires audio and a blue reply, rejecting the reported blindness response.
- These delays are practical lead time, not provider acknowledgements of frame processing. The combined fix passed live; individual changes were not isolated in an ablation experiment.

Run each probe through Make (this worktree has no `.env`; the sibling checkout supplies it):

```sh
make -f $HOME/Projects/a-eye/.env -f Makefile gemini-live-check PY=$HOME/Projects/a-eye/.venv/bin/python
```

All three completed runs used `models/gemini-3.8-live`, exited 0, and printed `blue-image check: PASS`:

| Run | Reply text | First-audio ms |
|---|---|---:|
| 1 | I only see a solid blue screen. | 451 |
| 2 | I only see a solid blue screen. | 477 |
| 3 | I see a solid blue screen. | 467 |

Timing starts immediately before sending the question, excludes the one-second frame pre-roll, and ends at first provider audio arrival. It does not measure safety-buffered browser playback. Before these runs, a worktree-only Make attempt reported not configured, and a sandboxed network attempt failed without exposing the provider exception. Authorized network access enabled the three successful runs. No media was saved.

Regression evidence: `test_camera_precedes_realtime_question` failed before the fix because only a client-content question was sent; it passes after the fix. The loopback test checks setup, video transport, realtime text, audio and consent. Probe reply checks cover blue success, the reported blindness reply, a blue denial and a wrong color.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_gemini_live.py` - PASS (`21 passed in 1.60s`). Loopback sockets required execution outside the restricted sandbox.

Test: `make test PY=$HOME/Projects/a-eye/.venv/bin/python` - FAIL (`1 failed, 1026 passed, 2 warnings in 66.28s`). The sole failure remains `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: missing `vision/fixtures/gemini_payment_required.json`, also absent from HEAD (`git ls-tree HEAD vision/fixtures/gemini_payment_required.json` returned no entry). No vision files were changed. Warnings concern short synthetic JWT keys. Make stopped before its web target, so that target was run separately.

Test: `make test-web` - PASS (`153 passed`, no failures/skips, `1266.711625 ms`).

Test: `git diff --check` - PASS.

Current changed files: `server/gemini_live.py`, `scripts/gemini_live_check.py`, `server/test_gemini_live.py`, `Makefile`, this report, and `RESULT.md`. All remain uncommitted.

## Earlier implementation verification (historical)

Privacy tests were written before the implementation; the first run failed collection because `server.gemini_live` did not yet exist. The final tests include a real loopback WebSocket server exchanging synthetic recorded-shape setup, audio, tool-call, and transcript frames. They cover consent before discovery, runtime catalogue/override validation, one reconnect then fallback, downscaling/rate limiting, metering, split safety transcripts, output checks and safe-turn recovery, actual temporary local-memory tag/find/forget, Rewind consent, grounding abstention, and default ws2 fallback. Browser tests exercise actual `agent.js` mode/consent/hello/caption wiring through the existing DOM/socket fixture.

Python used the existing sibling environment `$HOME/Projects/a-eye/.venv/bin/python`; this worktree has no local virtualenv. Loopback tests required sandbox escalation. No test needed a real credential, camera, microphone, or stored personal media.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q server/test_gemini_live.py server/test_ws2.py server/test_pointer.py server/test_cloud_meter.py server/test_proof_wall.py server/test_access.py` - PASS (`93 passed in 2.67s`).

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q` - FAIL (`1 failed, 1011 passed, 2 warnings in 64.57s (0:01:04)`). The sole failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: `FileNotFoundError` for `vision/fixtures/gemini_payment_required.json`. The fixture is absent from both this checkout and its HEAD tree; neither the vision test nor its fixture was changed. The vision owner must supply the original fixture. No invented replacement or skipped test was used. The two warnings concern short synthetic JWT test keys.

Test: `node --test client-web/` - PASS (`tests 153`, `pass 153`, `fail 0`, `skipped 0`, `duration_ms 1271.238167`).

Test: `git diff --check` - PASS (no output).

Real probe: `$HOME/Projects/a-eye/.venv/bin/python scripts/gemini_live_check.py` - NOT CONFIGURED (`not configured`, exit 2). The script opens a real session when configured, sends a synthetic blue frame and “what do you see?”, and prints model, first-audio ms, and reply text. Its timing is first provider audio arrival, not safety-buffered client playback. No real Google model catalogue/session, first-audio timing, or device playback claim is made here.

## Changed files

- Bridge and integration: `server/gemini_live.py`, `server/ws2.py`, `server/pointer.py`.
- Counters: `server/cloud_meter.py`, `server/proof_wall.py`.
- Web: `client-web/agent.js`, `client-web/agent.html`, `client-web/gemini-live.js`.
- Tests: `server/test_gemini_live.py`, `server/test_access.py`, `server/test_proof_wall.py`, `client-web/gemini-live.test.mjs`, `client-web/turn.test.mjs`, `conftest.py`.
- Probe and handoff: `scripts/gemini_live_check.py`, this report, `RESULT.md`.

Reviewer next steps: review the diff and the completed-turn audio tradeoff; verify browser and physical-phone playback before integration approval. The three current synthetic-camera Live probes supersede the historical not-configured probe. No commit, push, merge, or deployment was performed.
