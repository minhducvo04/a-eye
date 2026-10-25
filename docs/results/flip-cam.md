# Flip camera

Implemented and left uncommitted.

- Web: Flip camera uses the existing v1/v2 controls rows. Visibility requires a phone/tablet browser, coarse pointer or touch support, and at least two enumerated video inputs. Desktop Macs and touch Windows laptops do not qualify.
- Back is the default. The facing choice persists in this device/browser's localStorage with guarded reads/writes. Switching releases and replaces only video tracks, preserves audio and the stream, and does not touch the call transport. Failed switches attempt to restore the previous camera. Late acquisition after call end is discarded.
- Front preview is mirrored with CSS; canvas frame encoding remains unmirrored.
- iOS swaps front/back wide camera inputs on the capture session queue. The existing session and call remain running. Preview mirroring applies to front only; data-output mirroring is explicitly disabled.

## Changed files

- client-web/flip-camera.js, flip-camera.test.mjs
- client-web/agent.html, agent.js, agent.css
- client-web/index.html, call.js
- ios/AEye/App/Camera/CameraService.swift, CameraPreview.swift
- ios/AEye/App/RootView.swift, Views/CallScreen.swift
- docs/results/flip-cam.md, RESULT.md

## Checks

Test: `node --test client-web/` - PASS (164 tests, 164 pass, 0 fail).
Proof: `/private/tmp/flip-cam-node-final.log`.

Test: `swift test --package-path ios/AEyeCore` - PASS.
Summary: `Executed 63 tests, with 0 failures (0 unexpected)`.
Proof: `/private/tmp/flip-cam-swift.log`.

Test: `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /private/tmp/flip-cam-build CODE_SIGNING_ALLOWED=NO build` - PASS.
Summary: `** BUILD SUCCEEDED **`.
Proof: `/private/tmp/flip-cam-xcode.log`.

Test: `git diff --check` - PASS.

New regression tests initially failed because the helper did not exist. Fake-track checks cover video-only replacement, releasing the old camera before requesting the new one, preserving audio, and disposing of a late stream after call end. Visibility cases include Android, iPad desktop UA, desktop Mac, touch Windows laptop, and a single camera.

Initial Swift/Xcode sandbox attempts could not access compiler caches; authorized retries succeeded. The first web run exposed minimal existing test streams without getVideoTracks; preview lookup now tolerates them. The final suite passed.

## Limits

Simulator compilation and core tests do not prove physical camera behavior. No real camera/audio was captured. Device check: flip both ways during a call, verify mic/call continuity, front-only preview mirroring, unmirrored outgoing frames, and persisted web choice after reload.

Browser APIs cannot prove physical device type. The gate uses mobile user-agent detection, including iPadOS's Mac UA plus multitouch. Spoofed user agents cannot be distinguished reliably; unknown mobile UAs fail closed. Enumeration may expose fewer cameras until permission is granted; visibility refreshes after camera startup and device changes.
