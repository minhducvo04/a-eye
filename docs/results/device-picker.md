# Device picker (web): choose the mic, camera and speaker, and see which mic is live

the team could not tell which microphone the page was listening to. The web call page now shows it and lets him pick.

## What changed (client-web only)

- `devices.js` (new): pure helpers for the lists, the choice and the fallback (`deviceOptions`, `chooseDevice`,
  `devicesLocked`, `audioConstraints`, `videoConstraints`, `loadChoice`/`saveChoice` in try/catch, `micLine`,
  `sinkSupported`) and a small level preview for the Settings meter.
- Settings > Devices: Microphone, Level bar, Camera, Speaker (only where `AudioContext.setSinkId` exists: Chrome,
  Brave). Before permission the lists hold only "Default" and an "Allow access to see devices" button asks once.
  Choices are kept in `localStorage` (`aeye.mic`, `aeye.camera`, `aeye.speaker`).
- Call screen: a line under the pipeline ("Hearing ...") reads `Mic: <label of the live track>`, or `Mic off · <label>`.
- Mic: `getUserMedia({audio: {...MIC_CONSTRAINTS, deviceId: {exact}}})`, noise settings kept. `voice.setMicDevice(id)`
  restarts only the capture (old tracks stopped). `voice.micLabel()` reads the live track label.
- Browser speech recognition always hears the system default mic, so a chosen mic switches recognition to Whisper
  (server STT); picking Default again switches back. The Settings footnote says so.
- Camera: `deviceId` when chosen, else `facingMode: "environment"`. Switching while live opens the new track, then
  stops the old one; the call and frames keep going. `startCamera`'s camera-off fix is untouched.
- Speaker: `voice.setSinkId(id)` routes server voice (AudioContext). The browser voice (speechSynthesis) can't be routed.
- `devicechange` (AirPods in or out) refreshes the lists. A chosen device that disappears, or fails with
  OverconstrainedError/NotFoundError, falls back to the default with a notice ("Chosen mic is gone. Using the default mic.").

## Limits

- Browser recognition can't use a chosen mic (the Web Speech API has no device option), hence the Whisper switch.
- The meter in Settings shows the call mic while listening, otherwise a preview of the chosen mic while the sheet is open.
- Fallback on unplug was checked in Chromium by hiding the device from `enumerateDevices` and firing `devicechange`,
  not with real AirPods.

Test: node --test client-web/ - PASS (88 tests, 0 fail)
Test: make browser-smoke URL=http://127.0.0.1:8023 - PASS (BROWSER SMOKE PASS, frames_sent 2, no problems)
Test: Chromium with fake devices - PASS (lists show Fake Audio Input 1 and 2, fake_device_0; "Mic: Fake Audio Input 2"
after picking it, STT Whisper; unplug notice, back to default and Browser; camera swap stops the old track; locked
state shows "Allow access to see devices" and the lists fill after the tap; no console errors)
