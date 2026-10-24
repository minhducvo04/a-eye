# RESULT: pair-vision

Implemented phone pairing in the Vision Pro call UI. Build verification is blocked by the execution sandbox; this work is not yet verified in the simulator.

## Changed files

- `visionos/AEyeVision/App/Call/Pairing.swift`: app-local v2 pair/request/status wire handling, pairing state, expiry and same-server phone link with URL-encoded token from the call socket URL. Unknown JSON fields are ignored.
- `visionos/AEyeVision/App/Views/PairSheet.swift`: large code, selectable phone link, local Core Image QR, countdown and retry. Hides the code and QR after join or expiry.
- `visionos/AEyeVision/App/Call/CallController.swift`: sends pair requests, handles pairing messages before the shared decoder, blocks photo sends while joined (including camera off), resets pairing on disconnect/end. Clears draw state on camera-source changes so independent frame sequence numbers do not suppress new overlays.
- `visionos/AEyeVision/App/Views/CallScreen.swift`: pairing control, status labels and phone overlay mapped to the neutral canvas.
- `visionos/AEyeVision/App/RootView.swift`: replaces the picked photo with a neutral backdrop while joined; restores the photo after leave.
- `visionos/AEyeVision/App/DebugHooks.swift`: contract-example decode assertions, unknown-field tolerance, request payload, token link, QR creation and join/off/leave/expiry checks. Runs on Debug app launch; prints only `PAIRING_DEBUG_CHECKS_PASS` after passing.
- `visionos/RESULT.md`: appended pairing handoff.
- `RESULT.md`: this report.

The project synchronizes the App folder, so no Xcode project edit was needed. No test target exists. No edits to iOS, server, client-web or contracts. Files remain unstaged; no staging attempt, commit, push or publication.

## Limits

- No live preview of the phone frames exists on the headset. Server draw ops appear on a neutral canvas with a small “Phone camera” label. Phone frame dimensions are not in the pairing/draw contract, so normalized coordinates map to that canvas, not to a camera image.
- A selected photo remains in memory and resumes sending after `left`. While joined, even with camera off, no new headset photo frames are sent. A send already submitted before the join notification cannot be recalled.
- The existing photo-picker flow is retained: pick/change before a call; after leave, the previously picked photo is reused. With no photo selected, there is no fallback frame until one is picked.
- Token comes from the configured server URL query (`?token=...`); the app has no separate token setting. The link/QR is displayed intentionally but never logged or sent to a QR service.
- Debug assertions were added but could not be executed. Phone/server integration, QR scanning and visual layout still need a simulator/device run against the parallel server implementation.

## Verification

Test: `xcodebuild -project visionos/AEyeVision/AEyeVision.xcodeproj -scheme AEyeVision -destination 'generic/platform=visionOS Simulator' -derivedDataPath /tmp/a-eye-pair-vision-build CODE_SIGNING_ALLOWED=NO build` - FAIL (exit 74; sandbox blocked SwiftPM caches and CoreSimulator before app compilation).

Exact build result line:
```text
xcodebuild: error: Could not resolve package dependencies:
```
Diagnostic includes `Operation not permitted` for the Clang module cache and SwiftPM manifest diagnostics. Full output: `/tmp/a-eye-pair-vision-build.log`. The required escalation retry returned `Rejected("approval request failed")`; it did not execute. There is no `BUILD SUCCEEDED` result.

Test: `xcrun swiftc -frontend -parse visionos/AEyeVision/App/Call/Pairing.swift visionos/AEyeVision/App/Call/CallController.swift visionos/AEyeVision/App/Views/PairSheet.swift visionos/AEyeVision/App/Views/CallScreen.swift visionos/AEyeVision/App/RootView.swift visionos/AEyeVision/App/DebugHooks.swift` - PASS (exit 0; syntax only, not type checking or runtime verification).

Test: `git diff --check` - PASS (exit 0).

## iPhone app follow-up (not edited)

1. Add camera-only mode in `ios/AEye`: connect to `/ws2` on the same server with the same auth token; send v2 `hello` with required session/pack fields plus `role:"camera"`, `pair_code`, and camera state, then v2 frames. Keep speech and the call UI on Vision Pro.
2. Add code entry or QR scanning. Read the pair code/server/token from the link and use them to connect.
3. Decode `pair_status`: joined confirms pairing, camera updates reflect `camera_on`/`source`, left stops the camera session, rejected/expired returns to entry with a retry. Send the v2 camera message when toggling camera; stop capture/sends when disconnected or off.

Integrator (outside the sandbox): xcodebuild generic/platform=visionOS Simulator CODE_SIGNING_ALLOWED=NO build -> BUILD SUCCEEDED (Pairing.o and PairSheet.o compiled); installed and launched on the Apple Vision Pro simulator (visionOS 26.5): console printed PAIRING_DEBUG_CHECKS_PASS (v2_pair and v2_pair_status decode, QR generated). The sheet was not driven by taps and no live pairing ran against a server from the simulator.
