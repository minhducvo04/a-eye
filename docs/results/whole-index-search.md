# Whole-index past-call search

Implemented on `pkg/whole-index`, based on `b88653cf6eebd2909398014223d237774ff6c6dc`.

`Rewind.search_kept` searches saved clip IDs in newest-first batches of 60,
using `asyncio.gather` with at most six batches per index. Completed rows merge
by ascending rank, then descending score; equal keys retain newest-batch order.
Only the best `limit` matching hits are returned. A failed batch cannot discard
successful batches.

One four-second async deadline covers index lookup, all primary searches and
the existing shared-index fallback. At the deadline, pending searches are
cancelled and completed rows are returned. The HTTP client's existing per-call
timeouts are unchanged. HTTP failures log their numeric status in the existing
allowlisted `error` field, without response bodies, URLs or queries. Other batch
errors log only the exception class.

Owner filtering, current-call exclusion, consent/demo checks and the `INDEX_NAME`
fallback condition are unchanged. No contract, dependency or other module changed.

## Verification

Python checks used the requested interpreter with
`PYTHONPATH=.pytest_cache/whole-index/offline:.`. A local audit hook blocked
network connections, DNS, socket binds and `.env` access. All service clients
were fake clients or mock HTTP transports; no live TwelveLabs request was made.

Before the fix, the new 250-ID and 400-ID concurrency regressions and the failed
batch regression failed: **3 failed, 13 deselected in 1.29s**.

Test: `~/Projects/a-eye/.venv/bin/python -m pytest -q server/test_rewind.py server/test_past_calls.py server/test_clip_play.py` - FAIL (**39 passed, 7 failed in 6.18s**; summary read).

All seven added cases passed in that run:

- 250 IDs searched in five concurrent batches, merged and limited globally.
- 400 IDs bounded to six batches containing the newest 360 IDs.
- One HTTP 400 batch preserves older hits and logs status without private text.
- A real four-second wait returns completed hits and cancels the slow batch.
- Empty owner-index results trigger all batches against the shared index.
- Slow index lookup is included in the deadline (accelerated clock budget).
- Fallback shares one deadline and retains its completed hits (accelerated budget).

The seven failing cases also fail with the unchanged HEAD `server/rewind.py`
loaded under its normal module name, excluding only the new tests:
**32 passed, 7 failed, 6 deselected in 2.26s**. No working source was swapped.
Baseline check command:
`PYTHONPATH=.pytest_cache/whole-index/offline:. ~/Projects/a-eye/.venv/bin/python .pytest_cache/whole-index/baseline_check.py`.

Existing failing nodes:

- `server/test_past_calls.py::test_last_call_summary_without_cloud` (all three parameters).
- `server/test_past_calls.py::test_cloud_block_still_allows_local_summary[private]`.
- `server/test_past_calls.py::test_save_snapshots_text_before_cleanup`.
- `server/test_past_calls.py::test_summary_bound_and_legacy_record_fallback`.
- `server/test_clip_play.py::test_past_call_timeout_keeps_existing_still`.

The summary tests disagree with existing recall routing/transcript behavior;
the playback test expects one cancellation where existing fallback causes two.
These assertions and their production paths were left unchanged.

Test: `git diff --check` - PASS.

Retained local logs: `.pytest_cache/whole-index/final.log` and
`.pytest_cache/whole-index/baseline.log` (ignored, not committed).

## Scope and limits

The requested six-batch cap covers all saved IDs up to 360; a larger library
searches only its newest 360 IDs. The shared-index fallback retains its original
condition: it runs only when the primary index returns no rows, and only while
the total deadline has time left. Rank is batch-local; numeric score breaks
rank ties when available. Live provider acceptance and latency remain unverified.

Files changed: `server/rewind.py`, `server/test_past_calls.py`, this report and
`RESULT.md`. Work stayed in this worktree. No `.env` read, network access, push,
merge or deployment. The requested targeted suite is not fully green due to the
seven reproduced baseline failures above.
