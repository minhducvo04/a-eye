# Live default — 2026-10-24

Implemented on web and iOS; changes remain uncommitted. This supersedes the default-selection and opt-in descriptions in gemini-live.md and ios-live.md.

## Behavior

- Both mode rings select Gemini Live at launch. Starting a call still requires the existing user action; launching does not activate the microphone automatically.
- Live and General use the same existing Live bridge, general pack, Google URL consent, and server PCM transport. Google defaults on only when no saved choice exists. Saved false remains false.
- With Google off or Private on, selecting Live or General starts the existing pipeline without Live URL parameters. Private hello and server-side LOCAL_ONLY checks remain intact.
- Changing Google consent ends the affected web call and any active iOS call. Changing Private ends the current call. A fresh call rebuilds microphone/playback transport and rechecks policy. iOS snapshots transport per call so changing consent cannot misroute cleanup.
- Existing server failure handling remains unchanged: initial connection failure announces “Gemini Live is unavailable. I am switching to the normal pipeline.” Subsequent input uses the normal Claude pipeline (subject to existing cloud switches; Private remains local). A dropped Live socket gets one reconnect attempt before the same fallback. No per-input retry or repeated notice was added.

## Other modes and limits

Sink/home guide, Memory, PC Build, Cooking and Assembly retain their own flows and existing speech. The bridge owns conversational audio/text input, tool dispatch and complete provider turns; it exposes no speech-only method to read an already generated specialist answer. Routing those answers through it would require a new lifecycle/synthesis path, so they are left unchanged under the owner's exception. Coming-soon modes remain unavailable.

The web DOM/socket harness verifies the initial selection, General and Live query/hello transport, saved Google opt-out, Private selection, revocation, and existing Sink behavior. Swift core tests cover selection policy, saved preferences, default mode and URL isolation. Existing server tests cover privacy, initial fallback, reconnect/fallback and real loopback transport. No new Google session, physical iPhone playback or browser audio rehearsal was performed. Simulator compilation is build proof only. Tests were updated with the implementation; no fail-before claim is made.

## Verification

Test: `make test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` - FAIL.

```text
1 failed, 1033 passed, 2 warnings in 104.67s (0:01:44)
FAILED vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared
```

The sole remaining failure is the previously reported missing `vision/fixtures/gemini_payment_required.json`; `git ls-tree HEAD vision/fixtures/gemini_payment_required.json` also returns no entry. No substitute fixture or skip was added. Make stops before its web target, so web was run separately. The initial full run also exposed the stale browser URL test; that test is corrected and passes in the final full run. Warnings concern synthetic short JWT keys.

Test: `node --test client-web/` - PASS.

```text
tests 158; pass 158; fail 0; skipped 0; duration_ms 1250.953959
```

Test: `swift test --package-path ios/AEyeCore` - PASS.

```text
Test Suite 'All tests' passed at 2026-10-24 18:23:17.907.
Executed 63 tests, with 0 failures (0 unexpected) in 0.008 (0.012) seconds
```

Build: `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /tmp/aeye-live-default-build CODE_SIGNING_ALLOWED=NO build` - PASS.

```text
** BUILD SUCCEEDED **
```

The first Swift attempt was blocked by nested sandbox creation before compilation. Swift tests and Xcode build subsequently ran with approved access. Existing SpeechOut Sendable/deprecated Bluetooth warnings and the no-AppIntents metadata warning remain.

Test: `git diff --check` - PASS.

Local logs: /tmp/live-default-full-final.log (final full suite), /tmp/live-default-full.log (initial run), /tmp/live-default-node.log, /tmp/live-default-swift.log, /tmp/live-default-xcode.log.

## Changed files

- Web: client-web/agent.js, agent.html, gemini-live.js; gemini-live.test.mjs and turn.test.mjs.
- iOS: App/Call/CallController.swift, App/RootView.swift; AEyeCore GeminiLive.swift and Modes.swift plus their tests; ios/README.md.
- Server test only: server/test_access.py imports the shared client policy and expects Private/opt-out URLs to omit Live parameters.
- Handoff: docs/results/live-default.md and RESULT.md.

No server runtime, frozen contracts, dependencies, secrets, or media files changed. No commit, push, merge or deployment.
