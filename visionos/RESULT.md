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

## Pair phone camera (pair-vision)

Added app-local `Call/Pairing.swift` and `Views/PairSheet.swift`, with hooks in CallController, CallScreen, RootView and DebugHooks. The call requests a code, shows a local Core Image QR and token-bearing link, hides the code on join, and shows connected/off/left status. Photo sending pauses throughout the phone join and resumes after leave.

There is no phone frame preview or frame-size metadata: draw ops appear on a neutral canvas labelled “Phone camera”. Existing photo selection remains the fallback. See `../RESULT.md` for changed files, iPhone follow-up and verification details.

Test: `xcodebuild -project visionos/AEyeVision/AEyeVision.xcodeproj -scheme AEyeVision -destination 'generic/platform=visionOS Simulator' -derivedDataPath /tmp/a-eye-pair-vision-build CODE_SIGNING_ALLOWED=NO build` - FAIL (exit 74; sandbox cache/CoreSimulator access blocked before compilation).

Exact result: `xcodebuild: error: Could not resolve package dependencies:`. Escalation retry failed with `Rejected("approval request failed")`. Swift syntax parsing and `git diff --check` pass; debug decode/state/QR checks are added but have not run. No simulator or integration success is claimed for this addition.

## Round 2 (pkg/visionos-2)

Parity with iOS c39cb5d and the web call page, the paired phone as camera + mic, and the memory-aid views.

- Waveform strip, wait card and scan sweep: copied from `ios/AEye` (`ListeningStrip`, `WaitCard`, `ScanSweep`,
  the RMS level patch in `SpeechIn`).
- `EXPERT m.s s` chip while `turn.stage` is `expert`, cleared by its own `expert_done` (web `turn.js`).
- Rewind: bottom-bar button and Settings switch (one state), TwelveLabs upload notice on the first switch-on, Keep
  clips, "Forget this call's clips" (`POST /api/rewind/forget`), "Rewind on" + Recap chip (`POST
  /api/rewind/recap`), Recap sheet at the end of a call that had Rewind on, `rewind_recap` messages.
- Private mode: Settings > Privacy toggle (saved), `hello.private`, server voice, Rewind off and disabled, green
  Private badge in the pill. Speech recognition stays on-device (Apple, `requiresOnDeviceRecognition`).
- Paired phone: the pair sheet closes on join, the headset mic mutes while the phone is camera + mic and comes back
  after, a `cancelled` turn stops the headset's voice.
- Memory aid: `rewind_hit` opens the Then/Now split (earlier frame boxed with its time, live picture with an arrow to
  the matching `track` box; matches `renderSplit` in `client-web/memory.js` on pkg/memory-ui), count chip
  "Remembering N things today" with Forget that / Forget today. They use `/api/memory/*` when it exists and fall back
  to this call's Rewind clips, as the web client does.
- Server voice falls back to the headset's system voice when no `audio` arrives 2 s after the first line.
- Wire additions the shared `AEyeCore` lacks are in `App/Call/CallExtras.swift`; `ios/` is untouched.

### Not possible without a server change: phone video on the headset

`server/pairing.py` stores the phone's frames in the call's session only; nothing is relayed to the call socket, and
`pair_status` carries no frame size. While paired the headset shows a dark canvas with the overlay stretched to it.
To show the live phone picture, the server would need, for example, an additive v2 server message (say
`camera_frame`: `seq`, `w`, `h`, `jpeg_b64`) sent to the call socket at most once a second, or at least `w`/`h` on
`pair_status`. No server or contract file was changed.

### Limits

- Simulator only. No mic was opened (typed input); speech in, both voices and barge-in still need the headset.
- The wait card, EXPERT chip, split view and Recap steps were rendered from injected server messages
  (`-AEyeDebugInject`), because the mock server answers in about 90 ms and has no TwelveLabs.
- The memory routes and the caregiver "place" line wait for pkg/memory-ui and pkg/local-memory to land.

### Test

- `swift test --package-path ios/AEyeCore` - PASS (51 tests, 0 failures, exit 0)
- visionOS simulator build, `CODE_SIGNING_ALLOWED=NO` - PASS (exit 0); device SDK build
  (`-destination generic/platform=visionOS`, unsigned) - PASS (exit 0)
- Simulator against `A_EYE_MOCK=1` on :8447: `hello` with private logged `tts:server stt:server`; Rewind polled
  `/api/rewind/status`; Forget hit `/api/memory/forget` 405 then `/api/rewind/forget` 200; call end hit
  `/api/rewind/recap` 200; a fake phone joined with the on-screen code (`pair_joined`), its `audio_in` made a turn
  (`turn_done`), the headset showed the caption and the draw. Screenshots: `screenshots/round2/`.

## Real headset run (not done; the team runs it while wearing the headset)

Run from the repo root on the Mac, with the headset paired in Xcode (Window > Devices and Simulators) and
Developer Mode on. The team id comes from an environment variable and never goes in a tracked file.

```sh
export AEYE_TEAM=<your 10-character team id>      # Xcode > Settings > Accounts
xcodebuild -project visionos/AEyeVision/AEyeVision.xcodeproj -scheme AEyeVision -configuration Debug \
  -destination 'generic/platform=visionOS' -derivedDataPath build/visionos \
  -allowProvisioningUpdates DEVELOPMENT_TEAM="$AEYE_TEAM" build
xcrun devicectl list devices                      # note the headset's identifier
xcrun devicectl device install app --device <headset-id> build/visionos/Build/Products/Debug-xros/AEyeVision.app
xcrun devicectl device process launch --device <headset-id> ai.aeye.vision -- -serverURL ws://<mac-lan-ip>:8000/ws2
```

If the bundle id `ai.aeye.vision` is taken for that team, add `PRODUCT_BUNDLE_IDENTIFIER=<your.id>` to the build
line and use it in the launch line.
