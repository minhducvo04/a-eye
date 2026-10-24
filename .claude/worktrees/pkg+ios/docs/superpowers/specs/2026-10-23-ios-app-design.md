# A-eye iOS app: design

Date: 2026-10-23. Branch: `worktree-pkg+ios` (from `origin/main`). Folder owner: Duc (`ios/`, AGENTS.md).

## Intent

A native iPhone app that feels like Snapchat: open it and you are already looking through the camera. Instead of
a ring of lenses, the bottom ring holds **helper modes** (the server's v2 "packs"). Swipe to pick one, tap the
centre to start a call, and the AI talks to you, sees what the camera sees and draws on top of the live view.

Why native at all, when Safari already works: zero friction (no URL, no HTTPS/Tailscale setup, no browser chrome,
no "allow camera" every visit) and a camera-first feel the web page can't match. That feel is the point of the
iOS app.

## Goals

1. Cold launch lands on a live rear-camera view with the mode ring. No splash flow, login or home screen.
2. The ring shows the four real packs: General, PC Build, Cooking, Assembly. Swiping changes the selection;
   tapping the centre circle starts a call in that pack.
3. Extra trades the user wants to show (Mechanic, Plumbing, Engineering) appear in the ring as **"coming soon"**:
   visible and swipeable, not callable. (User decision: ship what runs, tease the rest.)
4. In a call: live camera, server `draw` ops rendered over it, the spoken line as a caption, a small presence
   indicator (listening / thinking / speaking, helper vs shopper), mic always on, end-call button.
5. PC Build shows a prominent **Power is off** button until confirmed (server-side safety gate).
6. Market answers (`market_results`) show as a bottom sheet of up to 3 offers with fits / unverified / no.

## Non-goals (this weekend)

- Projects, New build, Project home, Summary and Parts-scan screens from the old `ios/README.md` plan.
- The v1 socket (`/ws`). The app speaks **v2 (`/ws2`) only**.
- Object tracking between frames (`VNTrackObjectRequest`), ARKit, 3D. The web client doesn't track either.
- Server-side TTS audio playback (`tts:"server"`). Stretch only.
- Adding new packs. Mechanic/Plumbing would be new files in `server/packs/` (server owner's call, with their own
  safety rules); not part of this app.
- App Store / TestFlight distribution.

## Anti-goals (fails even if it "works")

- Anything between launch and the camera: onboarding, a picker screen, a spinner that blocks the preview.
- Storing or uploading frames, photos or audio anywhere except the in-memory JPEG sent to our server.
- Any API key in the app. The app only knows a server URL.
- Copy that implies it is safe to work on mains, gas or the inside of a PSU, or that it's a certified tool.
- Replacing the Safari demo before the native app passes the same rehearsal (ios/README.md:10).

## Constraints

- **Contract:** `contracts/schema.json` v2, `additionalProperties:false` everywhere. No contract change is needed.
  Relevant shapes (line numbers are from schema.json on this branch):
  - Client → server: `hello` (:1919) `{v:2, type, session_id, pack, board_id?, client:"ios", tts:"browser"}`;
    `frame` (:1961) `{seq, ts_ms, w, h, jpeg_b64}`, **no `orientation` field**; `user_text` (:2006)
    `{text, final}` (send only `final:true`; `source` is optional, omit it); `barge_in` (:2043)
    `{utterance_id, at_ms}`; `confirm` (:2073) `{what:"power_off", value}`. No upstream audio in v2.
  - Server → client: `draw` (:2108), `draw_op` (:1629), `say` (:2141), `agent_state` (:2217),
    `market_results` (:2245), `error` (:2270), `audio` (:2182, ignored unless the stretch goal lands).
  - Packs (`server/packs/__init__.py`): `general`, `pc_build`, `cooking`, `assemble`. Only `pc_build` requires
    power-off. PC Build sends `board_id:"demo-b650"`.
- **Behaviour parity with `client-web/agent.js`** (the reference client), so the server sees the same traffic:
  - Frames at 1 per second, long side capped at 640 px, JPEG quality 0.7. Skip a frame if the previous send is
    still in flight.
  - Draw semantics (`client-web/draw.js:54-82`): a new `draw` replaces that agent's ops; `clear` wipes that
    agent's ops; drop a `draw` whose `seq` is lower than the last one drawn.
  - Role colours: target `#3DDC97`, info `#9EB6FF`, warn `#FF8A3D`, ok `#4C9AFF`. `circle.r` is a fraction of
    the shorter side. `ttl_ms` 0 or missing means persistent; otherwise fade out at the end.
  - Coordinates are 0..1 of the **sent frame**; map them through the same aspect-fill transform the preview uses.
  - Reconnect 2 s after a socket close.
- **Apple frameworks only.** No third-party packages (CLAUDE.md: no new libraries without a request).
  `AVFoundation` (camera), `Speech` (`SFSpeechRecognizer`, on-device when available), `AVSpeechSynthesizer`
  (speech), `URLSessionWebSocketTask` (socket), SwiftUI + `Canvas` for the overlay.
- **Networking:** the phone reaches the dev server over the LAN (`ws://<mac-ip>:8000/ws2`) or Tailscale
  (`wss://…`). Needs `NSAllowsLocalNetworking`, `NSLocalNetworkUsageDescription`, and camera, microphone and
  speech-recognition usage strings.
- **Tooling:** Xcode 27.1 is installed. The agent sandbox cannot run `xcodebuild` or the simulator, so the
  person driving builds on their own Mac and a real iPhone (the camera doesn't work in the simulator).
- **Tests (AGENTS.md rule 4):** XCTest next to the code. Wiring into `make test` touches the Makefile, which
  isn't `ios/`-owned: ask its owner.
- Finish with `RESULT.md` in the worktree (AGENTS.md rule 5).

## Decided by the user

- Camera-first launch, Snapchat-style ring of modes at the bottom, centre circle starts the call.
- Modes are the server's packs ("sentiment toggle"). Trades without a pack are shown as "coming soon".
- Work happens on its own branch.
- The user builds it with Claude: Claude writes the code, and the user compiles in Xcode and runs it on their own
  iPhone over a cable. So every plan task ends at a point the user can build and look at on the phone. Duc owns
  `ios/` and still needs to be told.

## Screens

1. **Camera (home).** Full-bleed rear preview. Top-left gear opens Settings. Bottom: the ring, with the selected
   mode's name above it ("PC Build · tap to start"). "Coming soon" items are dimmed and say so in that label;
   tapping one does a small shake and nothing else.
2. **Call.** Same preview, ring tucked away. Top: pill with mode name and elapsed time, plus a presence dot
   (helper blue / shopper orange; pulses when speaking, spins when thinking). Overlay canvas for draw ops.
   Caption card for the last `say`. Bottom bar: mic mute, end call (red), and in PC Build only, a large
   **Power is off** button until confirmed. Market sheet slides up on `market_results`.
3. **Settings sheet.** Server URL (text field, saved in `UserDefaults`), connection status. Nothing else.

Ending a call closes the socket, clears overlay and caption, and returns to Camera with the same mode selected.
The camera session keeps running across both screens so there is never a black flash.

## Voice

- **Listening:** `SFSpeechRecognizer` running continuously during a call; interim text shown faintly, each final
  result sent as `user_text {final:true}`.
- **Speaking:** `hello.tts = "browser"`, so the app speaks each `say` itself with `AVSpeechSynthesizer`.
- **Barge-in:** if the user starts talking (a final or ≥2-word interim result that isn't an echo of the line being
  spoken) while the app is speaking, stop the synthesizer and send `barge_in` for that `utterance_id`. Use
  `AVAudioSession` `.playAndRecord` with `.voiceChat` mode for echo cancellation.
- **Stretch:** `tts:"server"` and play 16 kHz PCM16 `audio` chunks through `AVAudioEngine` (Cartesia voice).

## Calls made by Claude (check these)

- **Testable core package.** Contract types, draw-op reducer, aspect-fill transform and the socket state machine
  live in a local Swift package (`ios/AEyeCore`) with XCTest, runnable by `swift test` on a Mac. The app target
  stays thin (camera, speech, views). `RESULT.md` reports the `swift test` result plus a manual device check.
- **On-device speech only.** `requiresOnDeviceRecognition = true`, so mic audio never leaves the phone (privacy
  rules). If on-device recognition or mic permission is unavailable, the call shows a text field and sends typed
  `user_text {final:true}`, matching the web client's typed fallback.
- **Power-off is per connection.** The server forgets `power_off` on every new `hello` (`server/ws2.py:104-121`),
  including the 2 s reconnect. So in PC Build the **Power is off** button reappears after every (re)connect and
  the app never re-sends `confirm` on its own. Button only, no voice match.
- **Server URL.** Settings holds one full URL (`ws://host:8000/ws2` or `wss://…/ws2`). Default comes from an
  untracked build setting (`AEYE_SERVER_URL` in a gitignored `.xcconfig`, with a committed `.example`). If no URL
  is set, the Camera screen shows a "Set server" chip instead of letting a call fail.
- **Build order / cut order.** (1) camera + call loop in General (hello, frames, draw, say, speech in/out);
  (2) mode ring with the four packs; (3) PC Build power-off button; (4) market sheet; (5) "coming soon" items;
  (6) barge-in; (7) server TTS. Anything from (4) down is cut first if time runs short.
- **Mockup.** The reference is the two-phone mockup shown in chat: live camera, glass caption card, green target
  box with a monospace label, white centre ring with smaller dimmed circles either side, step/progress hairlines
  at the top, red end-call button.

## Left to the builder

Project layout inside `ios/` and how the `.xcodeproj` is created; Swift type design for the contract
(Codable structs vs a thin enum); state management; ring animation and haptics; exact visual polish of the
caption, presence dot and market cards (follow the mockup in the brainstorm: dark glass over the camera, white
centre ring); which "coming soon" trades to show and their icons; how errors are surfaced (caption in
warning colour is fine).
