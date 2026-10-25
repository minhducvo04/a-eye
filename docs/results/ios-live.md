# iOS Gemini Live

Implemented and left uncommitted. Simulator compilation and the Swift core suite pass. Real Google sessions and physical iPhone microphone/speaker playback are not verified.

## Behavior

- Settings adds the off-by-default **Gemini Live (Google)** consent switch and **Private mode**, with a disclosure that microphone audio and downscaled camera video go through the server to Google.
- The existing mode ring adds **Gemini Live** (`gemini-live`) at the end, matching web order. Memory stays selected at launch. Selecting Live without consent, or with Private mode on, opens Settings without connecting. The controller independently rejects that start.
- Live connects with `mode=gemini-live&google=1`, preserving token/owner query parameters. Reserved mode/Google parameters are rebuilt for each call, so a manually entered server URL cannot enable Live for a normal mode. Hello uses `pack:"general"`, `tts:"server"`, `stt:"server"`, `client:"ios"`. Private normal calls include `private:true`.
- Changing Google consent ends an active Live call; changing Private mode ends any active call. The next call rechecks settings. Server `LOCAL_ONLY=1` enforcement remains server-owned.
- The separate `LiveAudio.swift` component converts microphone input to mono 16 kHz PCM16, sends existing `audio_in` messages, and queues existing server `audio` messages for in-memory playback. It enables voice processing, detects utterance ends after 0.7 seconds of silence, and caps utterances at 15 seconds for normal-pipeline fallback. Idle silence is not transmitted. One microphone send is in flight at a time; under backpressure samples are dropped rather than buffered indefinitely, while an utterance-final marker is retained.
- Live requests microphone permission without requesting Speech permission. Denied/failed microphone access falls back to typed input. Audio setup completes before connecting, so a permission prompt cannot discard the first server reply. Normal calls still use on-device recognition and system speech; no audio preference is overwritten by Live.
- `say` updates the existing caption without duplicate system speech. `turn.text` feeds the existing listening strip. PCM is validated as mono 16 kHz, even-length base64 data; playback completion waits for the final chunk and the actual played-back callback. The playback queue is capped at 60 seconds. Interruption/listening and cancelled events, disconnect, and call end clear queued audio.
- Mic mute removes the input tap. Camera off sends `camera{on:false}` to clear the server frame and stops sending frames. Live JPEGs are capped at 320 pixels on the long side, at the existing one-second cadence. Capture buffers older than 1.5 seconds are rejected. No raw media or credentials are logged or written to disk.
- The existing ring, Settings form, waveform, captions, camera preview and call controls are reused. No server, contract or dependency changes.

## Changed files

New:
- `ios/AEye/App/Call/LiveAudio.swift`: native PCM capture, conversion and playback.
- `ios/AEyeCore/Sources/AEyeCore/GeminiLive.swift`: consent-safe URL configuration, PCM decoding/encoding, transcript extraction and utterance gate.
- `ios/AEyeCore/Tests/AEyeCoreTests/GeminiLiveTests.swift`: consent refusal plus allowed control, query preservation/isolation, transport payloads, invalid sample rate, captions, silence and utterance boundaries.

Updated:
- `ios/AEye/App/Call/CallController.swift`: per-call transport selection and lifecycle.
- `ios/AEye/App/Camera/CameraService.swift`: freshness and configurable frame size using the existing sizing function.
- `ios/AEye/App/RootView.swift`: consent-gated selection, including autostart.
- `ios/AEye/App/Views/{SettingsSheet,CallScreen,ListeningStrip}.swift`: consent controls and shared transport presentation.
- `ios/AEyeCore/Sources/AEyeCore/{ClientMessage,ServerMessage,CallState,Modes}.swift`: hello options, audio dispatch, reducer handling and mode entry.
- `ios/AEyeCore/Tests/AEyeCoreTests/{ModesTests,ServerMessageTests}.swift`: updated ring expectations and invalid-audio rejection (valid audio is now decoded).
- `ios/README.md`, `docs/results/ios-live.md`, `RESULT.md`: usage and handoff.

## Verification

Test: `swift test --package-path ios/AEyeCore` - PASS.

```text
Test Suite 'All tests' passed at 2026-10-24 16:54:26.909.
Executed 62 tests, with 0 failures (0 unexpected) in 0.008 (0.013) seconds
```

Build: `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /tmp/aeye-ios-live-build CODE_SIGNING_ALLOWED=NO build` - PASS.

```text
** BUILD SUCCEEDED **
```

Test: `git diff --check` - PASS (no output).

Local compiler/test proof: `/tmp/ios-live-build.log` and `/tmp/ios-live-tests.log`. The initial pre-implementation targeted test attempt was blocked by SwiftPM's nested sandbox before compilation (`/tmp/ios-live-before.log`); it is not a failing-regression claim. Tests and builds then ran with approved Xcode/SwiftPM access. The first executable suite run had one obsolete assertion that valid server audio must be ignored; it was updated to reject malformed audio, with positive PCM decoding covered by the new tests. The final suite passes. Existing `SpeechOut.swift` Sendable/deprecated-Bluetooth warnings and the no-AppIntents metadata warning were observed in the initial build; no new LiveAudio compiler warnings were reported.

## Limits and next checks

The required build is a real simulator compile, not a simulator audio rehearsal or physical-device proof. Core tests exercise wire/configuration decisions, not AVFoundation hardware, UI interaction, acoustic echo cancellation, or provider latency. No Google API call, personal microphone capture, or camera-media probe was performed.

Rehearse on a physical iPhone with an authorized/configured server: blocked consent and Private mode, typed/mic calls, server fallback, speaker echo, mute/unmute, camera off/on, barge-in, consent revocation, reconnect, and returning to a normal mode. An audio-engine route failure switches to typing and asks for a call restart to restore capture. The existing server owns provider discovery, reconnect/fallback, safety buffering and `LOCAL_ONLY` checks.

No commit, push, merge or deployment was performed.
