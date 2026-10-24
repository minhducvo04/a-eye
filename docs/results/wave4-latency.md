# Wave 4 latency, measured 2026-10-23 about 20:10 PDT

Real stack: vision on the GPU box (Qwen2.5-VL, one label per call, num_ctx 4096, keep_alive 30m), local brain
qwen3.5:9b think off, `boxsvc` on the box (faster-whisper large-v3-turbo, Kokoro 82M, YOLO11n), server and browser
on the developer Mac over Tailscale. Synthetic test images and Kokoro-made speech only; no real camera or mic.

| What | Measured |
|---|---|
| Old `/scene` call (why it was 5 s) | cold load 2.2 s; changing num_ctx reloaded the model for 6.8 s; multi-label prompt generated 119 tokens (0.75 s) |
| One-label vision call, fresh frame, from the Mac | 0.96 to 1.05 s wall (image prompt eval 0.62 s, generation 0.22 s) |
| Same image repeated (prompt cached) | median 406 ms [357 to 1748], n = 5 |
| Kokoro first audio from the Mac, warm | 141 to 153 ms |
| Whisper turbo, 2 s utterance | 101 to 109 ms on the box; 324 to 741 ms wall (upload over Tailscale), also during a VLM call |
| YOLO11n 320 px detect | 9 ms on the box, 170 ms median wall |
| Local brain probe (`make llm-probe`) | 408 ms warm |
| Voice turn, browser STT + server Kokoro (WS script, 3 runs) | end of speech to first audio 861, 889, 984 ms |
| Voice turn, server Whisper + Kokoro (WS script, 3 runs, real-time paced) | 1879, 1943, 2559 ms (the audio upload is the extra) |
| Agent page dev overlay, typed question + Kokoro (`?dev=1&tts=server`) | voice 1284 ms, brain 550 ms, audio 1281 ms, turn 2019 ms |
| Agent page dev overlay, typed question + browser TTS | voice 1197 ms, brain 830 ms |

Default for the demo: browser STT (Safari) + Kokoro TTS meets the 1.5 s budget. Server Whisper does not over
Tailscale (about 1.9 s); on the venue LAN or with streamed upload it may.
