# ui-hearing

The call page shows when it is hearing, and the reply can be heard.

- A level ring swells around the helper orb while the mic is on, and a small waveform sits by the mic button. Browser speech recognition uses a separate mic stream for the meter. Server speech recognition reuses the capture that is already open. Both stop when listening stops.
- Interim words type out in a bottom caption with a caret, then the final line replaces them and fades after 2 seconds.
- The label by the orb reads Listening…, Thinking…, Speaking…, or Tap the mic to talk. While the user is talking, Listening… wins over the agent state.
- Mic denial, a missing speech API, and a non-HTTPS page each show a message. A missing speech API switches to server recognition and sends a new hello on the same socket.
- Tap to start resumes audio, primes speech synthesis, and starts the mic. Mute, volume, and Test voice sit at the bottom. Mute and volume are stored in localStorage and applied to browser speech and to server audio gain.
- Reply lines stream as they arrive, highlighted while spoken, with Helper in cool blue and Shopper in amber. The transcript drawer keeps the latest 50 lines.
- If server audio does not arrive within 1.5 seconds of a sentence, or playback errors, that sentence is spoken by the browser and the page says the server voice is unavailable.

## Files

- `client-web/ui.js`
- `client-web/ui.test.mjs`
- `client-web/agent.html`
- `client-web/agent.js`
- `client-web/agent.css`
- `client-web/voice.js`
- `client-web/presence.js`
- `client-web/presence.test.mjs`

## Limits

No real microphone, Safari, or iPhone was tested. Headless Chrome could not start in this sandbox, so the 375 px layout was not measured in a browser.

Test voice speaks with the browser voice, including when `tts=server`. Kokoro audio only arrives as `v2_audio` during a reply, so the button cannot play a server clip before one exists. Live replies still use that audio, and fall back to the browser voice if it is late or fails.

Server speech recognition does not echo interim words, so the live caption follows browser recognition only.

Test: node --test client-web/ - PASS (60 pass, 0 fail)
