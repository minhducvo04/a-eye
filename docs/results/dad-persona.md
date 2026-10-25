# Dad persona result — 2026-10-24

Implemented the owner's 2026-10-24 decision: A-Eye is openly an AI dad in **“Dad, how do I?”**, with Sink as the hero task. All changes are uncommitted.

## Delivered

- `server/product_rules.py` permits dad/father persona wording and still detects these words for family venting. The fixed neutral/serious vent replies and existing safety gates remain. Added actual-parent, isolation and romantic claim patterns; existing dependency and generic praise bans remain.
- `server/personas.py` and three JSON files provide Strict, Funny and Chill dad. The validated registry has style-only fields and optional classic/Live voices. `GET /api/personas`, optional `hello.persona`, TS/Swift mirrors, classic/Live prompt blocks and voice selection are wired. Unknown persona IDs reject hello. See [personas.md](../personas.md) for adding a file.
- Web and iPhone Settings discover personas dynamically and persist selection. Native classic turns request server TTS so the choice affects audio; native speech handles absent audio and immediate out-of-turn notices. Echo tracking and interruption stop server playback. Physical playback remains unverified.
- Both rings default to Sink, General and Memory. `ENABLE_EXTRA_MODES=1` reveals the five extra modes without deleting their code. General retains Gemini Live with existing consent/private fallback. `SHOPPING=1` is required for search, generated market requests, v1 market and the REST market endpoint.

## Tests changed and why

These are intentional policy expectation changes from the **owner decision 2026-10-24**, not removal of safety coverage:

| Test files | Change and reason |
|---|---|
| `server/test_product_rules.py` | Removed dad/father from the parametrized banned-role expectations by changing `ROLE_WORDS`; added permitted AI dad/father/style sentences. Added actual-parent, isolation and romantic refusals and explicit dad/father vent cases. Existing streaming/output checks, dependency restrictions and neutral replies remain tested. |
| `server/test_personas.py` (new) | Tests all shipped classic prompt styles, JSON drop-in/invalid fields, registry and feature endpoints, optional hello, real local WS persona/voice selection and unknown-ID rejection, and ignoring model shopping output while disabled. Additional persona files are allowed. |
| `server/test_gemini_live.py` | Existing loopback WebSocket test now also checks the persona style block and selected Live voice in the actual setup envelope. |
| `server/test_shopping.py` | Existing enabled-shopping tests explicitly set `SHOPPING=1`; added default-off refusal with no source or vision call. |
| `server/test_agent.py`, `test_backbone.py`, `test_stream.py`, `test_wiring.py` | Existing tests that expect shopping now explicitly enable it. Their search/compatibility assertions remain. |
| `client-web/turn.test.mjs` | DOM/socket fixture serves registry and flags; expects Sink by default, verifies core versus extra ring visibility, General's Live/opt-out behavior, persona hello and call restart on selection. Replaces expectations for the old separate Live ring entry. |
| Swift `ModesTests`, `CallStateTests`, `ClientMessageTests` | Expect three default modes plus gated extras, address PC explicitly instead of assuming its old index, and verify optional persona/server TTS encoding plus registry decoding. |

Before implementation, the new policy tests produced `6 failed, 66 passed`; the new registry test initially could not import the missing module. The first full-suite attempt exposed old shopping-on assumptions, which were corrected as above.

## Verification

Commands used the sibling checkout's existing Python environment. Tests exchanged synthetic messages through real local HTTP/WebSocket services; no cloud credentials or personal media were used.

| Command | Result | Retained log |
|---|---|---|
| `make test PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` | **FAIL:** `1 failed, 1232 passed, 2 warnings in 62.63s (0:01:02)` | `/private/tmp/dad-persona-full-final.log` |
| `node --test client-web/` | **PASS:** `tests 165`, `pass 165`, `fail 0`, `skipped 0` | `/private/tmp/dad-persona-node-final.log` |
| `swift test --package-path ios/AEyeCore` | **PASS:** `Executed 64 tests, with 0 failures (0 unexpected)` | `/private/tmp/dad-persona-swift.log` |
| `xcodebuild -project ios/AEye/AEye.xcodeproj -scheme AEye -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath /private/tmp/dad-persona-build CODE_SIGNING_ALLOWED=NO build` | **PASS:** `** BUILD SUCCEEDED **` | `/private/tmp/dad-persona-xcode-final.log` |
| `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_personas.py` | **PASS:** `5 passed in 0.97s` after allowing extra drop-in files in test expectations | `/private/tmp/dad-persona-registry-final.log` |
| `git diff --check` | **PASS** | No output |

The sole full-suite failure is `vision/test_gemini.py::test_recorded_payment_failure_is_reported_and_cleared`: missing `vision/fixtures/gemini_payment_required.json`. This is the same missing fixture recorded in [gemini-live.md](gemini-live.md); no vision file was edited, fixture invented, or test skipped. The vision owner needs to restore the original fixture. Make therefore stopped before its web target, which was run separately. Python warnings concern short synthetic JWT keys.

After the completed full run, only the drop-in test expectation, web voice-sample selection, native audio fallback and documentation changed; the affected registry test, complete web suite and simulator build were rerun. No server implementation changed after that full run. Native build warnings include existing speech delegate sendability and deprecated Bluetooth-option warnings.

## Limits and handoff

- A simulator compile is not a physical iPhone audio/camera result. No browser visual run or live Google/TTS provider voice audition was performed. Review selected-voice playback, echo/barge-in and no-server-TTS fallback on a device before demo integration.
- Product wording uses deterministic token/phrase detectors, not a comprehensive semantic classifier. Style is subordinate to existing coded safety gates; no claim that every possible paraphrase is caught. JSON catchphrases must remain trusted, reviewed copy.
- Sink's deterministic steps and safety stops intentionally keep their fixed wording across personas. Existing privacy, consent and cloud-budget controls remain in force.
- Changed areas: server registry/rules/orchestration/API/shopping and tests; contracts schema/types/examples/changelog; web page/controller/tests; Swift core mode/message/registry types and tests; native controller/audio/settings/ring/root; reference socket; this report, `docs/personas.md` and `RESULT.md`.
- No commit, push, merge or deployment was performed.

Test: full Python suite - FAIL (1232 passed; one pre-existing missing fixture). Test: web - PASS (165). Test: Swift - PASS (64). Test: simulator build - PASS.
