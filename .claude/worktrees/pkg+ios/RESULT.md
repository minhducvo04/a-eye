# RESULT: ios (native iPhone app)

Branch: `worktree-pkg+ios`. A camera-first SwiftUI app: mode ring of v2 packs, `/ws2` call loop with
`client:"ios"` and `tts:"browser"`, draw overlay, on-device voice input, PC Build power-off gate and market sheet.

## Files changed

- `ios/`
  - `.gitignore`, `README.md` (rewritten)
  - `AEyeCore/`: `Package.swift`; `Sources/AEyeCore/` (`Tuning`, `ClientMessage`, `ServerMessage`, `Market`,
    `DrawOp`, `DrawState`, `CoverTransform`, `CallState`, `Modes`, `VoiceRules`); `Tests/AEyeCoreTests/` (`Tuning`,
    `ClientMessage`, `ServerMessage`, `DrawState`, `CoverTransform`, `CallState`, `Modes`, `VoiceRules` `Tests.swift`)
  - `AEye/SETUP.md`, `AEye/Config/Local.xcconfig.example`
  - `AEye/App/`: `AEyeApp.swift`, `RootView.swift`; `Camera/` (`CameraService`, `CameraPreview`); `Call/`
    (`SocketClient`, `CallController`, `SpeechOut`, `SpeechIn`); `Views/` (`ModeRing`, `CallScreen`,
    `OverlayView`, `CaptionCard`, `PresenceDot`, `MarketSheet`, `SettingsSheet`, `PermissionNotice`, `Style`)
  - the Xcode project (`ios/AEye/AEye/AEye.xcodeproj`) does not exist yet; the user creates it per SETUP.md
- `docs/superpowers/`: `specs/2026-10-23-ios-app-design.md`, `plans/2026-10-23-ios-app.md`
- `RESULT.md` (this file)

## Limits

- No server TTS: the phone speaks the text (`tts:"browser"`); `audio` messages are ignored.
- No tracking between frames: boxes stay where the server drew them until the next `draw` or fade.
- Mechanic, Plumbing and Engineering are "coming soon" (no pack).
- `make test` is not wired for Swift (the Makefile is not owned by `ios/`). Run the package tests directly.
- The branch is named `worktree-pkg+ios`. Rename it before merging: `git branch -m pkg/ios`.
- The code was never compiled by the agent. The sandbox blocked git, swift, xcrun and xcodebuild, so expect to fix
  small compile errors on the first build.

## Status

Test: swift test --package-path ios/AEyeCore - NOT RUN (sandbox blocked swift; run it first)

Device rehearsal - NOT RUN (see ios/AEye/SETUP.md)

## Rehearsal pass criteria

It counts as passed when all of these are true:

- cold launch reaches the camera in under 2 s;
- a PC Build call runs end to end: power-off, ask about a part, see a box, ask about price, see the sheet;
- a General call works;
- one Wi-Fi drop recovers;
- nothing is saved to Photos or Files.
