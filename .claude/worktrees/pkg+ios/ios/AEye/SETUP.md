# Setting up the A-eye Xcode project

The Swift sources are already in `ios/AEye/App/`. The agent could not run Xcode, so these steps are yours.
Xcode 27.1, a real iPhone on iOS 17 or later, and a cable. Run commands from the worktree root.

## 0. Check the core package first

Before opening Xcode:

```sh
swift test --package-path ios/AEyeCore
```

It should pass. If it does not, stop and fix that first; the app builds on it.

If `swift test` says it cannot find XCTest (or "no such module 'XCTest'"), the command line tools are pointing at the
wrong place. Run `sudo xcode-select -s /Applications/Xcode.app` and try again.

## 1. Create the project

1. Xcode > File > New > Project > iOS > App.
2. Product Name `AEye`, Interface SwiftUI, Language Swift, no tests, no Core Data / SwiftData.
   Uncheck "Create Git repository".
3. When Xcode asks where to save, choose **`ios/AEye/`** (the folder that already holds `App/`, `Config/` and this
   file). Do not choose `ios/`. Xcode always makes a folder named after the product inside the location you pick,
   so you end up with:
   - the project: `ios/AEye/AEye/AEye.xcodeproj`
   - the template sources: `ios/AEye/AEye/AEye/` (`AEyeApp.swift`, `ContentView.swift`, `Assets.xcassets`)

   `App/`, `Config/` and this file are not touched; they are siblings of the new `ios/AEye/AEye/` folder.
   If Xcode ever offers to *replace* a folder, cancel: that would delete `App/`, `Config/` and this file.
4. From now on open the project at **`ios/AEye/AEye/AEye.xcodeproj`**.
5. In the project navigator, under the template `AEye` group, delete **only** `AEyeApp.swift` and `ContentView.swift`
   (right-click > Delete > Move to Trash), i.e. `ios/AEye/AEye/AEye/AEyeApp.swift` and
   `ios/AEye/AEye/AEye/ContentView.swift`. The template `AEye` group itself **stays**, with `Assets.xcassets` in it.
6. Add the app sources: File > Add Files to "AEye"..., browse to **`ios/AEye/App`** (a sibling of the project folder)
   and select the `App` folder. Untick "Copy items if needed". If Xcode offers "Create folders" or
   "Create groups", choose **folders** (the blue folder icon, a synchronized folder), so files added to `App/`
   later appear automatically. Make sure the **AEye** target is ticked, then click Add.
7. Confirm `App/AEyeApp.swift` is the only `@main` in the target.

## 2. Target settings (AEye target > General)

- Minimum Deployments: **iOS 17.0**.
- Supported Destinations: **iPhone** only (remove iPad and Mac / Designed for iPad).
- Device Orientation: **Portrait** only (untick Landscape Left / Right and Upside Down).
- Signing & Capabilities: your personal team, bundle id `com.<you>.aeye`, "Automatically manage signing".

The app shows on the iPhone (and in Settings) as **AEye**, the product name. Wherever this guide says
"Settings > AEye", that is the entry to look for.

### First run on the iPhone

Do these once, before the first Run to the device:

1. **Developer Mode**: on the iPhone, Settings > Privacy & Security > Developer Mode > On. The phone restarts;
   confirm "Turn On" when it asks after the restart. (The switch only appears after Xcode has seen the phone once, so
   plug it in and open Xcode first.)
2. **Trust the developer certificate** (needed with a free personal team): after the first install the app will not
   open ("Untrusted Developer"). On the iPhone: Settings > General > VPN & Device Management > your Apple ID under
   Developer App > Trust. Then launch the app again.

## 3. Add the local package

File > Add Package Dependencies... > Add Local... > choose `ios/AEyeCore` (relative to the project, that is
`../../AEyeCore`). Add the `AEyeCore` library to the `AEye` target. Do not edit the package.

## 4. Build Settings (AEye target > Build Settings, "All" and "Combined")

Search each name and set it:

- **Swift Language Version = Swift 5.** The sources are written for Swift 5 language mode; Swift 6 mode will report
  actor-isolation errors.
- **Default Actor Isolation = nonisolated.** Recent Xcode templates default this to MainActor. The camera, socket
  and speech delegates are called off the main thread, and the code is written for `nonisolated` as the default
  (the three delegate classes are also marked `nonisolated` themselves, and the `@MainActor` types say so
  explicitly).
- **Approachable Concurrency = No.** It changes how isolation is inferred for protocol conformances, which is
  not what this code expects.

If the compiler rejects `nonisolated final class` on `CaptureRig`, `SocketClient`, `SynthesizerDelegateProxy` or
`RecognitionPipeline` (in `App/Call/SpeechIn.swift`; that spelling needs Swift 6.1 or later), delete the
`nonisolated` keyword from those four declarations; with the two settings above they are already non-isolated.
Do the same for the `nonisolated` on the two static functions in `SpeechIn` (`authorize` and
`requestSpeechAuthorization`) only if the compiler rejects them.

## 5. Info keys (AEye target > Info tab > Custom iOS Target Properties)

Add these rows with exactly these strings:

| Key | Value |
| --- | --- |
| `NSCameraUsageDescription` (Privacy - Camera Usage Description) | `A-eye looks through the camera to point at parts while you work.` |
| `NSMicrophoneUsageDescription` (Privacy - Microphone Usage Description) | `So you can talk to A-eye hands-free.` |
| `NSSpeechRecognitionUsageDescription` (Privacy - Speech Recognition Usage Description) | `Speech is turned into text on this iPhone.` |
| `NSLocalNetworkUsageDescription` (Privacy - Local Network Usage Description) | `Connects to the A-eye server on your network.` |
| `NSAppTransportSecurity` (App Transport Security Settings) > `NSAllowsLocalNetworking` (Allows Local Networking) | `YES` |
| `AEYE_SERVER_URL` (String) | `$(AEYE_SERVER_URL)` |

The microphone and speech keys are used by voice input (Task 8). Without them the app crashes the first time it
asks for the permission, so add them before the first run.

## 6. The xcconfig

The config files live in `ios/AEye/Config/` (a sibling of the project folder).

1. In Finder or a terminal: copy `ios/AEye/Config/Local.xcconfig.example` to `ios/AEye/Config/Local.xcconfig`.
2. Edit it to your Mac's LAN IP, keeping the `$()` trick:
   `AEYE_SERVER_URL = ws:/$()/192.168.1.10:8000/ws2`
3. **Drag `Local.xcconfig` into the project navigator first** (from Finder, `ios/AEye/Config/Local.xcconfig`).
   Untick "Copy items if needed" and tick **no** target. Without this step it will not show up in the next step.
4. Select the **project** (top of the navigator, not the target) > Info > Configurations. For both **Debug** and
   **Release**, set the `AEye` target row to `Local` (and the project row too, if you like).
5. `Local.xcconfig` is git-ignored (`ios/.gitignore`). Never commit it.

If the xcconfig is missing the app still runs: the server field is just empty and the camera screen shows a
"Set server" chip.

## 7. Task 5 device check (camera and mode ring)

Plug in the iPhone, pick it as the run destination, Run. (Task 5 and Task 6 files are all on disk already, and
`RootView` uses the call layer, so the app is built once with both; you can still do the two checks in order.)

- The app opens straight onto the live **rear camera**, upright in portrait (not rotated or stretched).
- **PC Build is centred** in the ring at launch, with "PC Build" and "tap to start" above it.
- Swiping the ring snaps one item to the centre each time, with a haptic tick. The centre item has the white ring
  and is the largest; neighbours shrink and fade.
- Mechanic, Plumbing and Engineering say "coming soon". Tapping one shakes it and gives a warning haptic.
- Settings > AEye > Camera off, relaunch: the "Camera access is off" notice with an Open Settings button appears,
  not a black screen.

## 8. Task 6 device check (call loop)

On the Mac: `VISION_BACKEND=fake make dev`. Make sure the xcconfig points at that Mac's IP and port.

- At the first connection iOS shows the **Local Network** prompt. Tap **Allow**. If you tapped Don't Allow, turn it
  on in Settings > AEye > Local Network and relaunch.
- Start **General** (swipe to General, tap the centre). Within about 3 seconds there is no error, and the
  server's spoken greeting or answer appears in the caption card and is spoken aloud.
- Stop `make dev`, then start it again: the top shows "Reconnecting...", then returns to normal without
  leaving the call.
- End call (red button) returns to the camera screen with the same mode still selected, and no black flash.
- Gear > clear the server field: the camera screen shows the "Set server" chip, and tapping the centre of the
  ring opens Settings instead of starting a call. The hint under the field shows what URL it will use.

## 9. Task 7 device check (draw overlay and presence)

`VISION_BACKEND=fake make dev`, General mode, point at anything and type or say nothing yet. Expected: when the
server sends a `draw` (the fake scene returns objects, and the fallback turn boxes the first one), a green/blue box
animates in over the camera and lines up with the same region the web page would draw (open
`http://<mac>:8000/agent.html` on the Mac to compare). The presence dot changes as the agent thinks and speaks.

## 10. Task 8 device check (listening, typed fallback, barge-in)

General mode: say "what am I looking at" → it appears as interim text, then a reply is spoken. While it's speaking
say "wait, stop" → speech stops within ~1 s. Let a long reply play in silence → it is **not** cut off by its own
voice. Turn off mic access in Settings › AEye → the call shows the text field and typing works. Airplane mode +
Wi-Fi only (no internet) still transcribes (proves on-device).

## 11. Task 9 device check (PC Build power-off gate and market sheet)

PC Build: before tapping, ask anything → the server answers "Switch the power off and unplug it first…" and the
button is visible. Tap → "Thanks. What are we working on?" and the button hides. Restart `make dev` mid-call → the
button comes back. Ask "find me cheaper RAM that fits" → the shopper speaks and the sheet shows fixture offers with
chips.

## 12. Commit

Task 5 and Task 6 were written together and `RootView` depends on the call layer, so Task 5 does not build alone.
Tasks 7, 8 and 9 add files under `ios/AEye/App/` (`Views/OverlayView.swift`, `Views/PresenceDot.swift`,
`Views/MarketSheet.swift`, `Call/SpeechIn.swift`) and extend `CallController`, `SpeechOut` and `CallScreen`, so the
single combined commit below already covers them: `git add ios/AEye/App` picks up every new and changed file. Commit
once, after all the device checks (sections 7 to 11) pass. Look first, and adjust the paths if Xcode placed anything
differently:

```sh
git status
git add ios/AEye/AEye ios/AEye/App ios/AEye/Config/Local.xcconfig.example ios/AEye/SETUP.md
git add ios/.gitignore ios/README.md ios/AEyeCore docs/superpowers RESULT.md
git status
git commit -m "ios: app shell, camera, mode ring, v2 call loop, draw overlay, voice input, power-off gate, market sheet"
```

`ios/AEye/AEye` is the Xcode project folder (it contains `AEye.xcodeproj` and the template `AEye/` sources with
`Assets.xcassets`). The second `git add` line is the core package (`ios/AEyeCore`), the ignore file, the iOS README,
the spec and plan under `docs/superpowers`, and `RESULT.md`; without it the commit would leave the package the app
depends on out of the repo.

**Do not stage `ios/AEye/Config/Local.xcconfig` or any `xcuserdata/` folder** (the latter lives inside
`ios/AEye/AEye/AEye.xcodeproj/`). Both are ignored by `ios/.gitignore`, so the paths above never include them, but
read the second `git status` and unstage them if they appear (`git restore --staged <path>`). Never use
`git add -A` here.

If you prefer the plan's two commits, make the first one with `git add` for the project folder, `SETUP.md`, the
xcconfig example and the Task 5 files only (`App/AEyeApp.swift`, `App/RootView.swift`, `App/Camera/`,
`App/Views/ModeRing.swift`, `App/Views/PermissionNotice.swift`, `App/Views/Style.swift`), message
`ios: app shell, live camera, mode ring`, then `git add ios/AEye/App` and commit
`ios: v2 socket, frames, captions, spoken replies`.

## Known limits

- The microphone button mutes and unmutes listening. It is inactive (struck-through mic) when the call uses the
  typed field instead, because mic or speech permission is off or this iPhone has no on-device recognition.
- Speech recognition is on-device only. If the language has no on-device model the call uses typed input.

## Full rehearsal

After sections 7 to 11 pass, run the full rehearsal on the phone. It passes when all of these are true:

- cold launch reaches the camera in under 2 s;
- a PC Build call runs end to end: power-off, ask about a part, see a box, ask about price, see the sheet;
- a General call works;
- one Wi-Fi drop recovers;
- nothing is saved to Photos or Files.

The pass criteria and the known limits are in [`RESULT.md`](../../RESULT.md) at the worktree root. After you have
run `swift test --package-path ios/AEyeCore` and the rehearsal, update its two status lines: replace `NOT RUN`
in `Test: swift test ...` with `PASS/FAIL (<n> tests)`, and in `Device rehearsal - ...` with `PASS/FAIL (<notes>)`.
The integrator reads those lines before merging.
