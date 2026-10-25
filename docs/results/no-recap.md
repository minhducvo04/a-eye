# No end-of-call recap

Implemented on `pkg/no-recap`, locally only; no push, no .env reads, no external service calls.

## Behavior

- Web hang-up no longer requests `/api/rewind/recap`, opens a recap sheet, or renders incoming recap cards. Removed the Recap chip and its dedicated styles. The shared Rewind sheet still serves find answers.
- Only a call ending with Recall on and Remember this call checked shows `Saving this call for Recall, about 30 s`. Existing status-chip/glass styling is reused on the start screen, with no new screen.
- Both clients poll the owner-scoped existing `/api/rewind/status` endpoint. Its new `save_status` field confirms `saved` only after every clip is indexed and the kept-call index is written. The line then becomes `Saved. Your next call can recall this one.`
- Keep processing now waits for live uploads already indexing at hang-up, as well as the last pending clips. It does not call Pegasus. Explicit recap routes/tools remain callable by other callers; unused web recap helpers remain in rewind.js.
- New calls cancel/invalidate the previous status watcher. Empty, failed, or unavailable saves never display success; polling stops after 300 attempts. Recall-off and unkept calls show nothing and do not poll.
- No iPhone recap view or trigger existed in this checkout (searched all ios/). Added the same gated status on its existing StartScreen, preserving call controls and memory settings.

## Limits

- Existing anonymous `local` owners cannot persist a cross-call library. They therefore never receive a misleading saved confirmation. Authentication/owner behavior was not changed.
- This is fake-provider/runtime test and compile evidence, not a live TwelveLabs, browser screenshot, or physical-iPhone verification. Network access was not enabled.
- The app target could not be built here: Xcode package manifest diagnostics require a cache path outside the writable sandbox, and CoreSimulator services were unavailable. No app-target compile success is claimed.

## Checks

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server` - FAIL (1135 passed, 15 failed, 2 warnings, 96.75 s). Fourteen failures explicitly report denied loopback socket binds; the remaining Live hazard test receives an error after Live startup raises PermissionError. No unrelated tests were modified. Log: `/private/tmp/no-recap-server.log`.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_no_recap.py` - PASS (3 passed). This final focused run includes an added parameter after the full run: both already-indexing live clips and final pending clips, plus off/unkept/failed/empty calls. Fake TwelveLabs asserts no analysis. The initial regression run failed because save_status did not exist.

Test: `node --test client-web/*.test.mjs` - PASS (172 passed, 0 failed). Runtime DOM fixtures exercise no automatic request, ignored recap cards, exact saving/saved text, and no status/poll for off or unkept calls. Log: `/private/tmp/no-recap-web.log`.

Test: `swift build --package-path ios/AEyeCore --scratch-path /private/tmp/a-eye-no-recap-swift --disable-sandbox` - PASS (Build complete, 5.69 s). Default SwiftPM nested sandbox failed first; this flag disables only SwiftPM's nested sandbox, not the enclosing workspace restrictions. Log: `/private/tmp/no-recap-swift.log`.

Test: `swiftc -frontend -parse ios/AEye/App/Call/CallController.swift ios/AEye/App/RootView.swift ios/AEye/App/Views/StartScreen.swift` - PASS (syntax only).

Test: `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /private/tmp/a-eye-no-recap-xcode -clonedSourcePackagesDirPath /private/tmp/a-eye-no-recap-packages -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO build` - BLOCKED (package cache permissions; retry with temporary CLANG_MODULE_CACHE_PATH and SWIFTPM_MODULECACHE_OVERRIDE still blocked on manifest diagnostics). Log: `/private/tmp/no-recap-ios.log`.

Test: `git diff --check` - PASS.

## Full server run failures

```
FAILED server/test_bg_context.py::test_live_publishes_context_while_next_build_waits_and_cancels_on_close
FAILED server/test_cloud_meter.py::test_real_websocket_send_boundary - Permis...
FAILED server/test_gemini_live.py::test_fake_live_recent_step_transcripts_and_scene_stay_local
FAILED server/test_gemini_live.py::test_fake_live_wire_audio_tools_captions_and_revocation
FAILED server/test_gemini_live.py::test_reconnect_once_then_fallback_and_close
FAILED server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[False-False]
FAILED server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-False]
FAILED server/test_gemini_live.py::test_reconnect_reuses_latest_resumable_handle[True-True]
FAILED server/test_limits.py::test_live_minutes_stop_idle_connection - Permis...
FAILED server/test_live_prefetch.py::test_slow_tool_does_not_delay_audio - Pe...
FAILED server/test_live_prefetch.py::test_streaming_prefetch_card_cache_and_idle_publication
FAILED server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[False]
FAILED server/test_live_streaming.py::test_fake_live_streams_before_complete_and_stops_mid_reply[True]
FAILED server/test_live_streaming.py::test_ws2_hazard_sends_stop_caption_and_fixed_audio
FAILED server/test_step_check.py::test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero
```

## Files

- `client-web/agent.js`, `agent.html`, `agent.css`: remove recap UI/trigger; show gated save status.
- `client-web/turn.test.mjs`: client runtime regressions.
- `server/rewind.py`, `server/rewind_api.py`: wait for all indexing and expose retention status.
- `server/test_no_recap.py`: fake TwelveLabs regressions.
- `ios/AEye/App/Call/CallController.swift`, `RootView.swift`, `Views/StartScreen.swift`: gated post-call status.
- `docs/results/no-recap.md`, `RESULT.md`: evidence and handoff.
