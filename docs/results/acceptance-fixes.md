# Acceptance fixes — 2026-10-25

Implemented on `pkg/accept-fix`, based on `3af1262`. Offline tests pass for the changed behavior;
**live latency and local recognition of the synthetic mug remain unverified**. No network probe,
model change, `.env` read, push, or edit to the other builder's protected files was made.

Evidence: the supplied `acceptance-20261025T091304-650886Z.json` in the main checkout,
the source in this worktree, and executed tests. No separate server-log excerpt was attached.
The acceptance report does not retain scene captions or Ollama prompt/evaluation timings.

| Flow | Finding | Change | Remaining proof |
| --- | --- | --- | --- |
| private | Product latency defect: a locally available description went through another large CPU model; first-token timeout did not bound first spoken text. | Reuse a recent local caption for closed current-view questions; bound other private model streams until their first spoken text. | Home-PC caption quality, STT and local TTS latency; rerun under 4 s. |
| memory | Reproducible product lookup defect even when the local caption says mug. Actual historical caption is absent from the report. | Remove opening-time language from object matching and select the opening observation; verify it reaches Live's evidence prompt. | Confirm the synthetic A caption really names mug/cup. |
| ask | Product gate holds an ordinary present-view question and can discard/restart its Live response. | Let closed current-view forms keep the original Live generation. | Rerun the unchanged 2 s audio target. |

## Private: actual path and latency

`ws2` constructs `LLMClient`, not `brain_local.LocalBrain`. Private privacy guards disable cloud
providers. `server/llm.py` posts to `${OLLAMA_URL}/api/chat`; the fallback URL when unset is
`http://127.0.0.1:11434/api/chat`. The running home-PC address and overrides were **not inspected**.
The relevant model setting is `LOCAL_LLM_MODEL`, default `qwen3.6:35b-a3b-q4_K_M`, not
`BRAIN_TALKER_MODEL`. Default options are `num_ctx=4096`, `BRAIN_NUM_GPU=0`,
`BRAIN_NUM_THREAD=8`, `think=false`, `stream=true`, and `LOCAL_KEEP_ALIVE=2h`.

Streaming was already enabled. Startup `warm_brain()` submits a one-token "Hi" with the same
options in a background task; it neither guarantees warm completion before a call nor warms the
full turn prompt. General turns include pack, expert and pointer instructions, scene and history.
`LOCAL_FIRST_TOKEN_S=15` stops guarding latency after any content token, including JSON metadata.
The HTTP client has a 20 s timeout, not a four-second end-to-end speech deadline. A slow prefill,
JSON header or unfinished speech clause can therefore leave the user without an answer.

In the report, the private scene finished at call time 0.765 s (VLM 738 ms), well before speech.
Speech ended at 7.042 s; transcribing/thinking started promptly. At 18.859 s, only drawing-clear
and speaking-state events appeared; no `say` or audible reply arrived before the observation ended.
That locates the delay after routing rather than first-scene acquisition. It does not distinguish
model loading, prefill, queue contention and token generation; there are no Ollama timings to do so.
The default CPU model plus unnecessary second generation is the code-supported bottleneck,
not a demonstrated cloud-only dependency or absence of streaming.

For general private/current-view questions, `run_turn()` now answers with an attributed local
camera note when the camera frame is at most 3 s old, the cached scene was completed within 10 s,
and its source is `ollama`. Empty/failed captions do not qualify. Pack refusal/guard checks still
apply. The attribution matters: a recent cached note may precede a changed view. No text-model
call is needed, and the existing private TTS path speaks the answer.

Other private/local-only model streams now have `LOCAL_REPLY_S=3` by default, cancelled only
when actual speech text is emitted, not when a header token arrives. Expiry closes the stream
and says the local brain is taking too long. This is an availability response, **not** a successful
answer. The harness now requires an A-object answer in a `say` event within 4 s and still rejects
cloud brain provenance. It cannot pass on timeout filler. This four-second check measures text;
private audible playback still needs a real voice run.

No new model or environment setting is required for the caption path. `LOCAL_REPLY_S` is the new
optional deadline override; changing `BRAIN_TALKER_MODEL` will not tune this default ws2 path.
I did not switch to the GPU vision model: `docs/results/local-brain.md` records vision contention,
and explicitly says CPU-only 35B talker latency was not measured. Its 1.09 s median first-token
and 2.36 s total talker results used seven GPU layers, not these CPU-only defaults.

**Honest floor:** the harness includes 600 ms of VAD hang, then transport/STT and local TTS time.
Cached-caption handling removes text-model generation; an in-process synthetic STT/vision/voice
call completes within the test's 0.5 s bound, but that is not a home-PC benchmark. Cold or missing
captions and general private reasoning have no verified sub-4-second floor. The new 3 s deadline
starts at model streaming, not before routing/context collection, and does not bound TTS.

## Memory: caption provenance, storage and recall

The synthetic fixture draws A as a blue mug and B as a red apple without text labels.
The report's Live replies name both, but Live sees the pictures separately; its reply is not proof
that the local captioner recognized them. Reported `track` labels are generic `the object`.

`scene_loop()` requests `caption=True`. `vision/ollama.py` uses `VISION_CAPTION_MODEL`, default
`qwen2.5vl:7b-q4_K_M`, for a 15-word JSON caption with an 80-token allowance. The returned
caption and labels are stored in both scene memory and recent memory before `track` is sent.
The report keeps tracks, not those captions. Thus scene scans/storage code are evidenced, but
the historical string "mug" in recent memory is not established from the supplied artifact.

Independently of caption quality, `RecentMemory.find()` treated `show` and `start` as required
object words. Even a stored "A blue mug on the table" failed the exact acceptance question.
With those words removed, the old default selection would also choose the latest scene (apple).
Opening-time language now selects the earliest scene from the first 10 s of the call. If opening
notes expired from the ten-minute buffer, a later retained scene is not relabelled as the start.

Tests store mug at 1 s and apple at 25 s, then prove the lookup and Live evidence prompt contain
the mug, not apple. Another test supplies only a generic caption plus a Live "blue mug" transcript:
the lookup stays generic and does not invent mug evidence. Unseen wrench still has no match.

The image and mug expectation are unchanged because there is no evidence that this captioner
failed to name it. Before claiming the real memory flow fixed, inspect `/scene` output for these
synthetic A/B fixtures on the owner's running vision service. If A stays generic, use an unmistakable
prop fixture through `--frames` with honest `--object-a` aliases; do not inject "mug" into memory
from the question or Live transcript. Keep real camera captions out of logs.

## Ask: first-turn cost

The report measures first nonempty audio at 2.8876 s after speech ended. Session-ready was at
0.738 s and the first scene completed at 4.904 s (VLM 4.138 s); user speech began at 6.001 s and
ended at 7.043 s. Live setup and the first caption therefore finished before this latency interval.
Background context building does not explain a synchronous wait here.

The input-final event was at 7.646 s, thinking at 7.733 s, an empty output/end around 8.213 s,
then real audio at 9.930 s. With `ROUTER=on`, `MemoryTurn.watch()` held every question of at least
three words, even "what is on the table". After a 300 ms debounce and a now-scope decision, it
called `prompt_turn()`, which waits up to 3 s for provider idle and requests another generation.
That behavior is reproduced in the regression; the report pattern is consistent with it, though
it does not separately instrument router warm-up or each provider generation.

Closed present-view forms and their supported streaming prefixes now bypass that hold. Explicit
past wording still takes precedence, including an appended "earlier in this call". Safety and guide
routing retain precedence. The test verifies original audio is delivered with no scope classifier
or replacement prompt, and verifies the appended-past case still takes the memory path.

The 2 s target remains unchanged. The known harness floor includes its 600 ms VAD hang plus
transport/provider time. Live's initial audio guard buffers 250 ms of **audio content**, which can
arrive faster than playback; it is not necessarily 250 ms of wall time. Offline tests cannot supply
a new measured latency floor, so increasing the limit to hide 2.8876 s would be unjustified.

## Verification and owner handoff

Required command, executed in this worktree with the owner's venv:

```
~/Projects/a-eye/.venv/bin/python -m pytest -q server router scripts
17 failed, 1007 passed, 2 warnings in 51.02s
```

All 12 added regression cases passed in that run, including the in-process `/ws2` private audio
turn (synthetic adapters; no sockets). Initial focused runs reproduced the memory, duplicate
generation, slow private and permissive-harness failures before the changes.

The full gate is **FAIL**, not green: 15 failures directly hit denied loopback binds, one hazard
test has a secondary `KeyError` after Live startup reports `PermissionError`, and one unchanged
`scripts/test_ready.py` assertion expects an Xcode subprocess that `scripts/ready.py` no longer
executes. A failed-test-only diagnostic reproduced the same 17 failures. The two warnings concern
pre-existing synthetic JWT keys. Full output is retained locally at
`/private/tmp/a-eye-accept-fix-suite.txt`; the committed test summary is adjacent to this report.
`git diff --check` passed. No real-model, browser, microphone or network rerun was performed.

For the owner: run the unchanged live acceptance procedure after integration, keep the 2 s ask
and 4 s private answer targets, and inspect synthetic caption evidence if memory still fails.
Do not treat this offline result as deployment or physical-device acceptance.
