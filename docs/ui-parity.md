# UI parity: iOS app and web call page

The web call page (`client-web/agent.html`, `agent.css`, `agent.js`) follows the native app in `ios/`. Same
modes, words, colours and layout, so an idea tried on one client reads the same on the other. Both speak the v2
contract on `/ws2`; this change touched no protocol.

Screenshots (iOS Simulator, iPhone 17, left; Chromium at 390x844 with a fake camera, right):
`docs/ui-parity/ring-ios-vs-web.png`, `docs/ui-parity/call-ios-vs-web.png`, and desktop
`docs/ui-parity/call-web-desktop.png`.

## Tokens (`Style.swift`, `DrawOp.swift`)

| Token | iOS | Web (`agent.css` `:root`) |
|---|---|---|
| warn | `#FF8A3D` | `--warn` |
| helper | `#8EB6FF` | `--helper` |
| shopper | `#E8943A` | `--shopper` |
| end call | rgb(0.90, 0.22, 0.24) | `--end-call` `#E6383D` |
| draw roles | target `#3DDC97`, info `#9EB6FF`, warn `#FF8A3D`, ok `#4C9AFF` | `draw.js` `ROLE_COLOR` (unchanged), `--role-*` |
| glass | black 0.32 over `.ultraThinMaterial`, 1 px white 0.14 edge | `.glass`: same tint, `backdrop-filter: blur(20px)`, inset 1 px edge |
| radii | caption 20, power button 16, offer card 16, capsules | `--r-caption`, `--r-button`, `--r-card`, 999px pills |
| type | SF Pro, SF Mono for pill, chips, eyebrows | `-apple-system` stack, `ui-monospace` stack; sizes are iOS Large defaults (11/13/15/17/20) |
| market sheet | `#0C1016` | `--sheet-bg` |

## Screens and elements

| iOS | Web | Notes |
|---|---|---|
| `RootView` camera screen: gear top left, ring at bottom | `#picker`: gear top left, `#ring` | iOS shows the live camera behind the ring; the web shows a dark backdrop because the camera starts only from a tap (Safari rule). |
| `ModeRing`: General, PC Build, Cooking, Assembly, Mechanic, Plumbing, Engineering; PC Build centred; centre 78 px with white 5 px ring, neighbours 52/42/34 at 0.8/0.55/0.38; title + "tap to start" / "coming soon"; coming soon shakes | Same list (`MODES` in `agent.js`), scroll-snap 84 px slots, same sizes, opacities, labels and shake; arrow keys move it | Web: tapping a side mode that works starts it at once (mouse has no swipe). iOS only scrolls it to the centre. Haptics are iOS only. |
| "Set server" chip | none | Web always uses the host that served it. |
| `CallScreen` top pill: presence dot · A-eye · mode · m:ss | `.pill`: same order, mono 13 px | |
| "Connecting…" / "Reconnecting…" warn chip | `#link` | Same words. |
| `PresenceDot`: shopper wins; speaking pulses 0.9 s with halo, thinking spins a 70% ring 1 s, listening steady ring, idle empty | `#presence-dot` CSS, `applyAgentState` uses the `CallState.reduce` rule | Accessible label "Helper is thinking" etc. The old web floating orbs (`presence.js`) are no longer drawn. |
| `CaptionCard`: eyebrow A-EYE / SHOPPER, text up to 8 lines, error in warn under it; a new `say` clears the error | `#caption`, `#replies`, `#error` | Web holds the whole current turn (it streams `reply_delta` and sentence `say`s), clamped to 8 lines; iOS shows the last `say`. Screen readers hear "Helper"/"Shopper" before the text. |
| interim line, faint, 2 lines | `#interim` | |
| PC Build "Power is off" button + "Switch the PSU off and unplug it first."; hides after tap; returns after reconnect | `#power-gate` | Same behaviour (hidden after a sent `confirm`, reset on a new socket). |
| typed bar (only when voice input is off) | `#composer` | Web always shows it (keyboard on desktop, noisy hall). Placeholder stays "Type a message" (the smoke test types into it). |
| bottom bar: mic 56 glass (struck through in warn when muted), end call 68 red | `#mic`, `#end-call` same sizes and colours | Web adds camera on/off, hold to talk (also Space) and a settings gear. |
| End call: back to the ring, same mode selected | `endCall()` | Closes the socket without reconnecting, stops camera and mic. |
| `OverlayView` (port of `draw.js`) | `draw.js` | Box labels now use medium mono 15 px with the same dark shadow; label pills medium 15 px. Web adds the object tracker between frames. |
| `MarketSheet`: SHOPPER eyebrow, category title, up to 3 offer cards (title, chip Fits / Does not fit / Unverified, retailer, price + shipping, "View at …" http(s) only), note, "No matching offers." | `#market` bottom sheet | Web also prints the compat reasons under the price when the server sends them. Close button, backdrop or Escape dismisses. |
| `SettingsSheet`: Server, Connection, privacy note | `#settings`: Server (read only), Connection, privacy note | Web only, same sheet: Voice picker (`/api/voices`, Cartesia first when keyed), Test voice (`/api/voice_sample`), Mute, Volume, mic Sensitivity, Recognition (Browser or Whisper), Room noise, Upload photo, Transcript. |
| `PermissionNotice` "Camera access is off" + Open Settings | `#permission` with Try again / Not now | A web page cannot open browser settings. Also used for "Camera needs HTTPS". |
| none | "Tap to start" overlay, pipeline line (Sent, Thinking 1.2 s), `?dev=1` latency HUD | Web only. |

## Messages

| Direction | iOS | Web |
|---|---|---|
| client to server | `hello` (`client:"ios"`, `tts:"browser"`), `frame`, `user_text` (always final, no `source`), `barge_in`, `confirm` | all of those, plus `camera`, `audio_in` (server STT), `hello.stt`, `hello.camera`, `hello.voice` |
| server to client | uses `draw`, `say`, `agent_state`, `market_results`, `error`; ignores the rest | also `turn`, `reply_delta`, `audio`, `track`, `metrics` |

The iOS app sends nothing the web lacks, so nothing new was needed on the web.

Voice: `?tts=browser` forces the browser voice; `?tts=cartesia` means server TTS with the default Cartesia voice
from `/api/voices`, sent as `hello.voice = "cartesia:<id>"`. The picker choice is remembered per browser.
