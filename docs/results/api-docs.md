# api-docs result

Completed the phone-facing reference and reference client without changing backend code or schema.

## Files changed

- `docs/api.md`: lifecycle, all v2 message examples and fields, draw/tracking guide, ordering caveats, error handling, audio/frame formats and bounds, REST specification, cookbook, Swift usage and cited latency results.
- `ios/Reference/AEyeSocket.swift`: 216-line Foundation client; bearer authentication, hello, text/audio/confirmation/interruption sends, guarded UIKit JPEG conversion, Codable response payloads and all eight draw kinds, receive loop and reconnect.
- `contracts/CHANGELOG.md`: v1/v2.0/v2.1/v2.2 inventory and additive freeze rule.
- `docs/check_api_examples.py`: validates every immediately tagged JSON fence with `contracts.validate`; fails on missing/malformed tags or invalid examples without printing payloads.
- `RESULT.md`: this handoff and verification evidence.

## Checks and evidence

Test: .venv/bin/python docs/check_api_examples.py - PASS (21 examples)
Test: swiftc -typecheck ios/Reference/AEyeSocket.swift - PASS (exit 0; macOS, UIKit branch excluded)
Test: swiftc ios/Reference/AEyeSocket.swift /tmp/AEyeDecodeCheck.swift -o /tmp/aeye-decode-check - PASS (exit 0)
Test: /tmp/aeye-decode-check - PASS (8 response fixtures; 8 draw kinds round-trip; unknown fields/types/kinds)

The temporary executable check decoded the checked-in response examples with an extra unknown field, round-tripped every draw kind through Codable, and checked unknown response types/draw kinds. This is a real compile/run, not an iPhone integration test. No application-wide suite was run for this documentation/reference-only package.

## Limits and integration notes

- Token gates, REST routes, mock mode and expanded phone command are documented from the supplied parallel-package specification and marked “(new tonight)”. They are not implemented in this checkout and were not exercised. No tunnel, service, global setting or trust-store change was made.
- No physical-phone, iOS SDK/UIKit, camera resize, live socket/reconnect, mic playback or mock-mode integration test was performed. The Swift helper leaves camera capture, audio conversion/playback, tracking/rendering and shopper UI to the app; it ignores market_results as an unsupported event.
- Current backend can omit a final say marker after early streamed clauses, does not guarantee post-turn listening/idle, and interleaves background track/metrics with speech. These are documented rather than changed.
- Schema samples contain placeholder image/audio data. Cookbook commands replace images with a local synthetic prop image for actual requests.
- Historical latency figures were cited, not remeasured. No new phone performance claim is made.
- Files left unstaged; no commit, push or publication attempted. No git-add sandbox failure occurred because staging was not requested or attempted.
