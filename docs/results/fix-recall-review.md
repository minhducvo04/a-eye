# Recall review fixes

All ten high/medium findings from the independent Recall review are fixed on `pkg/fix-recall`.
Final server run: **864 passed, 2 warnings in 46.35s**. No real TwelveLabs or Gemini calls were made.

## Changes and reproductions

Ten regression functions in `server/test_recall_review.py` reproduced all ten findings before the fixes
(`10 failed in 0.84s`). The final file has eleven cases because the flush race runs at two boundaries.

| Review finding | Change | Regression function (without `test_`) |
| --- | --- | --- |
| High: water location triggers a shutoff lecture | Match running/still-on/not-off supply claims, excluding “water is on the left/floor/stove.” The valve checker remains the only plumbing-step unlock. | `water_location_is_not_running_supply` |
| High: PSU connection question triggers live-wire stop | Ordinary PSU/power-supply “plugged in?” questions pass; actual live-power and wire-work claims still stop. | `psu_connection_question_is_not_live_wire_work` |
| Medium: wet electronics omitted | Add PSU, power supply, charger, power strip, computer and laptop to the water/electric pairing. | `water_electric_includes_demo_devices` |
| High: hello/socket teardown deletes a replacement call | Reuse the active object for the same session and owner. Repeated hello stops its sampler without ending Rewind. Socket teardown passes its Rewind and Session objects; stale cleanup cannot end a replacement or a resumed call now attached to a newer socket. | `repeat_hello_and_stale_socket_cleanup_preserve_call` |
| High: disabling during flush loses uploaded IDs | Stop sampling immediately; prune unsent work under the flush lock. Recheck consent after encoding. Forget waits for uploads before cancelling polls and deleting. Both index-creation and upload-in-flight race points are tested through call-end cleanup. | `off_during_flush_keeps_uploaded_id_for_deletion` |
| Medium: Private/spend cap blocks deletion | Forget calls `delete_video(..., force=True)`; deletion failure retains the ID for another attempt. MockTransport verifies a DELETE with Private and the cap active. | `forget_deletes_even_with_private_mode_and_spend_cap` |
| Medium: anonymous kept-call leakage | Open-demo owner `local` neither reads nor writes a shared saved-call catalog. Its retained clips remain scoped to the current call. Authenticated saved-call reads/writes use that call's owner key; Alice/Bob controls verify isolation. | `anonymous_kept_calls_never_cross_call_boundary` |
| Medium: recap reuploads deleted frames | Only indexing/ready clips qualify, with active consent. Unkept call-end clears frames. Forget marks clips deleted before discarding references; a recap encoding concurrently with Forget rechecks status before upload. | `recap_never_reuploads_deleted_frames` |
| Medium: HTTP paths lack hello consent | Unset privacy switches use defaults: TwelveLabs off. Rewind binds its own mutable call switches/private flag around flush, poll, search and recap, and checks its on/end state. HTTP off-switch requests cause zero provider work. | `http_recap_flush_search_honor_call_switch` |
| Medium: transient polling failure is terminal | Retry transport failures up to three times after the initial attempt, retaining poll backoff and timeout. Provider failure remains terminal. | `transient_poll_errors_retry_before_failure` |

## Verification

- Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_recall_review.py` - PASS (`11 passed in 0.84s`).
- Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server` - PASS (`864 passed, 2 warnings in 46.35s`).
- Test: `git diff --check` - PASS.
- Final suite output is in [fix-recall-server-tests.txt](fix-recall-server-tests.txt); the local venv path is normalized.
- The first sandboxed server run reported `18 failed, 845 passed, 2 warnings in 47.21s`.
  Fifteen failures were blocked loopback sockets. Two fixtures needed explicit consent, and one exposed
  recent-memory cleanup behavior that was restored in `ws2.py`. The final run enabled loopback sockets;
  fake providers exercised real local WebSocket/HTTP boundaries and the existing real ffmpeg encoder test.
- The two final warnings are short synthetic JWT HMAC keys in existing identity tests.

## Files and limits

Production fixes: `server/rewind.py`, `server/ws2.py`, `server/safety.py`, `server/privacy.py`.
`server/rewind_fake.py` only adds the already-existing real client's `force` parameter to its fake delete method.
Tests: new `server/test_recall_review.py`; updated `server/test_rewind.py`,
`server/test_recall_pipeline.py`, `server/test_recent_memory.py` for explicit consent, fake-client signature,
and deletion expectations. No assertions were weakened to allow cloud work with the switch off.

`server/gemini_live.py`, `server/live_memory.py`, `server/recent_memory.py` were not edited.
No `.env` was read. All media in these tests is synthetic; provider availability and physical sink behavior
remain unverified. Anonymous saved-call search is deliberately restricted to the current call; authenticated
owners retain cross-call lookup. No push or deployment is included.
