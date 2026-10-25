# Publication scrub

Changes are uncommitted. No history was rewritten, no remote changed and nothing was published.

Removed personal names, author handles, home paths, a GPU tailnet address and machine/user names, personal
domain references, Apple signing identity and bundle namespace. Runtime local services now default to
loopback and remain environment-configurable. Scripts require explicit local service/path configuration and
fail before performing work when it is missing. The held-out team dataset filename is now generic.

Added `scripts/check_public.py`, `scripts/export_public.py`, `scripts/test_public.py` and
`docs/public-export.md`. Python's default suite now includes the scripts directory. The exporter copies
working-tree bytes of tracked files, excludes private/history/data/media content, rejects symlinks and
unreviewed binaries, checks the Git-free staging tree, and exposes output only after a successful check.

## Verification

- Test: `python3 scripts/check_public.py` - PASS (`625 files, 0 hits, 108 binary files without visual inspection`). Binary files are excluded by export, not certified safe by this scan.
- Test: `python3 scripts/export_public.py /private/tmp/aeye-public-scrub-release-20261024` - PASS (`422 files`; exported tree: `0 hits`, `0 binary files`). This is a local review artifact only.
- Test: `make test PY=$HOME/Projects/a-eye/.venv/bin/python` with localhost access - FAIL (`1 failed, 1075 passed, 2 warnings in 57.15s`). Sole failure: `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`, missing `vision/fixtures/gemini_payment_required.json`. `git cat-file -e HEAD:vision/fixtures/gemini_payment_required.json` confirms the fixture is absent from HEAD. No fixture was fabricated and no test was skipped. The two warnings concern short synthetic JWT keys. Log: `/private/tmp/scrub-full-localhost.log`.
- The initial sandboxed full run had `6 failed, 1064 passed, 2 warnings, 4 errors in 41.13s`; all extra failures/errors were localhost socket restrictions and disappeared in the permitted run. Log: `/private/tmp/scrub-full.log`.
- Test: `node --test client-web/` - PASS (`158 tests, 158 pass, 0 fail`). Run separately because Make stops at the Python failure. Log: `/private/tmp/scrub-node.log`.
- Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q scripts/test_public.py eval/backends/test_backends.py eval/brain/test_brain_eval.py` - PASS (`24 passed in 0.67s`). This final targeted run covers the CLI refinement made after the full run: require endpoints only for selected network backends, preserve offline table generation. Includes positive/negative scanner and exporter controls, tracked modifications, exclusions, no Git history, symlink/binary rejection, failure cleanup, existing-output refusal and guard self-scan.
- Test: `bash -n scripts/night_box.sh` - PASS. Real unset-environment invocations of the shell script and vision benchmark exited 1 with clear configuration errors before doing work.
- Test: `git diff --check` - PASS. `git diff --cached --stat` is empty. New files are intent-to-add only so scans/exports include them; all content changes remain unstaged and uncommitted.

## Limits

- Original tracked screenshots/media remain private and were not visually inspected. All are excluded from
  the public export. The text scanner is not a guarantee that arbitrary names or identities in prose have
  been recognized; known inventory patterns are enforced in code.
- Reserved synthetic identities and exact cloud-meter boundary fixtures remain. The standard tailnet CIDR
  remains because changing it would weaken privacy enforcement.
- Data-free exports omit board and evaluation/training fixtures and private documentation/results; workflows
  requiring those files need local data. Some links to excluded historical notes will not resolve.
- PowerShell/Windows and physical-device execution were not available. Bash syntax and real missing-setting
  refusals were checked. No remote machine, model provider, credential or real media was used.
- Generic Apple bundle/keychain identifiers require local provisioning and re-entry of previously saved tokens.
- Only export into a fresh repository; never push this private repository's existing history.

## Replaced or reconfigured tracked files

- `.env.example`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md`
- `boxsvc/README.md`
- `boxsvc/run_box.ps1`
- `device/aeye-device.service`
- `docs/api.md`
- `docs/build-credits.md`
- `docs/device.md`
- `docs/devpost-draft.md`
- `docs/model-choices.md`
- `docs/pc-benchmarks.md`
- `docs/privacy.md`
- `docs/results/auth-fixes.md`
- `docs/results/client-live.md`
- `docs/results/client-stt.md`
- `docs/results/client-voice.md`
- `docs/results/client-web.md`
- `docs/results/dad-flow.md`
- `docs/results/device-picker.md`
- `docs/results/eval.md`
- `docs/results/family-note.md`
- `docs/results/finetune-plan.md`
- `docs/results/gemini-live.md`
- `docs/results/gemini-vision.md`
- `docs/results/grow.md`
- `docs/results/headset-web.md`
- `docs/results/home-fix.md`
- `docs/results/live-default.md`
- `docs/results/local-brain.md`
- `docs/results/memory-gemini.md`
- `docs/results/model-tiers.md`
- `docs/results/pointer.md`
- `docs/results/private-capture.md`
- `docs/results/proof-wall.md`
- `docs/results/ready.md`
- `docs/results/recent-memory.md`
- `docs/results/router-train.md`
- `docs/results/shopping.md`
- `docs/results/step-check.md`
- `docs/results/team-export.md`
- `docs/results/trigger-door.md`
- `docs/results/wave6-turn-latency.md`
- `docs/ui-polish/art-direction.md`
- `docs/voice-options.md`
- `eval/backends/run.py`
- `eval/brain/distill.py`
- `eval/brain/run.py`
- `eval/brain/vision_watch.py`
- `ios/AEye/AEye.xcodeproj/project.pbxproj`
- `ios/AEye/App/Call/TokenStore.swift`
- `ios/AEye/Config/AEye.xcconfig`
- `ios/AEye/SETUP.md`
- `ios/AEyeCore/Tests/AEyeCoreTests/TuningTests.swift`
- `ios/README.md`
- `pyproject.toml`
- `router/data.py`
- `router/embed.py`
- `scripts/night_box.sh`
- `scripts/night_restore.ps1`
- `server/api.py`
- `server/box_client.py`
- `server/brain_local.py`
- `server/expert.py`
- `server/llm.py`
- `server/safety.py`
- `server/step_check.py`
- `server/test_access.py`
- `server/test_auth_fixes.py`
- `server/test_rt.py`
- `server/ws2.py`
- `vision/README.md`
- `vision/ollama.py`
- `visionos/AEyeVision/Config/Local.xcconfig.example`
- `visionos/PLAN.md`
- `visionos/RESULT.md`
- `voice/noise_bench.py`
- `voice/voice_pick.py`
- `router/data/heldout_team.jsonl` (renamed from the identifying filename; references updated).
- `RESULT.md` (links this receipt).
