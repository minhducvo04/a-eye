# Live bridge hold fixes — 2026-10-25

Branch: `pkg/fix-bridge`. Starting revision: `cb2ad61`.

Mic chunks after VAD ends no longer release an active guide task, memory hold or
memory task, or a latched safety stop. The chunk still reaches the input wire.
Ordinary barge-in can still reset its reply. The existing hold-owner reset and
cancellation APIs and memory version checks are unchanged; raw PCM does not
cancel or invalidate their work.

`prompt_turn()` already re-checks both `safety_stopped` and `closed` after its
provider-idle wait, including the timeout path. That fix arrived in
`5f9bb95` through `pkg/fix-memory` (merge `738f934`). No duplicate production
change was needed there.

Two regression functions were added to `server/test_gemini_live.py`:

- `test_mic_chunk_preserves_code_owned_hold`: stalls the actual guide valve-check
  path or memory lookup, ends VAD, sends another mic chunk and synthetic provider
  output, and verifies no captions/audio escape. It also checks a safety stop
  stays latched, memory versions survive PCM, owner completion sends the checked
  prompt, and ordinary barge-in remains usable (four cases).
- `test_prompt_turn_rechecks_stop_after_provider_idle_wait`: changes safety or
  closed state while the prompt is waiting, then releases the wait normally or
  raises its timeout. Every case must return false, retain the block, and send
  no provider prompt (four cases). These passed on the inherited implementation.

## Verification

The mic reproduction failed before the production fix: **3 failed, 1 passed**
(guide, memory and safety leaked output; ordinary barge-in passed). An initial
guide fixture needed `introduced=True` to reach the valve checker; the corrected
fixture reproduced the output leak before the production edit.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_gemini_live.py -k 'mic_chunk_preserves or prompt_turn_rechecks' --tb=short` - PASS (**8 passed, 36 deselected in 0.76s**).

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server router` - PASS
(**908 passed, 2 warnings in 50.90s**, exit 0; final summary read).

The first full run was blocked by sandbox loopback-socket restrictions:
**15 failed, 893 passed, 2 warnings in 49.29s**. The successful rerun had local
socket access. The two warnings concern short synthetic JWT signing keys in
existing identity tests. The suite exercised real local HTTP/WebSocket transport
with fake providers; no real Gemini calls were made.

Test: `git diff --check` - PASS.

Changed files: `server/gemini_live.py`, `server/test_gemini_live.py`,
`docs/results/fix-bridge.md`, and the appended root `RESULT.md` receipt.

Limits: no `.env` reads, real media, real Gemini calls, push, deployment, or
physical-device verification. Guide and memory owner implementations were not
edited. Existing explicit text-turn recovery behavior is unchanged; this fix
prevents raw mic input from releasing code-owned holds or safety stops.

Finished
