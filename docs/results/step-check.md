# Valve step checker

Implemented in the working tree for lead review; no commit. **Real-photo accuracy and the home-box model run are not verified.** Runtime remains fail-closed until an operator selects a qualifying real evaluation report. Synthetic results cannot enable it.

## Behavior and API

- `server/step_check.py`: `await Checker(method, threshold).check(frame_bytes, closed_reference=None, open_reference=None, captured_at=monotonic_time)` returns `Verdict(state, confidence)`, where state is `closed`, `open` or `unsure`. Confidence is a model score, not a calibrated probability. The default threshold is 0.95; configuration cannot lower it below 0.9.
- `POST /api/step-check`: JSON `{image_b64, closed_reference_b64?, open_reference_b64?}` returns `{state, confidence}`. Invalid input, unavailable configuration, provider errors and timeouts return `unsure, 0.0`. The HTTP inspection endpoint cannot unlock a session. It uses the existing `/api` authentication and `Cache-Control: no-store`.
- `server/agent.py`: on every gated home turn, clear the previous pass, run the checker on the current camera frame, and consume a confident closed result synchronously through the existing `HomeGuide` gate. Open, unsure and errors say **“Show me the valve again, closer.”** A pass is cleared immediately after consumption. Hazards run first; cancellation cannot leave a reusable pass.
- The 1.5-second frame-age limit is checked before and after inference. An answer that arrives after that limit cannot pass, even if its score is high. The provider/HTTP deadline is eight seconds. Missing frames and camera-off fail closed.
- `client-web/step-check.js`, `agent.html`, `agent.js`: one card shows “Checking the valve...”, then “Water is off · Checked on this machine” or “Show me again”. Existing `turn.detail` messages carry status; contracts are unchanged. New turns, cancellation, camera shutdown and disconnection remove stale success. The card never sends a confirmation.

## Methods

1. **Qwen:** existing local Ollama `/api/chat`, default `VISION_CAPTION_MODEL=qwen2.5vl:7b-q4_K_M`. Strict JSON schema and parser reject prose, extra/duplicate keys, booleans, nonfinite or out-of-range confidence. Prompt requires an unambiguous valve position and abstention on ambiguity, blur, glare, occlusion or multi-turn handles. The optional closed/open photos are explicitly identified as references. No fake runtime fallback.
2. **Image embedding:** local CPU CLIP-compatible ONNX image encoder, cosine similarity against one closed and one open reference. Both references are required. Similarity below 0.9 or a gap below 0.05 abstains. Score is `(best_cosine + 1) / 2`; the tuned confidence threshold is applied afterward. No combination was added.

Qwen accepts only localhost or literal private/loopback/Tailscale addresses; public URLs, DNS hostnames other than localhost, redirects and environment proxies are blocked. The embedding encoder reads local weights only and never downloads them. `onnxruntime` and `numpy` are already specified in `router/requirements-router.txt` and available in the test interpreter; no new dependency was added.

Provide an operator-provisioned CLIP ViT-B/32-compatible ONNX **image** encoder at `STEP_CHECK_ENCODER`, with input `pixel_values [N,3,224,224]` and output `image_embeds [N,D]`. Preprocessing uses RGB, bicubic short-side resize, center crop, and CLIP mean/std. Arbitrary vision exports with a different interface or preprocessing are unsupported and fail closed. No encoder checkpoint was provisioned or measured in this task.

## Pictures and consent

Live frames and supplied comparison images are decoded/resized only in RAM. Tests cover malformed input, errors, a real loopback HTTP round-trip, and Pictures saved remaining **0** for ordinary checks. No live frame is saved automatically; image content and provider exception text are not logged.

`PUT /api/step-check/reference` accepts `{state: "closed"|"open", image_b64, consent: true}`. Only literal `true` is accepted. It requires an enabled `A_EYE_MEMORY_KEY` cipher; the local-memory plaintext fallback is refused. References belong to the authenticated caller's existing memory identity and are encrypted with its Fernet cipher. The home flow loads only its attached memory store. Enable that caller's existing memory attachment to use a saved reference; this package does not enable memory automatically.

`DELETE /api/step-check/reference` removes both of that caller's references; existing memory “Forget everything” also removes them. Individual references persist until deleted (no separate reference expiry). The reference API is available for integration; no reference-upload UI was added.

An explicitly saved reference is a saved picture and is counted by the existing proof strip. **Zero applies to the default RAM-only flow, not a user-authorized reference save.** The implementation does not hide encrypted pictures from the counter. No files under `data/` were manually edited, and no private planning notes were copied into this repository.

## Evaluation and measured pipeline proof

Dangerous false-**closed** results first: **Qwen stand-in: 0; embedding stand-in: 0.** These are synthetic protocol/pipeline results, not Qwen/CLIP accuracy or latency measurements.

Executed:

```sh
/Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/step_check_eval.py --synthetic --report /private/tmp/step-check-synthetic.json
```

The fixture draws 12 prop-valve images in an automatically deleted temporary directory. Qwen uses a deterministic HTTP transport stand-in; the embedding method uses deterministic image features. Both exercise the real checker wrapper. Fixed seed: `20261024`; tune: 6 (two references, four scored); held-out: 6.

| Method (synthetic stand-in) | Actual | Predicted open | Predicted closed | Predicted unsure |
|---|---|---:|---:|---:|
| Qwen | open | 3 | 0 | 0 |
| Qwen | closed | 0 | 3 | 0 |
| Embedding | open | 3 | 0 | 0 |
| Embedding | closed | 0 | 3 | 0 |

| Method (synthetic stand-in) | Frozen threshold | p50 | p95 |
|---|---:|---:|---:|
| Qwen | 0.99 | 1.174 ms | 1.245 ms |
| Embedding | 0.99 | 2.739 ms | 2.808 ms |

The synthetic ranking selected Qwen by latency after tied classification counts; this does **not** select the real deployment method. The JSON report is marked `synthetic: true`, and runtime rejects it.

## Human dataset: layout and one command

Keep all human photos outside the repository and coding-agent context. Supply 20 independently captured open images and 20 closed images of the same home's valve. Use varied angles/light and avoid near-duplicate burst frames. An ambiguous/partial position should not be mislabeled as confidently closed. Duplicate image bytes are rejected before inference.

```text
~/a-eye-private/valves/
  open/
    001.jpg ... 020.jpg
  closed/
    001.jpg ... 020.jpg
~/a-eye-private/models/clip-vit-base-patch32-vision.onnx
```

After the local Qwen service and compatible encoder weights are provisioned, run from this worktree:

```sh
OLLAMA_URL=http://100.93.176.7:11434 STEP_CHECK_ENCODER="$HOME/a-eye-private/models/clip-vit-base-patch32-vision.onnx" /Users/minhducvo/Projects/a-eye/.venv/bin/python scripts/step_check_eval.py "$HOME/a-eye-private/valves" --report "$HOME/a-eye-private/valve-eval.json"
```

This produces a stratified fixed-seed 20/20 split. The first tune image of each class supplies a reference; the other 18 tune images select among confidence thresholds 0.9/0.95/0.99. Both thresholds are frozen **before either method sees any held-out image**. Nothing trains or tunes on held-out images. Hashes record split membership without copying photos. Latency includes preprocessing, reference encoding and inference; p50 is the median, p95 nearest rank, cold calls included.

Selection uses held-out false-closed count first, then correct closed, correct open, and p95 latency. Only methods with zero false-closed and at least one correct closed are eligible; all-abstaining methods cannot win. Held-out method selection is not an independent post-selection accuracy estimate. Do not repeatedly adjust thresholds/prompts after inspecting these results and still call this set held-out; collect a new set for that iteration.

The operator can set `STEP_CHECK_CONFIG` to the resulting real JSON report for new sessions. Runtime requires `synthetic: false`, at least 20 held-out photos, zero false-closed, a positive closed control, and a safe threshold. Missing/invalid reports keep the gate locked. These small-sample criteria are a demo acceptance boundary, not a statistical safety certification. Missing models appear as unsure results and may leave no eligible method.

## Verification and limits

Tests first: the new checker test initially failed collection because `server.step_check` did not exist. Final targeted tests cover strict parsing, local-only destinations, errors/timeouts/staleness, cancellation, positive/negative home-flow controls, consent/encryption/isolation, picture accounting, split separation and activation guards.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_step_check.py scripts/test_step_check_eval.py server/test_home_pack.py server/test_home_safety.py server/test_agent.py server/test_proof_wall.py` - PASS (**65 passed in 1.04s**).

The first sandboxed full suite reported **1 failed, 829 passed, 2 warnings, 4 errors in 40.41s**; all five failures were localhost bind permission errors. The five-test localhost rerun passed (**5 passed in 16.06s**). The subsequent full run found one isolated JS auth-test fixture missing the new valve-card dependency (**1 failed, 835 passed, 2 warnings in 71.09s**). `server/test_access.py` now supplies that dependency and asserts it is cleared; its existing auth assertions remain intact.

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q server/test_access.py::test_4401_stops_retries_and_offers_reload` - PASS (**1 passed in 0.56s**).

Test: `/Users/minhducvo/Projects/a-eye/.venv/bin/python -m pytest -q` - PASS with localhost access (**836 passed, 2 warnings in 67.51s (0:01:07)**). This is a single green final full-suite invocation. Both warnings concern existing short synthetic JWT keys in identity tests.

Test: `node --test client-web/` - PASS (**tests 145; pass 145; fail 0; skipped 0**, final run 1176.210792 ms). Includes actual call-page module event wiring and disconnect cleanup, with a DOM fixture; no browser screenshot was taken.

Test: `git diff --check` - PASS.

`test_real_loopback_api_to_qwen_protocol_keeps_pictures_zero` made real HTTP requests through the application and local Qwen protocol with a synthetic image/provider. It returned `closed, 0.99` and retained zero pictures; this is network integration proof, not a real Qwen inference.

The inherited home-pack contract hold remains: `contracts/schema.json` does not yet allow `home` and the client has no active home-pack selector. This package wires the server gate and card without changing or bypassing that contract. The lead must coordinate the contract/selector change before a real browser home call. Real valve photographs, local Qwen/CLIP accuracy and performance, visual browser review and a physical no-flow check remain unverified. A visually closed valve can still leak internally; this classifier cannot certify actual water flow or replace the guide's tap/no-flow check.

Finished: checker, evaluation harness, gate and card. Next: lead review and human-photo evaluation. Suggested: GPT-6 / high.
