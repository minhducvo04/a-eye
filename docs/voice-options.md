# Voice options for A-eye (2026-10-23)

**Default now:** the cascade, browser STT with Silero VAD, then a Claude Haiku 5.5 **talker** that speaks
first, with a Claude Sonnet 5.5 **planner** running in parallel for draw ops and follow-up notes. The scene
feed (Qwen2.5-VL on the PC) writes the view about once a second. It needs only the Anthropic key. Off
switches: `BRAIN_MODE=single` restores the old single call, and `?vad=0` restores the word-based barge-in.

**Best alternative measured tonight:** Gemini Live (`gemini-3.8-live`). The `GOOGLE_API_KEY` in `.env`
works and lists the Live models. It is only a server-side probe so far (`voice/gemini_live.py`), not wired
into the page. It would send the user's microphone audio to Google, which `AGENTS.md` does not allow
today ("Cartesia receives only the AI's own sentences"), so it needs Duc's yes first.

**Sign up:** Cartesia with the code `CARTESIACALHACKS` (first-time users). It is the only voice sponsor
prize ("Best Use of Cartesia"), and Ink-2 turn events plus Sonic-3.6 TTS slot straight into the cascade.
The second choice is Deepgram ($200 free credit), whose Voice Agent accepts Anthropic as its brain. There
is no Deepgram track at Cal Hacks.

## Measured on Duc's setup (Mac, PC over Tailscale)

| What | Before | After | How |
|---|---|---|---|
| Brain request to first spoken clause | Sonnet 5.5, draw JSON first: 1366 ms [1157-1696] | Haiku 5.5 talker, speech only: **555 ms** [532-707] | `voice/bench.py`, real API, n=8 each |
| Typed final words to first `say` on `/ws2` | single Sonnet call: 1090 ms median [1045-4543] | duo: **884 ms** median [744-1373] | `voice/bench_ws.py`, n=6 each, fake vision with fixed objects |
| First draw on `/ws2` | 1072 ms (and speech waits for it) | 1349 ms (speech does not wait) | same runs |
| Scene older than 1.5 s when asked (stale context) | 0/6 | 0/6 (real Qwen feed: 0/5, age 29-577 ms) | same runs, age of the last `track` message |
| Barge-in: user speech onset to playback stopped | needs 2 recognized words (not measured; Safari interims usually take 0.5 s or more) | **118-134 ms** (ducks at 54-70 ms) | browser pane, synthetic speech fed to the VAD, 3 runs |
| End of speech to words sent (browser STT) | 700 ms after the last interim (early final) | VAD end + 120 ms of quiet | unit-tested; no Safari timing yet |
| Gemini Live, end of speech to first audio | n/a | 1073 ms median [995-1602] | `voice/gemini_live.py`, n=4, synthetic speech |
| Gemini Live, cut-in to `interrupted` signal | n/a | 253 ms median | same |
| Gemini Live, used the newest scene note / called the draw tool | n/a | 4/4 / 4 calls | same |

Not verified yet: anything on an iPhone. vad-web has open iOS issues (#227 out of memory on iOS 17,
#134), and the page falls back to the word-based barge-in when the VAD fails to load. The boxsvc (Kokoro,
Whisper) on the PC did not answer tonight, so every measurement above used browser speech, and no
server-TTS first-audio number is new. Barge-in with an open speaker relies on the browser's echo
cancellation. The duck step (a misfire restores playback) limits damage, but it is not tested with real
echo.

## Talker + thinker + scene feed (Duc's design)

```
mic -> browser STT + Silero VAD --final words--> /ws2
                                   |-> TALKER  Haiku 5.5, SAY only, ~0.55 s to first clause -> TTS
  camera -> Qwen2.5-VL scene feed (1/s) -> view note ----^         (uses newest view + planner notes)
                                   |-> PLANNER Sonnet 5.5 in parallel -> draw ops now,
                                        note for the talker -> spoken as a follow-up only if it adds a
                                        fact or the talker said a filler ("Let me look.")
VAD hears the user -> duck at once, stop at 120 ms, cancel the turn and the planner on the server
```

Built in `server/agent.py` (`run_turn(..., planner=)`) and `server/ws2.py`. The planner runs outside the
GPU gate, so the two cloud calls overlap. It is on by default when an Anthropic key is set and
`LOCAL_ONLY` is off.

Can a talker take changing context mid-session?

| Talker | Live context mid-session | Tools for draw ops |
|---|---|---|
| Our cascade (Haiku) | Yes: each turn reads the newest view note and planner notes | Yes (the planner) |
| Gemini Live | Yes: `clientContent` with `turnComplete: false` (measured 4/4) | Yes (measured) |
| OpenAI Realtime | Yes per docs: `session.update` and `conversation.item.create` (no key, untested) | Yes |
| PersonaPlex-7B | No per the model card: one persona and voice prompt at session start | No |
| Kyutai Moshi / Unmute | Moshi: no text-injection path documented. Unmute: a cascade with an OpenAI-compatible LLM, so yes through the LLM | Not built in |

## Whole-stack comparison

Scores are out of 10 for tonight's demo. pub = vendor published; der = derived; ours = measured here.

| Stack | Time to first audio | Barge-in | Full duplex | Live scene context | Draw-op tools | iPhone Safari | Cost per min | Keys we have | Prize fit | Build hours | Score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a1) Ours: browser STT + VAD + Haiku talker + Sonnet planner (default) | ~0.9 s from final words (ours) | VAD duck 60 ms, stop 130 ms (ours) | Listens while it talks; turn-based | Yes | Yes | Yes (VAD unverified on iOS) | ~$0.03 der (Claude only) | Yes | Anthropic | done | **8** |
| (a2) Ours with Gemini Live as the talker | 1.07 s from end of speech (ours) | Server `interrupted` at 0.25 s (ours) | Yes | Yes (ours) | Yes (ours) | Yes (WebSocket, ephemeral token) | $0.012-0.014 der | Yes (`GOOGLE_API_KEY`) | MLH Gemini (swag) | 3 to 4 | 7 (needs a privacy yes) |
| (a3) Ours with PersonaPlex-7B on the 3090 Ti | 0.17 s turn-taking (pub) | 0.24 s native yield (pub) | Yes | No (start prompt only) | No | Needs our own audio relay | $0 | Gated HF weights (Duc must accept) | none | 6+ | 3 |
| (b) Cartesia: Ink-2 STT + Sonic-3.6 TTS (+ Line agents) with Claude and our scene feed | Sonic about 90 ms (vendor claim), 166-190 ms measured by others | Ink-2 turn events plus our VAD | Listens while it talks; turn-based | Yes (our loop) | Yes (our loop or Line client tools) | Yes (WebSocket) | ~$0.03 der (Ink + Sonic), Line $0.06 pub, plus Claude | **No** (sign up) | **Cartesia prize** | 2 to 3 | **8** once keyed |
| (c) OpenAI Realtime `gpt-realtime-2.1` (WebRTC) | not published | Built in, `semantic_vad` | Yes | Yes (docs) | Yes | Yes | $0.048 der (mini $0.015) | No | none | 3 | 5 |
| (d) Gemini Live alone (no Claude) | 1.07 s (ours) | 0.25 s (ours) | Yes | Yes | Yes | Yes | $0.012-0.014 der | Yes | MLH Gemini | 3 | 6 (drops Claude) |
| (e) Deepgram Voice Agent (Flux + Aura-2, Anthropic brain) | Flux end of turn ~260 ms (pub) | Flux eager end of turn | Listens while it talks | Yes (inject messages) | Yes (client functions) | Yes | $0.065-0.075 pub | No ($200 credit) | none | 2 to 3 | 7 |
| (f) ElevenLabs Agents (Claude selectable) | not published | Own turn model | Listens while it talks | Custom LLM endpoint | Yes | Yes | $0.08 pub plus LLM | No | none | 3 | 6 |
| (g) Pipecat or LiveKit Agents orchestrating Cartesia + Claude | adds a server hop | Smart Turn v3.2 / turn-detector | Listens while it talks | Yes | Yes | Yes (WebRTC client) | open source plus vendors | No (Cartesia) | Cartesia prize | 5 to 8 | 5 (too much plumbing tonight) |
| Hume EVI | not published | Tone-based | Yes | Partial | not found | Yes | $0.04-0.07 | No | none | n/a | 1 (API shuts down 2026-11-13) |

Cost assumptions: a 50/50 talk split, about 6 turns per minute, and context not re-billed. Claude cascade:
Haiku 5.5 at $0.10/$0.50 and Sonnet 5.5 at $2/$10 per million tokens, about 1.5k input tokens per call.
Gemini: $0.005/min audio in and $0.018/min out (pub). OpenAI: 600 input and 1,200 output tokens per minute
at $32/$64 per million (pub). Cartesia: about 800 credits per audio minute and $0.39/hour for Ink (pub).

## Recommendation for tonight

1. Demo on the default cascade. It runs on the key we have, keeps Claude as the brain and draws in
   parallel. Its first audio is about 0.9 s from the final words. Barge-in stops in about 130 ms when the
   VAD loads.
2. When the Cartesia key appears, swap browser speech for Sonic-3.6 TTS through `voice/cartesia.py`
   (the adapter exists) and Ink-2 for STT, then rerun `voice/bench_ws.py` and the browser barge test.
   That is the prize path, and the talker, planner and scene feed stay as they are.
3. Keep Gemini Live as the full-duplex fallback. Wire it only if Duc says yes to sending mic audio to
   Google.

## Reproduce

```sh
.venv/bin/python -m voice.bench claude-haiku-5-5 claude-sonnet-5-5   # BENCH_ROLE=talker for speech-only
.venv/bin/python -m voice.bench_ws ws://127.0.0.1:8000/ws2 6          # needs A_EYE_TOKEN empty or ?token
.venv/bin/python -m voice.gemini_live gemini-3.8-live 4
```

Sources (read 2026-10-23): npm `@ricky0123/vad-web` 0.0.31 and docs.vad.ricky0123.com; OpenAI realtime
pricing and VAD guides; ai.google.dev Live API, pricing and ephemeral tokens; cartesia.ai pricing and
docs; deepgram.com pricing and Voice Agent docs; elevenlabs.io agents LLM docs; dev.hume.ai; LiveKit
turn detector; Pipecat speech input; huggingface.co/nvidia/personaplex-7b-v1; github.com/kyutai-labs/unmute;
cal-hacks-13-0.devpost.com.

## Which voices sound most human (2026-10-24)

The default is now the server voice (`?tts=browser` or the picker brings back browser speech, which
sounds robotic). Order: Cartesia Sonic when `CARTESIA_API_KEY` and `CARTESIA_VOICE_ID` are set, then
Kokoro on the box, then the browser. The picker sits next to Test voice, which plays a server sample.

Kokoro voices, scored by `voice/voice_pick.py`. Each clip is the AI's own synthetic line, rated 1 to 5
for human-likeness by Gemini under shuffled labels, over 7 passes in two runs. This is a **proxy** for a
blind listen test: nobody has listened yet. First audio is the box `/tts` first chunk from the Mac,
median of 3.

| Voice | Proxy score (run 1, run 2) | First audio |
|---|---|---|
| af_kore (default) | 4.0, 3.6 | 343-346 ms |
| af_sarah | 4.0, 3.6 | 289-402 ms |
| am_puck | 4.0, 3.2 | 313-387 ms |
| af_heart (old default) | 3.5, 3.4 | 335-436 ms |
| bf_emma | 3.0, 3.6 | 371-388 ms |
| am_fenrir | 3.0, 3.8 | 316-373 ms |
| am_michael | 2.5, 3.0 | 418-442 ms |
| af_nicole, af_sky, af_aoede, am_echo, bm_fable | 2.4-2.8 | 312-483 ms |

The talker prompt now writes for the ear: contractions, short sentences, no lists or symbols, and a
filler ("One sec, looking.") only when it truly waits. Typed final words to first Kokoro audio with
af_kore and the new prompt: 1440 ms median [1030-1527], n=4 (`BENCH_TTS=server voice/bench_ws.py`).

## Cartesia is live (2026-10-24)

`CARTESIA_API_KEY` is set, so Cartesia Sonic 3.6 over the TTS WebSocket is the default server voice,
with Kokoro as the fallback (`voice/cartesia_ws.py`). One context per turn carries prosody across the
talker's clauses, and barge-in cancels the context. Picker voices: Katie (friendly, default), Cathy
(coworker), Parker (supportive pal).

| Server STT turn, from the final chunk (6 turns each, synthetic speech) | Transcribed | First say | First audio |
|---|---|---|---|
| Before partial STT, Kokoro af_heart | 838 ms | 1733 ms | 2062 ms |
| Partial STT, Kokoro af_kore | 41 ms | 883 ms | 1117 ms [958-1639] |
| Partial STT, Cartesia Katie | 37 ms | 857 ms | **1008 ms** [853-1158] |

Cartesia clause latency alone: 284 ms cold (TLS handshake, now paid at hello) and 118 ms warm.
