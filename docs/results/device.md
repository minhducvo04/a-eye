# Device client: result (2026-10-24, overnight)

**Built and verified on a Mac without hardware. Not verified: anything on a Raspberry Pi** (Pi camera, GPIO
button and LED, USB speakerphone, sounddevice playback, systemd unit, Tailscale on the Pi, Access service token).

## What works

- `device/`: a headless `/ws2` call device. Off by default (no socket, camera and mic closed). Button press or
  local motion turns it on; it turns itself off after 90 s with no change or at 15 min; another press turns it off.
- Private mode on by default (`hello.private: true`, server STT and TTS). `private = false` sends `hello.cloud`
  with the three switches.
- Frames at about 1 fps (640 px, q70), a 3-frame sharpest-of burst on turn-on, mic utterances by an energy VAD as
  `audio_in`, reply `audio` to the speaker, half duplex by default, barge-in as an option.
- Person drop on the device with OpenCV's HOG detector when OpenCV (below 5) is installed. Checked that it loads
  and runs (9 ms, no false positive on the synthetic table); not checked on a frame with a real person (no real
  people in tests by rule). OpenCV 5 removed `HOGDescriptor`, so the requirement pins `<5`.
- No server or contract change was needed.

## Real run: full turn against a real local server

`.venv/bin/python -m device.fake_turn --idle 20 --ask-at 8` from the worktree, server and vision (fake backend)
on free ports, auth off, temporary memory folder, Private on, STT and Kokoro on the GPU box, box Ollama not
touched (`OLLAMA_URL` pointed at a closed port). Synthetic key-table clip, macOS `say` mic, null speaker.

| Check | Result |
|---|---|
| turned on by the button | PASS (0.5 s) |
| server said listening, private hello | PASS (0.87 s) |
| frames sent | PASS (33) |
| utterance sent as audio_in | PASS (1.8 s of speech) |
| turn received | PASS (10.48 s, 0.01 s after the end of speech) |
| Whisper heard | "Where are my keys?" |
| reply text | PASS: "Let me think back." then "I last saw your keys by the middle motherboard, just now. Their home is the blue bowl. I'm pointing at it now." (find_item found; "motherboard" is the fake vision label) |
| reply audio received | PASS (8.65 s of PCM16 in 2 utterances) |
| turned itself off (idle 20 s for the test) | PASS (33.8 s: last reply audio plus 20 s) |
| no server errors | PASS |

Two earlier runs used `VISION_BACKEND=auto` (box Ollama) before the request to leave the box alone; they also
passed (find_item "not seen yet", since the first real scene took 16 s). Those two runs warmed models on the box.

## Tests

`.venv/bin/python -m pytest device -q`: **17 passed** (13 unit: power on/off, 90 s idle, change restarts idle,
15 min cap beats constant change, motion vs noise and jitter, VAD start/end/pre-roll/cap, privacy hello, env-only
credentials, example config; 4 client tests against an in-process mock server: full turn with reply audio and
idle off, motion trigger, person frames never sent, nothing sent while off).

## Limits

- `python -m device.fake_turn --mock` fails today: `server/mock.py` `MockBrain.stream` rejects the keyword options
  ws2 now passes (TypeError at `server/ws2.py:331`). The pytest client tests use their own brain stub instead.
  Owner of `server/mock.py` should add `**kwargs`.
- No wake phrase. Motion counts a hand reaching in, not a small key ring alone (about 0.2% of the picture).
- `SoundDeviceSpeaker.playing()` estimates playback end from bytes queued; fine for half duplex, rough for barge-in.
