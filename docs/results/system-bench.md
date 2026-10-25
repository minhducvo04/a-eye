# System benchmark: measured limits for judges

Measured on 2026-10-24. These are synthetic microbenchmarks, not a million-user capacity claim.
The running server uses its existing routing (including Opus and local fallbacks); the model notes do not describe every observed turn.

## Provenance and method

- Benchmark checkout: `806ae12c6cb983053332f4e5676b13e3928172cd`; Python 3.14.4; macOS-27.0.1-arm64-arm-64bit-Mach-O.
- Host: Mac17,6, 18 logical CPUs, 36 GiB RAM. Load client and server share this Mac.
- Existing port 8000 process: PID 71644, cwd $HOME/Projects/a-eye; checkout HEAD 806ae12c6cb983053332f4e5676b13e3928172cd at inspection. Running process code identity is not cryptographically verified.
- Raw timings, failures, token counts and resource samples: [system-bench.json](system-bench.json). No frames, audio, credentials or generated reply bodies are retained.
- p50 = median; p95 = nearest rank ceil(0.95*n). With ten samples p95 is the maximum; tails are noisy. Failed trials are excluded from completion quantiles and counted explicitly; observed Gemini first audio is retained even if completion times out.
- Serial trials, no benchmark load running alongside latency trials. Direct model order shuffled with seed 42; cold calls retained. Repeated identical prompts and image can benefit from local prefix/vision caching. Unrelated machine/home-GPU activity was not controlled.

## Prompts and timing boundaries

- **small_talk:** Hello! How are you today?
- **part_frame:** What is this part?
- **multi_step:** How do I wire an LED with a resistor to a 5 V battery supply? Explain the steps and resistor calculation.

Frame: deterministic 320x240 drawing of an axial resistor, generated only in RAM. Direct Claude gets that small synthetic crop; Qwen gets the same image. This is not a real camera accuracy test.

Direct first = first nonempty text delta; total = streamed response end, including HTTP connection setup but excluding Python client construction. Every direct request has a **192-output-token cap**, low Claude effort using the existing fast_options(), Qwen thinking off and temperature 0. Cap hits are censored answer lengths: total is time to the cap, not time to a complete answer. Qwen may report stop even at exactly 192 tokens; the cap column therefore uses output_tokens >= 192.

Server first = first reply_delta/say after user_text; total = turn done, browser TTS selected (no STT, server TTS or physical playback timing). A fresh WebSocket/hello precedes each turn and is outside the timer. Server-side brain-first-token is a separate internal clock. No server restart or model override was performed.

## Direct model latency

Seconds, p50 / p95. Success means transport returned text, not that the answer is correct or complete.

| Model | Tier | Text returned / attempted | First text | Total (capped) | At token cap |
|---|---|---:|---:|---:|---:|
| claude-haiku-5-5 | small_talk | 10/10 | 1.07 / 2.10 | 1.23 / 2.10 | 0 |
| claude-haiku-5-5 | part_frame | 10/10 | 1.11 / 3.18 | 2.01 / 4.35 | 0 |
| claude-haiku-5-5 | multi_step | 10/10 | 0.96 / 1.26 | 1.62 / 2.30 | 10 |
| claude-sonnet-5-5 | small_talk | 10/10 | 1.17 / 1.80 | 1.62 / 2.24 | 0 |
| claude-sonnet-5-5 | part_frame | 10/10 | 1.18 / 2.44 | 2.73 / 3.33 | 9 |
| claude-sonnet-5-5 | multi_step | 10/10 | 1.14 / 2.50 | 2.61 / 4.07 | 10 |
| claude-opus-5-5 | small_talk | 10/10 | 1.17 / 1.31 | 1.63 / 2.08 | 0 |
| claude-opus-5-5 | part_frame | 10/10 | 1.93 / 2.19 | 2.76 / 3.15 | 10 |
| claude-opus-5-5 | multi_step | 10/10 | 1.05 / 7.95 | 2.67 / 9.29 | 10 |
| qwen3.5:9b-q4_K_M | small_talk | 10/10 | 0.46 / 0.54 | 1.01 / 1.14 | 0 |
| qwen3.5:9b-q4_K_M | part_frame | 10/10 | 0.31 / 0.47 | 1.02 / 2.01 | 0 |
| qwen3.5:9b-q4_K_M | multi_step | 10/10 | 0.42 / 7.07 | 2.09 / 7.96 | 10 |

## Running server on 127.0.0.1:8000

| Trial | Done / attempted | First text p50 / p95 s | Total p50 / p95 s | Internal brain first p50 / p95 s |
|---|---:|---:|---:|---:|
| small_talk | 10/10 | 1.72 / 3.48 | 1.74 / 3.49 | 1.06 / 3.43 |
| part_frame (frame sent immediately; scene not confirmed) | 10/10 | 1.53 / 2.13 | 1.53 / 2.14 | 0.89 / 1.47 |
| multi_step | 10/10 | 3.24 / 10.19 | 3.97 / 10.46 | 2.81 / 9.09 |
| part_frame (scene confirmed, continuous 5 Hz synthetic feed) | 10/10 | 2.39 / 6.76 | 3.91 / 7.07 | 2.32 / 5.39 |

Scene preparation p50/p95: **1.86 / 9.66 s**. From first frame to first answer: **5.22 / 16.42 s**; from first frame to turn done: **6.64 / 16.73 s**.

The original immediate-frame trials returned turn metrics with zero vision wait. Code inspection shows a first-scene race: the turn only briefly waits if a scene task already exists. Those trials do not establish visual understanding. The additional ten trials wait for a track message and keep sending fresh identical frames; preparation is measured separately. A track message confirms scene delivery, not visual accuracy or a non-fake backend.

Observed brain labels (all server trials): `{'Brain: expert / claude-opus-5-5': 33, 'Brain: local / qwen3.6:35b-a3b-q4_K_M': 7}`.

## Gemini Live audio

Uses the same discovery, setup, transport logger and synthetic-video mechanism as scripts/gemini_live_check.py. The original unmodified blue-frame check is run once as a control; then ten trials per requested tier use its shared production helpers. First audio means first received nonempty audio payload, not speaker playback. Audio total and capped text total are not comparable workloads. Setup/discovery are excluded; the frame tier has a one-second camera pre-roll outside the timer. Total ends at turnComplete; 40-second timeout, no retries.

| Tier | First audio / completed / attempted | First audio p50 / p95 s | Turn complete p50 / p95 s |
|---|---:|---:|---:|
| small_talk | 10 / 10 / 10 | 0.63 / 2.02 | 4.80 / 18.98 |
| part_frame | 10 / 10 / 10 | 1.13 / 3.18 | 8.69 / 18.59 |
| multi_step | 10 / 9 / 10 | 1.13 / 2.63 | 27.88 / 35.72 |

First-audio quantiles include every observed first-audio event, including turns whose completion timed out. Total quantiles include only completed turns; the missing completions are right-censored at 40 s and make the successful-only totals optimistic.

Original blue-frame control: `[{'run': 0, 'ok': True, 'first_ms': 1005, 'model': 'models/gemini-3.8-live', 'check': 'PASS', 'process_ms': 6971.782874999917, 'exit_code': 0}]`.

## Network round trips

Twenty unauthenticated HEAD requests per host, each with a new curl/TCP/TLS connection; no redirects followed. HTTP 4xx/3xx still count as a network response. HEAD total includes DNS, TCP, TLS and HTTP service time; it is **not ICMP RTT** and cannot be subtracted directly from pooled model latency. Connect includes DNS; TLS is cumulative time_appconnect. Home box uses HTTP over the configured private network.

| Host | Responses / attempts | HEAD total p50 / p95 ms | TCP connect p50 / p95 ms | HTTP statuses |
|---|---:|---:|---:|---|
| api.anthropic.com | 20/20 | 170.01 / 282.27 | 23.78 / 75.60 | {404: 20} |
| generativelanguage.googleapis.com | 20/20 | 140.77 / 202.29 | 22.61 / 81.88 | {404: 20} |
| api.cartesia.ai | 20/20 | 109.53 / 187.94 | 21.59 / 62.31 | {405: 20} |
| api.twelvelabs.io | 20/20 | 178.30 / 331.19 | 45.30 / 99.18 | {404: 20} |
| <PC_TAILSCALE_IP> | 20/20 | 208.49 / 395.18 | 116.60 / 192.30 | {200: 20} |

## Local HTTP and WebSocket load

Separate single-worker uvicorn process on 127.0.0.1:18080, A_EYE_MOCK=1, LOCAL_ONLY=1, fake vision/brain/voice, router off. A real synthetic frame/answer preflight verifies both fake dependencies. Each tier opens all WebSockets, then holds them for 30 seconds while one HTTP worker per simulated client requests / at up to one request/second. HTTP errors and throttling are retained. Requests completing after the 30-second boundary are counted separately as http_late and excluded from throughput/latency. End-of-window ping/pong verifies surviving sockets. No model inference, hello/session state or media fan-out in the timed handshake hold; this is an optimistic transport baseline.

CPU is sampled ps %cpu for the server PID (100% = one core; OS-smoothed, not interval CPU accounting). RSS is server-only resident memory. Client and unrelated processes are excluded. Connection ramp and cleanup are outside the 30-second window. The process soft FD limit is raised to at most 8192; system limits are unchanged.

| Target | Established / alive at end | Min sustained | HTTP successes / errors / late | HTTP req/s | HTTP p50 / p95 ms | CPU p50 / p95 % | RSS p50 / p95 MiB |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 50 / 50 | 50 | 1499 / 1 / 0 | 50.0 | 3.35 / 92.34 | 6.60 / 20.00 | 106.76 / 136.69 |
| 200 | 200 / 200 | 200 | 5519 / 1 / 1 | 184.0 | 3.05 / 510.06 | 17.90 / 23.50 | 167.66 / 173.97 |
| 1000 | 1000 / 1000 | 1000 | 5199 / 0 / 801 | 173.3 | 5611.73 / 5791.98 | 1.70 / 28.20 | 317.89 / 322.16 |

Target 50: handshake p50/p95 **8.14 / 9.32 ms**; server peak CPU **52.3%**, peak RSS **137.05 MiB**, 30 resource samples.

Target 200: handshake p50/p95 **49.37 / 56.46 ms**; server peak CPU **26.2%**, peak RSS **174.36 MiB**, 29 resource samples.

Target 1000: handshake p50/p95 **148.73 / 165.35 ms**; server peak CPU **28.2%**, peak RSS **322.16 MiB**, 6 resource samples.

At 1,000 clients the shared load-generator event loop was heavily delayed: only six resource samples arrived instead of approximately 30, and successful HTTP requests took about 5.6 seconds. This is an observed limit of this single-Mac test arrangement, not an isolated server saturation result. The low server CPU samples do not establish spare application capacity. Use a separate load-generator host for a throughput ceiling. Errors are counted, but this harness does not retain their individual HTTP status/exception breakdown.

**Maximum demonstrated sustained connections: 1000 for 30 s**, not a measured saturation limit or active video-call capacity. Handshake p50/p95 and all resource samples are in the JSON. Mock preflight: `{'fake_vision_track': True, 'fake_brain_reply': True, 'turn_done': True}`.

## Existing accuracy evidence (collected, not rerun)

| Claim | Supported result | Source and limit |
|---|---|---|
| Router | 96/100 = 96%; Haiku reference 97/100 | [router-train.md](router-train.md): same-agent-written held-out questions; 3 unsure count as wrong. Expert 17/20; not independent user distribution. |
| Vision | Qwen3.5 15/16 boxes (93.75%); Qwen2.5-VL 12/16 (75%) | [backend-benchmarks.md](../backend-benchmarks.md), measured 16-image set; [vision-route.md](vision-route.md) repeats baseline. Small benchmark, not camera-wide accuracy. |
| Pointer requested 10/10 | **Not substantiated in this checkout or pointer document history.** Available result: 3/10 cached, 0/10 uncached; zero wrong pointers, other cases abstain | [pointer.md](pointer.md), [pointer-benchmark.json](pointer-benchmark.json): real local grounding, synthetic scenes, scripted talker, 1.5 s freshness deadline. Do not present 10/10. |
| Recent memory | 20/20 source selection and 20/20 answer-content checks | [recent-memory.md](recent-memory.md): synthetic acceptance fixture; Rewind stubbed; not fresh service accuracy. Loopback text 3.78 ms. |
| Rewind rehearsal | Latest documented batch 5/5; earlier batch 4/5 | [demo-rehearsal.md](demo-rehearsal.md): synthetic camera/mic, real vision, TwelveLabs stand-in. Latest first audio range .34-.52 s, card 1.02-1.70 s. |
| Memory rehearsal | Later integrated batch 4/5 all checks; 5/5 sure with box | [demo-rehearsal.md](demo-rehearsal.md): one timing-window miss; [memory-rehearsal.md](memory-rehearsal.md) earlier 5/5 memory checks but 0/5 router-labelled-past checks. Different scopes, do not pool. |
| Private proof wall | Prior final three runs: 15/15 trials, 30 answers with final audio | [proof-wall.md](proof-wall.md): later execution reports audio unavailable; preserve its run-specific qualifications, not a blanket current-device claim. |

## Capacity model for one million users — ESTIMATES

Registered users are not concurrent calls. Assume 1M daily active users, each using a 10-minute call/day, 4 user turns/minute. That is 10M session-min/day, 40M turns/day, 6,944 mean simultaneous calls across 24 h. Concentrating use into 8 h gives 20,833 mean concurrent calls; a 2x peak gives **41,667**. A literal 1M simultaneous calls is a different target: **66,667 user turns/s**.

Illustrative uncached prompt: 1,000 input + 200 output tokens/request. At current official standard prices, Haiku $0.0002/request, Sonnet $0.004, Opus $0.008. A Haiku talker every turn plus an additional Opus request on 5% of turns costs **$0.0006/turn**, or **$0.024 per 10-minute call**. Adding a Sonnet planner on 20% of turns gives **$0.0014/turn / $0.056 per call**. The latter is a planning scenario, not the current General pack behavior. At 1M calls/day: **$24k-$56k/day ($720k-$1.68M/30 days)** for these text-model requests alone.

The observed running server often selects Opus; if every turn were Opus at the same assumed token counts, the text-only estimate would instead be **$0.32 per 10-minute call**. Real context, prompt caches, thinking/output lengths, retries and fallback routing change this. Excludes TTS/STT, vision GPU rental/electricity, Rewind, network egress, storage, servers and tax. Local inference has no API invoice but is not economically free. Gemini native audio is an alternative architecture and is not added to the Claude total.

Price sources checked 2026-10-24: [Anthropic standard token pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Haiku $0.10/$0.50, Sonnet $2/$10, Opus $4/$20 per million input/output tokens); [Gemini Live pricing](https://ai.google.dev/gemini-api/docs/pricing) (3.8 Live text $0.75/$4.50, audio $3/$12, image/video input $1 per million tokens). These are list prices, not a billing export.

| Layer | Bottleneck and required change (estimate) |
|---|---|
| Home GPU | First likely bottleneck in the existing local-perception architecture. At 6 scans/min/session and an assumed .5-2 GPU-seconds/scan, each session consumes .05-.20 GPU equivalents. At 70% target utilization that is only 3.5-14 sessions/GPU, before voice/local-brain contention. A 41,667-call peak needs roughly 3,000-12,000 equivalent GPUs; 1M simultaneous needs about 71,000-286,000. Service time, batching and concurrency are assumptions, not established by this handshake test. The .5 s optimistic endpoint is informed by the five synthetic repeats in vision-route.md; not a production capacity measurement. |
| Cloud APIs | At the 41,667-call peak, 4 turns/min means 166,668 talker requests/min, plus assumed 8,333 expert requests/min and optionally 33,334 planner requests/min. Talker alone needs about 166.7M input and 33.3M output tokens/min at assumed token sizes. Provider RPM/TPM/concurrent-stream quotas and regional reservations must be negotiated; no quota headroom was verified. Moving perception to cloud transfers this bottleneck and changes privacy/cost. |
| HTTP/WS server | Horizontally scale event-driven workers behind a WebSocket-aware load balancer, with admission control, per-call routing and graceful draining. Even an illustrative 1,000 transport connections/worker would imply 42 workers at the daily peak, 1,000 for 1M simultaneous, before redundancy/headroom. This is arithmetic, not a recommendation: active sessions need a new media/inference soak test and distributed session ownership. |
| Queue/state | Use a managed bounded queue for GPU/expert jobs, per-call priority/cancellation, coalesced latest frames, deadlines, backpressure and tenant quotas. Do not queue every video frame. Move reconnect/session metadata to a shared store; retain privacy boundaries and opt-in ephemeral media. Queueing cannot create GPU capacity and must not hide stale-frame failures. |

Scaling order: instrument real active-call service time and quotas; separate inference from socket workers; add GPU replicas and managed queue admission; distribute session state; then run multi-host active-call and failure-recovery tests. No million-user deployment is proven here.

## Spend and verification

Direct Claude usage-derived list-price cost: **$0.159571**. Budget ledger including conservative per-call allowances: **$1.734571 of $2**. Server and Gemini billing totals were not exposed by these paths; their reserved allowances are estimates, not measured charges. The client blocks new requests when reservations exceed $2, but cannot enforce a provider-side dollar ceiling inside the already-running server. No retries are issued by the direct benchmark.

Targeted checks: `make -s -f Makefile -f scripts/system_bench.mk system-bench-test`; real runs of direct, server, server_scene, gemini, network and load phases; git diff --check. App code, contracts and dependencies are unchanged. No full app-suite, physical microphone/camera, device playback, WAN-scale load or cloud billing reconciliation claim.

Reproduce with Make (the extra file loads the main checkout .env only when this worktree has no .env):

```sh
make -s -f Makefile -f scripts/system_bench.mk system-bench PHASE=network
# Then direct, server, server_scene, gemini, load, report, one phase at a time.
# Existing phase results are refused; archive the JSON before a fresh paid run.
```

All task changes are uncommitted.

## Lead addendum: pointer rerun on Ethernet (2026-10-24 ~22:50 UTC)

The lead reran `python -m server.probe_pointer --url http://127.0.0.1:8001` on the same cached-caption synthetic set after the Mac moved from venue Wi-Fi to Ethernet. Summary line as printed: `{"frames": 10, "hits": 10, "drawn": 10, "wrong": 0, "cached_caption": true, "median_added_ms": 1091.2, "max_added_ms": 1110.4}`. Same limits as pointer.md: synthetic scenes, scripted talker. The 3/10 result in pointer.md was measured on venue Wi-Fi. The JSON was not saved, so treat 10/10 as lead-observed, not file-backed.
