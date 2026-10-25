# Past-call recall

Implemented on `pkg/past-calls`, based on `301fcbd`, 2026-10-25. Local commit only; no push.

Past-call questions now check saved Rewind calls before the local item/task store.
Object questions use `search_kept(question)` when TwelveLabs consent permits it,
reuse Rewind's saved-call age/offset sentence, and deliver the hit to `on_hit` for
the existing client card. A fresh call resolves its index before searching; it
does not need to upload a new clip first. Hits remain `sure=False` because they
have not received a frame-level vision check.

Generic questions, search misses and cloud-blocked requests use the newest kept
call's local summary. Explicit dates constrain the summary lookup. The current
session and its camera are never past-call evidence. Explicit temporal wording
wins; the decision model's past scope wins over the generic “what did I” recent
default. Missing summaries retain the existing long-term/honest fallback.

Saving a call snapshots up to 12 distinct recent scene captions plus user
questions, capped at 1,500 characters, beside the existing call start time and
clip IDs in `rewind_kept.json`. Helper claims and media are excluded. The snapshot
happens before WebSocket teardown clears RAM and before background indexing.
The anonymous-owner shared-library gate also applies to local summary reads.
Private mode, LOCAL_ONLY and missing consent block video search; local saved text
remains available as requested.

Changed files: `server/recent_memory.py`, `server/rewind.py`, `server/ws2.py`,
`server/test_past_calls.py`, this report and `RESULT.md`. No UI or contract changes.

## Verification

All tests used synthetic text/video IDs and fake service clients under the
network-restricted sandbox. No `.env` reads or external service verification.

- Before production edits: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_past_calls.py`
  — FAIL, 8 failed in 0.22s; reproduced missing summary, missing kept search,
  semantic past scope incorrectly reading current notes, and missing saved text.
- After production edits: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_past_calls.py server/test_recent_memory.py server/test_recall_review.py server/test_recall_pipeline.py`
  — PASS, 40 passed in 1.57s.
- Required suite: `~/Projects/a-eye/.venv/bin/python -m pytest -q server`
  — FAIL, **1,144 passed, 15 failed, 2 warnings in 95.81s**. Summary read.
- Final expanded acceptance file: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_past_calls.py`
  — PASS, **10 passed in 0.24s**. Added bounds/legacy-record/shared-owner checks
  and verified generic recall skips search even when consent is on. Production
  source was unchanged after the full suite started.
- Failure diagnosis: `~/Projects/a-eye/.venv/bin/python -m pytest -q server --lf --tb=line`
  — FAIL, 15 failed in 1.04s: 14 socket-bind `PermissionError` failures and one
  downstream missing `state` assertion after Live startup logs `PermissionError`.
- `git diff --check` — PASS.

Full-suite failures (no network permission relaxation attempted):

| Module | Failed tests |
| --- | --- |
| `test_bg_context.py` | `test_live_publishes_context_while_next_build_waits_and_cancels_on_close` |
| `test_cloud_meter.py` | `test_real_websocket_send_boundary` |
| `test_gemini_live.py` | `test_fake_live_recent_step_transcripts_and_scene_stay_local`; `test_fake_live_wire_audio_tools_captions_and_revocation`; `test_reconnect_once_then_fallback_and_close`; all three `test_reconnect_reuses_latest_resumable_handle` cases |
| `test_limits.py` | `test_live_minutes_stop_idle_connection` |
| `test_live_prefetch.py` | `test_slow_tool_does_not_delay_audio`; `test_streaming_prefetch_card_cache_and_idle_publication` |
| `test_live_streaming.py` | both `test_fake_live_streams_before_complete_and_stops_mid_reply` cases; `test_ws2_hazard_sends_stop_caption_and_fixed_audio` |
| `test_step_check.py` | `test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero` |

## Demo limit

The five existing saved records have no summary, according to the bug report;
their contents were not read or modified. Object search can use their existing
video IDs, but generic “last call” content cannot be reconstructed offline.
Save a new call after this change to demonstrate generic summary recall.
Summaries cover the retained recent-memory window, not an entire long call.
Real TwelveLabs results, Gemini speech and device/card rendering remain unverified.
