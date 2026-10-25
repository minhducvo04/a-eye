# General answer pointer

Implemented in the uncommitted `pkg/pointer` working tree, based on `b3ad980`. Ready for code review; live pointer coverage is limited by local inference latency. No merge, deployment or physical-device verification is claimed.

## Behavior and design

The General talker appends at most one `[POINT: blue mug on the left]` tag, copying a phrase from its spoken answer. A bounded incremental filter removes the tag **before** sentence splitting, captions, history and TTS. Split, malformed, oversized and incomplete tags stay silent. Missing, multiple or unspoken targets produce no pointer. Plain replies without the optional JSON header continue streaming.

This costs no extra language-model request, unlike extracting a target in another call after the answer. Naming the target in the answer's own stream also avoids a second model choosing a different referent. The code validates the tag and requires its phrase in the actual guarded speech; model compliance remains imperfect, and omission is safe. General no longer launches the parallel drawing planner or accepts cached JSON draw targets. Other packs retain their existing drawing paths; the explicit Expert path is unchanged.

After speech is queued, the server snapshots the latest frame and sends one named query to the existing local `/scene` grounding route. The deadline is the smaller of **1.5 seconds** and that frame's remaining freshness window. Speech does not wait for grounding. A same-frame, Ollama-sourced caption may be reused; otherwise independent caption generation shares the deadline. The caption must affirm the target noun and contain no absence, blur or glare indication. Colour and side qualifiers remain in the full grounding query.

Only one exact-label result from `source=ollama`, confidence at least **0.7**, finite valid bounds and a still-fresh frame may draw. Fake fallback, cloud source, low confidence, invalid geometry, cancellation, camera-off or deadline expiry all abstain. The result uses existing `clear`, `box` and `arrow` ops, `role=target`, a **2500 ms TTL**, an anchor bbox and the captured frame sequence. No schema, TypeScript, Swift or renderer change was needed. Both clients already consume these ops; their suites passed, but a physical iPhone and live browser overlay were not exercised here.

Private uses the existing local talker routing; there is no cloud target-extraction call. Grounding uses only the configured local vision client. The Private test selects the real local `LLMClient` path even with the default provider set to Claude, and makes any Claude access raise. A live Private turn also produced a valid silent tag. No raw camera frames, audio, secrets or real clips were read or saved.

`docs/results/zoom.md` was absent from the local `main` ref at the final check. This implementation has no small-part zoom dependency.

## Measurement

The local vision service was reachable and reported `fake=false`; its home Ollama host was reachable too. Ten deterministic 1280×960 synthetic mug scenes were generated in memory. The talker was scripted to isolate grounding cost; the actual local vision service performed captioning and grounding. A hit means IoU at least 0.5 against the fixture box; abstentions count as misses. Rows are retained in [pointer-benchmark.json](pointer-benchmark.json).

| Run | Hits / frames | Wrong pointers | Abstentions | Median added ms | Max added ms |
|---|---:|---:|---:|---:|---:|
| Same-frame caption cached | 3 / 10 | 0 | 7 | 1498.85 | 1501.3 |
| Caption also inside deadline | 0 / 10 | 0 | 10 | 1500.75 | 1501.7 |

The three successful cached boxes had IoUs **0.9802, 0.9811 and 0.9829**, with added times **1157.5, 1119.1 and 1135.7 ms**. Added time is first `say` emission to turn completion with immediate scripted speech. First speech took 2.6–3.8 ms in the cached run. Millisecond-scale timeout cleanup appears in total elapsed time; expired results never draw. Cached caption preparation is excluded and frame freshness starts after preparation: this is a favorable cached case, not a continuous-camera latency claim.

Two additional actual local-talker turns ran in Private on a synthetic live feed. One emitted `The blue mug is visible on the left side of the image. [POINT: blue mug]`; speech contained only the sentence, and grounding abstained after 1476 ms because the frame's freshness budget expired. Total turn: 5145 ms. The second talker was unavailable after 15009 ms, emitted no tag and drew nothing; its scene had fallen back to fake vision. These checks preceded the final plain-reply streaming fix. They establish live tag stripping, not successful end-to-end pointing. No physical camera input was used, consistent with AGENTS.md's synthetic/prop-frame rule.

Reproduce the grounding benchmark with the repository Python environment:

```sh
python -m server.probe_pointer --url http://127.0.0.1:8001
python -m server.probe_pointer --url http://127.0.0.1:8001 --uncached
```

## Verification

Tests were written first. The initial acceptance run had 6 failures and 11 passes, including a reproduced oversized-tag speech leak. The later plain-reply streaming regression also failed with a timeout before its fix. The final targeted run passed **95 tests** across pointer, stream, agent, latency and text-only evaluation tests. Coverage includes arbitrary stream chunks, no spoken metadata, confidence/source/absence refusal, bounded latency, immediate speech, cancellation, stale frames, camera-off, no second planner and Private routing.

Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q` - PASS (`980 passed, 2 warnings in 174.49s (0:02:54)`). The two warnings concern existing short test-only HMAC keys in identity tests.

Test: `node --test client-web/` - PASS (`tests 151`, `pass 151`, `fail 0`, duration 1231.867291 ms).

Test: `swift test --package-path ios/AEyeCore` - PASS (`Executed 59 tests, with 0 failures (0 unexpected) in 0.007 (0.011) seconds`).

Swift and socket-bearing Python tests required execution outside the sandbox. One preceding full Python run hit the existing `test_sixty_second_scene_loop` one-second wait timeout; its isolated rerun passed in 4.09 seconds. No keyframe code or assertions were changed.

## Files and review limits

- `server/pointer.py`: prompt, streaming tag filter, fail-closed local grounding and draw construction.
- `server/agent.py`: General integration, suppression of old General drawing paths and plain-reply streaming.
- `server/test_pointer.py`: pointer acceptance tests; `server/probe_pointer.py`: reproducible real-service fixture benchmark.
- `server/test_agent.py`, `server/test_stream.py`, `server/test_latency.py`, `voice/test_duo.py`: existing shape/planner checks now explicitly use non-General packs, preserving their original assertions. `server/test_backbone.py`: fake vision in General must not point.
- `eval/brain_turns.py`, `eval/test_brain_turns.py`: the text-only target-selection harness uses an explicit fixture grounding oracle and accounts for named pointers. It does not measure visual accuracy; fixture timestamps refresh after generation to model a held view.
- `docs/features.md`, this report, benchmark JSON and root `RESULT.md`: status and evidence.

The live hit rate is too low to promise dependable pointing yet. The backend's 0.7 confidence is heuristic, not calibrated; independent noun presence reduces absent-object hallucinations but does not prove the selected colour or side. Small parts, motion, real-camera quality and physical-client behavior remain unverified. A client timeout bounds visible waiting but may leave an already-running remote GPU inference finishing in the background. No new dependencies were added.
