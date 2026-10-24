# RESULT: pkg/visionos

Apple Vision Pro app `visionos/AEyeVision`, copied from the iPhone app in `ios/AEye`. Plan and the camera finding:
[`PLAN.md`](PLAN.md).

## Camera

visionOS gives regular apps no main-camera frames: `CameraFrameProvider` needs the enterprise entitlement
`com.apple.developer.arkit.main-camera-access.allow` and an Apple license file. visionOS 26 only dropped the
immersive-space requirement. `/ws2` keeps one session per socket, so frames cannot come from the phone in the same
session without a server change. The app therefore looks at a photo the user picks (`PhotosPicker`), sent as a
`frame` once a second like the iPhone's camera.

## Files

- `visionos/AEyeVision/AEyeVision.xcodeproj`: visionOS 26 target, bundle id `ai.aeye.vision`, synchronized `App/`
  folder, local package `../../ios/AEyeCore`.
- `Config/`: `AEyeVision.xcconfig` (empty server URL and team), `Local.xcconfig.example`, `Info.plist`.
- `App/Call/`: `SocketClient`, `SpeechIn` (copied as is), `SpeechOut` (plus server voice queue), `CallController`
  (photo source, voice id), `ServerVoice.swift` (server-voice `hello`, `audio` decode, `/api/voices`, PCM player).
- `App/Image/PhotoSource.swift`: the picked photo, upright, long side 640, JPEG 0.7, memory only.
- `App/Views/`: copies of the iPhone views. Changes: visionOS glass, no haptics, hover effects, notice takes the
  photo picker as its button, Settings has a Voice picker.
- `App/DebugHooks.swift`: Debug builds only. Launch arguments to drive a simulator run.
- `ios/AEyeCore/Package.swift`: `.visionOS(.v1)` added to `platforms`. No other change in `ios/`.

## Run in the simulator

```sh
A_EYE_MOCK=1 .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8437
xcodebuild -project visionos/AEyeVision/AEyeVision.xcodeproj -scheme AEyeVision \
  -destination 'platform=visionOS Simulator,name=Apple Vision Pro' CODE_SIGNING_ALLOWED=NO build
xcrun simctl launch booted ai.aeye.vision -serverURL ws://127.0.0.1:8437/ws2 \
  -AEyeDebugPhoto /path/photo.jpg -AEyeDebugTyped YES -AEyeDebugStart general -AEyeDebugSay "what am I looking at"
```

## Limits

- No live camera (see above). The overlay is drawn on the still photo.
- Voice input and playback were not heard: the simulator runs used typed input (`-AEyeDebugTyped`) so the Mac mic
  was never asked for. On-device speech, barge-in and both voices need a headset run.
- Server voice: if the server falls back to the browser voice after `hello` (no Kokoro box and no Cartesia key), the
  app hears no `audio` and stays silent for that call; captions still show. Pick "System voice" then.
- The photo cannot be changed during a call (end the call, pick, start again).
- Mechanic, Plumbing and Engineering are placeholders, as on the iPhone.

## Test

- `swift test --package-path ios/AEyeCore` - PASS (36 tests, 0 failures, exit 0)
- `xcodebuild ... -destination 'platform=visionOS Simulator,id=31FDBAB4-...' CODE_SIGNING_ALLOWED=NO build` - PASS
  (BUILD SUCCEEDED, exit 0)
- Simulator run against a mock server on :8437 - PASS: server log shows `hello` (`pack:general, tts:browser`) and
  `turn_start` .. `turn_done`; a second run shows `hello` (`pack:pc_build, tts:server`). Screenshots in
  `screenshots/`: no photo, ring with photo, General call with box, arrow and caption, PC Build call with the power
  gate.
