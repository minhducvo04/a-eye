# ios/ (Duc)

Built by rereynrd with Claude Code, 2026-10-23.

A camera-first SwiftUI iPhone app for A-eye. It opens straight onto the rear camera. A ring of modes sits at the
bottom; swipe to one and tap the centre to start a call. During the call the app sends camera frames, speaks the
agent's replies, listens to you, and draws the server's boxes, arrows, circles, paths, labels and pins over the live
picture.

## Modes

The ring shows the v2 skill packs plus three placeholders:

| Mode | Pack | Status |
|---|---|---|
| General | `general` | works |
| PC Build | `pc_build` | works; "Power is off" gate before any step |
| Cooking | `cooking` | works |
| Assembly | `assemble` | works |
| Memory | `memory` | works; centred at launch (the memory aid is the product focus, same as the web) |
| Sink | `home` | works; the app sends "sink" as soon as the helper first listens, like the web |
| Mechanic, Engineering | none | "coming soon" (tap shakes, no call) |

## Protocol

The app speaks the v2 contract (`contracts/schema.json`, mirror in `contracts/types.ts`) over `/ws2`. `hello` always
sends `client:"ios"` and `tts:"browser"`, meaning the phone speaks the text itself and the server sends no audio.
`board_id:"demo-b650"` is added for PC Build only. Frames are JPEG, long side at most 640 px, one per second, and
carry no orientation field. Behaviour mirrors `client-web/agent.js` and `draw.js`.

## Layout

```
ios/
  AEyeCore/        pure Swift package, no UIKit: runs `swift test` on a Mac
    Sources/AEyeCore/   message encoders and decoders, call state reducer, draw ops, aspect-fill mapping,
                        mode list, barge-in rules, tuning constants
    Tests/AEyeCoreTests/   tests for tuning, messages, draw state, cover transform, call state, modes, voice rules
  AEye/            the app
    AEye.xcodeproj the Xcode project (open this)
    App/           SwiftUI shell: camera, socket, speech in/out, call controller, views (synchronized folder)
    Config/        AEye.xcconfig, Info.plist, Local.xcconfig.example (Local.xcconfig is git-ignored)
    SETUP.md       first run on a phone and the device checks
```

`AEyeCore` holds everything that can be tested without a phone. `App/` only wires Apple frameworks (AVFoundation,
Speech, URLSessionWebSocketTask) to `CallState.reduce` and renders the result. No third-party packages.

## Test

```sh
swift test --package-path ios/AEyeCore
```

`make test` does not run this (the Makefile is not owned by `ios/`).

## Build and run

Needs Xcode 26 or later and a real iPhone on iOS 17 or later. Open `ios/AEye/AEye.xcodeproj`, pick your team under
Signing & Capabilities, choose the iPhone and Run. Details in [`AEye/SETUP.md`](AEye/SETUP.md).

## Point it at `make dev`

On the Mac run:

```sh
VISION_BACKEND=fake make dev
```

The server refuses any client that is not localhost unless it has credentials. On home Wi-Fi start it open
(`A_EYE_OPEN=1 make server`) and leave the app's token field empty, or set `A_EYE_TOKEN` in `.env` and type the
same value in the app's gear sheet (Access token; it is kept in the Keychain and sent as `?token=`).

Then give the app the Mac's address, either in `ios/AEye/Config/Local.xcconfig`
(`AEYE_SERVER_URL = ws:/$()/192.168.1.10:8000/ws2`) or at runtime in the gear sheet (Settings > server). The phone
and the Mac must be on the same Wi-Fi. Accepted forms: `192.168.1.10:8000` (becomes `ws://.../ws2`),
`http(s)://host` (becomes `ws(s)://host/ws2`), or a full `ws://` URL.

## Privacy

- Frames and audio live in memory only. Nothing is written to disk, Photos or Files, and nothing is logged.
- Speech recognition runs on the iPhone (`requiresOnDeviceRecognition = true`). If the language has no on-device
  model, or mic or speech access is off, the call falls back to a typed field.
- No API keys in the app. Frames go only to our own server.

## Limits

- Portrait, iPhone only.
- The phone speaks with the system voice (`tts:"browser"`); server TTS audio is not played.
- Boxes are drawn where the server put them. There is no tracking between frames, so they can lag a moving object.
- Mechanic and Engineering are placeholders.
- No app icon yet.
- The app is a helper, not a certified or medical tool, and it is not for mains, gas or PSU internals.
- Safari (`client-web/`) stays the committed demo unless native passes the same rehearsal.
