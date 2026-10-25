# Team export result — 2026-10-24

Implemented locally and left uncommitted. No data was uploaded, no cloud tables were created, and no real
personal storage was read. The full suite was run; it is not entirely green because the checkout lacks a fixture
used by an unrelated vision test.

## Changed files

- `schemas/export-v1.json`: standalone versioned JSON Schema for seven entities, field descriptions/units/privacy
  classes, strict row allowlists and forbidden payload fields. No live contract changes.
- `scripts/export_data.py`: offline call/date-range selection, explicit metadata snapshot reader, native plaintext
  memory-log adapter, private-call exclusion, text review gate, domain-separated keyed HMAC IDs, validation before
  publishing, seven NDJSON outputs and schema-hash/count manifest. Synthetic `--sample` mode.
- `scripts/test_export_data.py`: nine tests covering schema/sample, privacy/hash boundaries, selection, failure
  atomicity, native memory mapping, duplicate/orphan rejection, schema forbidden fields, key stability, and CLI errors.
- `docs/data-export.md`: source contract, table/index guidance, exact synthetic example rows, SpacetimeDB ingestion
  procedure and privacy/coverage limits.
- `docs/results/team-export.md` and `RESULT.md`: this handoff and required worktree receipt.

## Tests first and real run

Before implementation, `python -m pytest -q scripts/test_export_data.py` failed at collection because the exporter
module did not exist: `1 error in 0.06s`. The initial six tests passed after implementation; three additional
boundary tests were added during review and all nine passed. The schema is checked with Draft 2020-12 and each
exported sample row is validated, including format checks in the exporter.

Python executable used for all runs:
`/Users/minhducvo/Projects/a-eye/.venv/bin/python` (the worktree has no `.venv`).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q scripts/test_export_data.py` - PASS (`9 passed in 0.15s`).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q contracts device server vision voice market eval boxsvc router scripts` - FAIL (`6 failed, 1040 passed, 2 warnings, 4 errors in 40.79s`).
This includes every configured Python test directory plus `scripts/`, which default pytest discovery omits.
Nine failures/errors were local socket binds blocked by sandbox restrictions. One was the missing untracked
`vision/fixtures/gemini_payment_required.json` fixture in
`vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`.
Two warnings concern existing short synthetic JWT test keys.
Full initial output: `/private/tmp/team-export-pytest.log`.

Test: local-loopback retry of the nine sandbox-blocked cases below with loopback access - PASS (`9 passed in 16.83s`).
Output: `/private/tmp/team-export-loopback.log`.

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q device/test_capture.py::test_event_real_http_person_drop_and_no_files device/test_client.py::test_button_turn_reply_audio_then_idle_off device/test_client.py::test_frames_with_a_person_never_leave_the_device device/test_client.py::test_nothing_is_sent_while_off server/test_cloud_meter.py::test_real_websocket_send_boundary server/test_gemini_live.py::test_fake_live_wire_audio_tools_captions_and_revocation server/test_gemini_live.py::test_reconnect_once_then_fallback_and_close server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero scripts/test_ready.py::test_live_pair_request_on_fake_socket
```

Test: `node --test client-web/` - PASS (`tests 153`, `pass 153`, `fail 0`, `skipped 0`).
Output: `/private/tmp/team-export-node.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/export_data.py --sample --output /private/tmp/aeye-team-export-sample` - PASS (exit 0; one valid row in each of seven tables).

Manifest schema SHA-256:
`6894792344828ea95de986d3fd25f10aa514e0ecb325b5d0ff63352c5fe456c9`.
Sample artifacts: `/private/tmp/aeye-team-export-sample/`, including `manifest.json` and all seven `.ndjson` files.
They contain only synthetic metadata. No SpacetimeDB round trip was attempted.

## Limits and next integration work

There is no durable complete call archive in the current app. Export accepts an explicit local metadata snapshot;
the runtime/capture owners must supply that snapshot for non-memory entities. Existing plaintext memory records
can be adapted only with a call catalog containing trustworthy privacy metadata. Encrypted logs fail closed and
require an authorized local metadata-only snapshot. No capture behavior or storage in another package was changed.

Reviewed text and item/place labels remain personal data. Text review is an explicit producer assertion, not
semantic transcript detection. IDs are pseudonyms, not anonymization. Private calls never export. Zero output rows
mean no selected available records, not proof that no events occurred. The teammate still needs authorized import
reducers, private table access rules, and an ingestion verification against this manifest.

The integrator should restore the missing vision fixture from its owner and rerun that case before calling the
full suite green. No fixture was invented and no unrelated package was edited. No commit, merge, push or deployment.
