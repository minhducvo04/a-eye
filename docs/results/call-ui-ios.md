# iPhone dad-call UI — 2026-10-24

Updated the inherited, unfinished iOS UI changes for the revised owner spec. All changes remain uncommitted.

## Behavior

- Start screen: one visible **Call** button, serif “Dad,” slogan treatment, blue radial background, exact security line. No introduction paragraph or mode selector.
- Call always enters the general pack via `Modes.dad`, using the existing Gemini Live default and server-owned Claude fallback. Existing saved Google opt-out and Private mode remain respected. No Sink, General, Memory or Gemini entry buttons; specialist mode/guide code remains compiled.
- Call bar: camera, mic, red End Call, then a separate far-right Rewind/bookmark group. No phone-camera/flip button. Rewind explains silent TwelveLabs capture for this call; **Remember this call** chooses retention after hangup. Stopping Rewind capture preserves a prior retention choice, which can still be revoked. Both choices reset on a new connection/call.
- Removed the memory-aid mode and its controls from the UI. The owner-mandated security line still contains “memory aid” verbatim. The inherited unused `MemorySettings` model and `ModeRing` view remain as unexposed code.
- Clean Settings: Dad, Hold to talk, privacy/Google-sharing consent, server and access token. No Cartesia or voice/model picker.
- Completed the missing controller wiring: hold-to-talk begins muted, releases/cancels to mute, camera off/end stops capture, and a late camera permission answer cannot restart stopped capture. End Call remains visible with denied capture permissions.

## Verification

The initial real simulator build reproduced the unfinished view failure (`MemoryPanel` missing). Completed implementation compiles. Visual inspection caught and corrected an oversized decorative background expanding the start-screen content.

Test: `swift test --package-path ios/AEyeCore` - PASS (67 tests, 0 failures).
Test: `node --test client-web/` - PASS (165 tests, 0 failures, 0 skipped).
Test: `$HOME/Projects/a-eye/.venv/bin/python -m pytest -q` - FAIL (1232 passed, 1 failed, 2 warnings).
Build: `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /private/tmp/aeye-call-ui-build CODE_SIGNING_ALLOWED=NO build` - PASS (`** BUILD SUCCEEDED **`).
Test: `git diff --check` - PASS.

Python's sole final failure is the previously documented `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: missing `vision/fixtures/gemini_payment_required.json`. The first sandboxed attempt also blocked localhost sockets; the final run had local test access and cleared those failures. Direct pytest plus node run the Makefile's two test targets without loading `.env`.

New core regressions cover the dad default without an automatic Sink trigger, Live/Private selection, Rewind acknowledgement/refusal, retention transport and preservation when capture stops. No broad suites were rerun after the final iOS-only changes; Swift and simulator build were rerun.

Screenshots (actual iPhone 17 / iOS 26.5 simulator, visually inspected):
- `docs/results/call-ui-ios/start.png`
- `docs/results/call-ui-ios/call.png`

Call capture uses a loopback-only synthetic WebSocket fixture. Microphone and camera permissions were denied. It rendered the synthetic greeting and verified the actual handshake: `mode=gemini-live`, `google=1`, `pack=general`, `stt=server`. No personal media was captured and no provider was called. These screenshots prove layout and the denied-permission call state, not live AI conversation or physical-device operation.

## Limits

- The existing server owns provider fallback and conversational guide routing. Source inspection shows active Live inputs go straight to Gemini; this iOS-only change does not establish that “how do I fix my sink” starts the deterministic Sink guide. Existing Sink code remains intact. That integration needs the server owner's rehearsal/follow-through.
- Real microphone hold/release, audio echo cancellation, camera hardware, Rewind/TwelveLabs saving/deletion and provider fallback were not exercised on a physical phone. Rewind controls are core-tested; native taps could not be automated because the desktop tool could not access Simulator.
- The existing `rewind_state` acknowledgement omits `keep`; retention UI reflects the requested keep value after that command's acknowledgement, not a read-back of durable cloud storage.
- Existing speech sendability/deprecated Bluetooth warnings appeared on the initial compile; the final incremental build only reports skipped AppIntents metadata extraction.

## Files

App: `RootView.swift`, `Views/StartScreen.swift`, `Views/CallScreen.swift`, `Views/SettingsSheet.swift`, `Views/CallMemorySheet.swift`, `Call/CallController.swift`, `Call/LiveAudio.swift`, `Camera/CameraService.swift`.
Core: inherited `ClientMessage.swift`, `GeminiLive.swift`, `MemorySettings.swift`; added `RewindControls.swift`; updated `Modes.swift`, `ClientMessageTests.swift`, `ModesTests.swift`; added `RewindControlsTests.swift`.
Handoff: this note, `RESULT.md`, two screenshots.

Evidence logs: `/private/tmp/aeye-call-ui-{before,build,swift,python,web,fixture}.log`. The fixture script is `/private/tmp/aeye-call-ui-fixture.py`. No server, contract, dependency or secret files changed. No commit, push, merge or deployment.
