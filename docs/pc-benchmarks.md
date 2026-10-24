# GPU box benchmarks (2026-10-23)

Question: which models should the A-eye app use on the GPU box, and does each fit a real-time budget? Duc's
requirement: "it must run in real time". The budgets used below:

| Loop | Budget |
|---|---|
| Fast loop (detect, track, point) | at least 15 fps, so 66 ms or less per frame, end to end |
| Slow loop (VLM grounding answer) | 1 s or less |
| Voice turn | 1.5 s or less from end of speech to first sound |

## What was measured

- Machine: "the GPU box" (Windows, RTX 3090 Ti 24 GB, driver 610.88, Ollama 0.40.8, all models 4-bit). The idle
  desktop uses about 0.9 GB VRAM, so VRAM figures below include that. The brother's desktop was running, and
  another agent session had used the same Ollama before the runs, so contention was not controlled (the spreads
  were small).
- Every row: 1 warm-up, then n = 5 runs (YOLO n = 50, SAM n = 10, partial transcripts n = 5), reported as
  median [min to max]. Ollama numbers come from the server's own counters (`prompt_eval_duration`,
  `eval_duration`) and a streaming client on the box itself ("on box"). Rows marked "from Mac" ran from the
  developer Mac over Tailscale, so they include the network.
- Cache control: every Ollama request got a unique first line so prompt-prefix caching could not fake the
  prompt-processing time. A repeated identical request showed 27 to 60 ms time to first token, which is not
  representative.
- Vision photo: a public Wikimedia Commons motherboard photo (Gigabyte GA-H87M-D3H; licence not checked, used for
  benchmarking only). Box checks were done by eye on an overlay of the saved answers.
- Speech clip: 10 s from a public Wikimedia Commons recording (Roosevelt, Pearl Harbor address).
- Raw outputs: `C:\kyra-work\bench\res_*.json` on the box (private; not in git).

## Results

Real-time verdict: **meets**, **close** (within about 1.5x of budget, or meets only with a stated condition), or **no**.

| Job | Model and setting | Result (median [min to max]) | Real-time verdict |
|---|---|---|---|
| Fast loop, on box | YOLO11n, 320 px, fp16 | 19.0 ms/frame wall [18.5 to 26.0], 6.2 ms GPU | meets (about 50 fps) |
| Fast loop, on box | YOLO11n, 640 px | 23.9 ms [21.5 to 32.3], 9.0 ms GPU | meets (about 40 fps) |
| Fast loop, on box | YOLO11s, 320 / 640 px | 18.0 ms [17.8 to 19.8] / 23.3 ms [22.0 to 26.6] | meets |
| Fast loop, Mac over Tailscale, JPEG upload, one frame at a time | YOLO11n, 320 px (27 KB frame) | 184 ms [148 to 376] = 5.4 fps; 3 requests in flight: 9.5 fps | no |
| Same | YOLO11n, 640 px (106 KB frame) | 215 ms [172 to 944] = 4.6 fps; 3 in flight: 6.1 fps | no |
| Same | YOLO11s, 320 / 640 px | 178 ms = 5.6 fps (8.8 pipelined) / 233 ms = 4.3 fps (6.3) | no |
| Segmentation, on box | SAM2.1 large, 1024 px, one point prompt incl. image encode | 148 ms [147.7 to 148.5] | no per frame; fine on demand |
| Slow loop, on box | qwen2.5vl:7b, 1280 px, ONE label, JSON box (about 34 tokens) | 0.28 s total [0.27 to 0.30], first token 0.07 s | meets |
| Slow loop, from Mac | same | 0.63 s [0.59 to 2.0], first token 0.46 s | meets (median) |
| Slow loop, on box | qwen2.5vl:7b, 1280 px, FIVE labels (about 189 tokens) | 1.28 s [1.26 to 1.28], 158 tok/s generation | close |
| Slow loop, on box | qwen2.5vl:7b, 1024 px, five labels | 1.21 s [1.20 to 1.22] | close, boxes 4 of 5 right |
| Slow loop, on box | qwen2.5vl:7b, 640 px, five labels | 1.20 s | boxes unusable (finding 1) |
| Slow loop, on box | qwen2.5vl:7b at 320, 448, 640 px, one label | 0.24 to 0.26 s | fast but boxes unusable (finding 1) |
| Slow loop | SmolVLM2-2.2B | not measured: failed to run (transformers version mismatch in the venv, two tries) | not run |
| LLM, on box | qwen3.5:9b, think off, 1.2k-token prompt, 200-token answer | prompt 4,799 tok/s [4,777 to 4,864]; generation 124.6 tok/s [124.4 to 124.9]; VRAM 7.3 GB | meets |
| LLM, on box | gemma4:12b | prompt 2,765 [2,711 to 2,772]; generation 130 [127 to 143]; VRAM 9.7 GB | meets |
| LLM, on box | gemma4:26b-a4b | prompt 4,414 [4,399 to 4,426]; generation 145; VRAM 19.0 GB, all on GPU | meets |
| LLM, on box | qwen3.6:35b-a3b | prompt 3,045 [3,028 to 3,081]; generation 149; VRAM 23.5 GB; **about 0.9 GB (4%) runs on CPU: spills** | meets, no headroom |
| Voice, LLM first token, short reply | qwen3.5:9b / gemma4:12b, think off | on box 0.076 s / 0.069 s; from Mac 0.16 s [0.14 to 0.26] / 0.12 s [0.11 to 0.20] | meets |
| Voice, speech to text | faster-whisper large-v3-turbo fp16, 10 s clip | 0.114 s [0.114 to 0.126], RTF 0.011; transcript correct | meets |
| Voice, speech to text | faster-whisper large-v3 fp16 | 0.239 s [0.237 to 0.244], RTF 0.024 | meets |
| Voice, partial transcript | turbo, decode of a 1 s / 2 s buffered window | 0.090 s / 0.091 s (large-v3: 0.116 / 0.123 s) | meets (decode time only; add the audio chunk length) |
| Voice, text to speech | Kokoro 82M, GPU, one 18-word sentence (6 s of audio) | first audio 0.060 s [0.059 to 0.065], RTF 0.01; cold load 21 s | meets |
| Voice, text to speech | Chatterbox | not run (not needed while Kokoro is this fast) | not run |
| Concurrency, on box | VLM (1280 px, one label) running while qwen3.5:9b generates | fits: 14.1 GB VRAM. VLM 0.30 s alone becomes 0.69 s [0.36 to 0.71] (n = 26). LLM 124.6 becomes 55 tok/s | close |
| Concurrency, on box | VLM while gemma4:12b generates | fits: 16.4 GB. VLM 0.30 becomes 0.69 s; LLM 130 becomes 62 tok/s | close |
| Network | Mac to box, Tailscale direct path | ping 101 ms (one sample); HTTP keep-alive request median 79 to 111 ms [59 to 233], n = 30 per run; a new connection each time median 338 ms [204 to 539] | 100 to 200 ms of every remote call |

Voice turn estimate (a sum of measured parts, not an end-to-end run): speech to text 0.11 s + first LLM tokens
0.08 s + first audio 0.06 s = about 0.25 s of compute, plus two network trips (about 0.2 s), plus the silence
timeout chosen to decide the user stopped talking (0.3 to 0.5 s). About 0.8 to 1.0 s: **meets** if that silence
timeout stays under about 0.5 s.

Network share: the single-label VLM answer is 0.28 s on the box and 0.63 s from the Mac, so about 55% of the
remote latency is network and upload. A short LLM reply is 0.07 s on the box and 0.12 to 0.16 s from the Mac (about
50% network). Detection is worst: about 20 ms of work on the box becomes 180 to 230 ms from the Mac, so about 90% of
it is network.

## Findings that change the design

1. **Use 1280 px long edge for grounding.** Qwen2.5-VL under Ollama returns boxes in a coordinate space that does
   not match the image you sent when the image is small: at 640 px, boxes reached x = 922 (outside a 640-wide
   image) and, with a five-label prompt, the five boxes stacked in one column; at 320 and 448 px the coordinates
   were also out of range. At 1024 px, 4 of 5 labels landed on the right header; at 1280 px all 5 landed (checked
   on an overlay), which is the size `vision/ollama.py` already sends. Smaller images do not make it faster
   either: prompt token counts were nearly the same for 320 to 640 px.
2. **Ask for one label per call.** Latency is generation time, about 160 tok/s: 34 tokens is 0.28 s, 189 tokens is
   1.28 s. One or two labels meets the 1 s budget; the five-label prompt does not.
3. **Set `num_ctx` explicitly and keep it the same on every call to a model.** A 1280 px frame is about 2,100
   tokens, so `num_ctx` 2048 fails with HTTP 400; 4096 works. Changing `num_ctx` between calls reloads the model
   (3 to 7 s stalls when a bench switched between 4096 and 2048).
4. **The cold start is 2 to 3 s** (2.2 s load for the VLM). Keep the model loaded and send one warm-up request at
   app start.
5. **Detection over the WAN cannot be real time.** The GPU does it in 6 to 10 ms, but a one-frame-at-a-time round
   trip from the Mac is 180 to 230 ms because of the 100 ms network RTT plus the upload. Pipelining three requests
   reached at most 9.5 fps at 320 px. The fast loop must run next to the camera (phone or Mac), or the client must
   be on the same LAN as the box. A LAN estimate (not measured): about 25 to 35 ms per frame on the box plus a few
   ms of network, so about 30 fps.
6. **Running the VLM and an LLM at the same time fits in VRAM but costs speed**: the VLM takes 2.3x longer and the
   LLM runs at 45% speed. Do not generate a spoken reply while a grounding call is in flight if the pointer must
   stay under 0.5 s.
7. **qwen3.6:35b-a3b spills to CPU** (0.9 GB of 23.2 GB) and fills the card; gemma4:26b-a4b (19 GB) cannot sit next
   to the VLM (7.4 GB) either. Neither is a router; use them alone for a hard reasoning step if ever.

## What to use for which job

| Job | Use | Why |
|---|---|---|
| Pointing and tracking each frame | YOLO11n at 320 px, then a tracker or optical flow between detections, running on the phone or Mac | 6 ms GPU, but not usable over the WAN |
| Locate a named header or part (slow loop) | qwen2.5vl:7b, 1280 px, one label per call | 0.28 s on box, 0.63 s from Mac, boxes land on the right label |
| Router and short spoken replies (brain) | qwen3.5:9b, think off | 125 tok/s, 0.07 s first token, 7.3 GB, co-resides with the VLM |
| Alternative brain | gemma4:12b | 130 tok/s, 9.7 GB, slower prompt processing (2.8k tok/s) |
| Heavier reasoning, run alone | gemma4:26b-a4b | 145 tok/s, 19 GB, fully on GPU; not alongside the VLM |
| Speech to text | faster-whisper large-v3-turbo, fp16 | 0.11 s per 10 s of audio; partials about 0.09 s |
| Text to speech | Kokoro | 0.06 s to first audio |
| Cut out a region on demand | SAM2.1 large | 148 ms per prompt, too slow per frame |

## Recommended default config

Two loops:

- **Fast loop (every frame, 30 fps)**: detect with YOLO11n at 320 px and track between detections on the client.
  If it must run on the GPU box, the client has to be on the same LAN; do not plan on more than 5 to 9 fps over
  Tailscale.
- **Slow loop (about once a second, or on a step change)**: one grounding call to qwen2.5vl:7b for the label the
  current step needs, 1280 px long edge, answer about 0.3 s on the box and about 0.6 s from this Mac (add the
  venue's own RTT). Snap the tracker to the returned box.

```
VISION_MODEL=qwen2.5vl:7b-q4_K_M
vision call: image long edge 1280, one label per call, temperature 0, num_predict 60,
             num_ctx 4096 (same on every call), keep_alive "30m", warm-up call at app start,
             HTTP keep-alive connection reused
brain/router: qwen3.5:9b-q4_K_M, think off, num_ctx 4096, keep_alive "30m"
stt: faster-whisper large-v3-turbo fp16     tts: Kokoro
VRAM: VLM plus brain together used 14.1 GB of 24 GB (includes 0.9 GB desktop); Whisper and Kokoro VRAM not measured
```

Changes this implies in `vision/ollama.py` (not made here): the request has no `options`, so it uses Ollama's
default context (32k, which wastes VRAM) and no `keep_alive`; the locate prompt asks for all headers at once
(1.3 s) where one label would take 0.3 s; the client timeout is 20 s.

## Not measured or failed

- SmolVLM2-2.2B: failed to run (transformers incompatibility); not retried.
- Chatterbox: not run. SAM2.1 small or base: only the large checkpoint is on the box, so large was timed.
- Whisper and Kokoro VRAM, and a combined voice plus vision plus LLM run: not measured. The voice turn above is a
  sum of parts.
- Fast loop on a LAN, or on the phone: not measured. Network numbers are from the developer Mac's connection, not
  the venue's; re-run `tailscale ping` and the keep-alive request from the venue. A first YOLO-over-network pass ran
  while a model download saturated the box's link (2.8 to 3.3 fps); it was discarded and redone.
- Box accuracy used one board photo and five labels, judged by eye. It supports "1280 px works on this photo", not
  an accuracy rate.
- Setup for the speech and detection runs: a venv at `C:\kyra-work\venv-bench` (torch cu128, ultralytics,
  faster-whisper, kokoro, transformers) and a hard link `C:\kyra-work\bench\sam2.1_l.pt`. The faster-whisper turbo
  weights were downloaded to `C:\kyra-work\models\faster-whisper-large-v3-turbo`. No Windows settings, drivers or
  tasks were changed; Ollama was not restarted and stayed on 100% GPU.
