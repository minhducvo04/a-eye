# voice package

In-process TTS/STT adapter: Fake by default, Cartesia HTTP TTS when `CARTESIA_API_KEY` is set and `VOICE=cartesia`. Closed-set `match_command`. Cartesia STT is not implemented.

## Changed files

- `voice/adapter.py`
- `voice/fake.py`
- `voice/cartesia.py`
- `voice/commands.py`
- `voice/test_voice.py`
- `voice/README.md`
- `RESULT.md`

## Limitations

- `CartesiaAdapter.transcribe` raises `NotImplementedError("STT runs on the GPU host; see TODO")`. User audio is never sent to Cartesia.
- Cartesia TTS was written from current docs (`POST https://api.cartesia.ai/tts/bytes`) and checked only with `httpx.MockTransport`. No live API call.
- Docs used: https://docs.cartesia.ai/api-reference/tts/bytes (headers `Authorization: Bearer`, `Cartesia-Version: 2026-08-14`, `voice` as a string id, `model_id` `sonic-3.6`). Get-started still shows an older body (`voice: {mode, id}`) and version `2025-04-16`; we followed the bytes reference.
- Live acceptance of `output_format.container=raw` at 16000 Hz `pcm_s16le` is UNVERIFIED (docs list `raw` + `pcm_s16le` + 16000 as valid; this worktree never hit the network).

## Test

Test: .venv/bin/python -m pytest -q voice - PASS (23 passed in 0.11s)

Whole repo: `.venv/bin/python -m pytest -q` — PASS (64 passed in 0.13s)
