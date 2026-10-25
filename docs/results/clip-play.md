# Found-memory clip playback

Implemented on `pkg/clip-play`, based on `f5bbfc5`, in this worktree only. No push.

The existing found card now plays up to twelve JPEG frames from this call, each
at most 320 pixels on its longest side. Frames are ordered, sampled over the
available window from three seconds before to three seconds after the hit, and
loop at the supplied rate. One available frame stays still. Uploaded clips
already retain only six or seven frames, so playback can be sparse.

For saved calls, the existing TwelveLabs HTTP client retrieves
`/indexes/{index}/videos/{video_id}` and reads `hls.video_url`. Retrieval is
optional, consent-gated, and cancelled after two seconds. Missing URLs, provider
errors, or unsupported clients leave the existing evidence intact. The timestamp
`t_s` stays call-relative; with `clip_url`, `start_s` and `end_s` are video-relative
playback bounds around the hit. This prevents seeking to a full-call timestamp
inside a short uploaded video.

Native HLS playback is muted and inline, looping only the selected window.
Browsers without native HLS keep the frames or still. Playback errors restore
that fallback. Closing/replacing the card or opening another sheet disposes the
timer and video. Existing object boxes remain over the media; they are static
hit-frame boxes, not tracking boxes. The card layout and scope routing are unchanged.

Both the ordinary Rewind tool and Live memory callback use the same media
builder. Images and stream URLs are stripped from model tool results. The v2
schema, TypeScript type, and examples include the requested optional fields;
validation remains enabled. No dependency was added.

## Changed files

- `server/rewind.py`: bounded frame sequence, video retrieval, client payload.
- `server/rewind_tools.py`: keep all playback media out of model tool results.
- `server/gemini_live.py`: attach playback to the existing Live memory callback.
- `client-web/memory.js`, `client-web/agent.js`: playback and lifecycle cleanup.
- `contracts/schema.json`, `contracts/types.ts`, `contracts/examples.json`: optional v2 playback fields.
- `server/test_clip_play.py`, `client-web/clip-play.test.mjs`: synthetic regressions.
- `docs/results/clip-play.md`, `RESULT.md`: delivery evidence.

## Verification

Python checks use `PYTHONPATH=.pytest_cache/clip-play/offline:.`; a local
`sitecustomize.py` audit hook blocks network operations and `.env` access.
HTTP retrieval uses `httpx.MockTransport`; JPEGs are generated in RAM. Logs are
under `.pytest_cache/clip-play/` (ignored). No real camera media was used or stored.
The repository-wide Python target is invoked directly as `python -m pytest -q`
because the Makefile otherwise includes `.env`.

Before implementation, three initial server regressions and all three client
playback regressions failed. After implementation, all seven server playback
regressions pass, including both Live memory scopes, resizing/order/count,
media exclusion from tool results, timeout cancellation, and privacy gates.
All 175 client tests pass, including cycling, looping, cleanup, single-frame
fallback, native-HLS seeking, and error fallback.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server` - FAIL
(1146 passed, 22 failed, 2 warnings, 97.08 s; final source, summary read).
Test: `node --test client-web/*.test.mjs` - PASS (175 passed, 0 failed).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_clip_play.py server/test_live_prefetch.py::test_rewind_consent_revocation_blocks_lookup_and_cached_evidence` - PASS (8 passed; final source).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q contracts server/test_rewind.py server/test_past_calls.py server/test_live_memory.py server/test_recall_review.py` - FAIL (136 passed, 5 inherited failures; all contract examples passed).
Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q` - FAIL (1750 passed,
25 failed, 4 errors, 2 warnings; run before the final text-only-hit guard).
Test: `git diff --check` - PASS.

The final server failures comprise 15 tests blocked by network restrictions
(including a downstream Live-start assertion) and 7 non-network failures
reproduced unchanged against the original `f5bbfc5` source in an ignored snapshot
inside this worktree. That baseline comparison returned 29 passed, 7 failed.
The inherited failures concern private-session saved-call selection, summary
wording/evidence, old card-suppression expectations, and old memory-routing
expectations. They were not weakened or changed.

The broader Python run also has a denied synthetic `.env` read, another socket
test failure, and four device socket-fixture errors. It caught a playback
regression for a text-only fake hit: invoking the media helper lost its answer.
The final guard skips media building without a frame or video ID; the existing
consent-revocation test now passes, as do all new playback tests. The final server
run above includes this correction. No all-suite PASS is claimed.

Evidence: `server-final.log`, `client.log`, `targeted.log`, `baseline.log`, and
`test-py.log` in `.pytest_cache/clip-play/`. Initial failed acceptance tests are
also visible in the session output. The baseline comparison ran
`server/test_past_calls.py`, `server/test_live_memory.py`,
`server/test_gemini_live.py::test_recent_tool_temporal_routes_and_local_result_cards`,
and `server/test_recent_memory.py::test_fixture_sources_and_honest_fallback`.

Final failed server nodes:

- `server/test_bg_context.py::test_live_publishes_context_while_next_build_waits_and_cancels_on_close`
- `server/test_cloud_meter.py::test_real_websocket_send_boundary`
- `server/test_gemini_live.py::test_fake_live_recent_step_transcripts_and_scene_stay_local`
- `server/test_gemini_live.py::test_recent_tool_temporal_routes_and_local_result_cards`
- `server/test_gemini_live.py::test_fake_live_wire_audio_tools_captions_and_revocation`
- `server/test_gemini_live.py::test_reconnect_once_then_fallback_and_close`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[False-False]`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-False]`
- `server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-True]`
- `server/test_limits.py::test_live_minutes_stop_idle_connection`
- `server/test_live_memory.py::test_code_owned_memory_does_not_send_query_or_crop_cards[rewind-rewind_hit]`
- `server/test_live_memory.py::test_code_owned_memory_does_not_send_query_or_crop_cards[long-term-find_item]`
- `server/test_live_prefetch.py::test_slow_tool_does_not_delay_audio`
- `server/test_live_prefetch.py::test_streaming_prefetch_card_cache_and_idle_publication`
- `server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[False]`
- `server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[True]`
- `server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio`
- `server/test_past_calls.py::test_cloud_block_still_allows_local_summary[private]`
- `server/test_past_calls.py::test_save_snapshots_text_before_cleanup`
- `server/test_past_calls.py::test_summary_bound_and_legacy_record_fallback`
- `server/test_recent_memory.py::test_fixture_sources_and_honest_fallback`
- `server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero`

## Limits

No live TwelveLabs, browser, Safari, or physical-device playback was performed:
network access was prohibited. HLS availability and the provider response shape
are verified only with fake responses. A past hit without an available URL or
local image retains its existing text-only result. No changes were made to
routing, saved-call storage, frame retention, or unrelated failing tests.
