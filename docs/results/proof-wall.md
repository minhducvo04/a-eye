# Proof wall — lead review receipt

Implemented in the working tree; no commit. Read AGENTS.md and CLAUDE.md. No changes to contracts or server/ws2.py.

The Private expert regression failed first at the expert handoff, then passed after routing Private expert requests through the normal local talker. It says “Private mode: I will answer with the local model.” Subsequent model-requested escalation is also disabled in Private mode. Existing provider guards select the local backend; local failure is shown as unavailable/canned, not a successful model answer.

## Judge setup and offline login

1. Before disconnecting WAN, provision the local model files and LAN services. Set OLLAMA_URL, BOX_URL, VISION_URL and, if used, ROUTER_OLLAMA_URL to the machines' **home LAN addresses**, not a public tunnel or a relay-dependent address. Keep the LAN switch/Wi-Fi on when unplugging internet.
2. Configure A_EYE_TOKEN privately in the server environment. Do not enable A_EYE_OPEN. Run `LOCAL_ONLY=1 make server` (or the same uvicorn command with the configured environment). Select Private in Settings: local brain, Kokoro, server STT, Rewind off.
3. LAN page: `http://<server-LAN-IP>:8000/agent.html?token=<A_EYE_TOKEN>`. The browser sends that token as a Bearer header to `/api/proof` and uses the existing token path for `/ws2`. A valid token is checked before Cloudflare certificates, so this works without Access or internet. Do not copy a real token into receipts or logs.
4. Camera/microphone require a secure browser context: on the server Mac use `http://localhost:8000/agent.html?token=<A_EYE_TOKEN>`; on another LAN device use an already trusted local HTTPS endpoint/certificate. Plain LAN HTTP permits the page and typed demo but is not camera/mic proof. Cloudflare Access/tunnels are not the offline route.
5. Run `make offline-check` and `python scripts/proof_wall_rehearsal.py` with the same local service environment. If this worktree lacks a venv, `make offline-check PY=/Users/minhducvo/Projects/a-eye/.venv/bin/python` uses the existing interpreter. No model download is performed by these scripts.

Authentication is unchanged. The new GET `/api/proof` is under the existing `/api/` middleware: no credential and wrong credential are 401 remotely; valid token succeeds. There is no new write endpoint or public proof bypass.

## What the strip proves

- **Pictures saved**: actual recursive image-file count under this checkout's server `data/` directory, including encrypted `.jpg` crops. Counts filenames with known image extensions without opening content or following symlinks. An unreadable directory returns unknown. This does not inventory other directories, extensionless files, video or audio; externally configured memory directories are outside this count.
- **Online/Offline**: server TCP handshake to `1.1.1.1:443`, cached for 10 seconds. It sends no HTTP payload, credentials, media or conversation. This intentional connectivity probe is an outbound connection attempt even in Private mode. Offline means this probe failed, not universal proof that every internet host is unreachable. HTTP failure displays unknown, never Offline.
- **Brain**: actual streaming provider/model captured in turn context and carried in the existing `turn.detail` field. Local, expert/cloud and unavailable/canned are distinct. Expert answers use their result model metadata. Planner tasks cannot overwrite talker metadata. No schema changes. Memory lookup and fixed safety answers do not invoke a brain and retain the last model label.
- **Stopped by code**: the fixed home-safety refusal or a streamed sentence replaced by the safety guard emits turn metadata. The label clears on the next received turn.

Cloud boundary tests exercise Anthropic, Cartesia, TwelveLabs, hosted OpenAI-compatible fallback and Private expert routing with intercepted transports. They support the guarded paths tested; they are not a formal proof over every possible code path or arbitrary operator-supplied service URL. The requested physical WAN-disconnected demonstration remains for the judge; networking was not changed during this run.

## Verification

Interpreter: `/Users/minhducvo/Projects/a-eye/.venv/bin/python` (this worktree has no `.venv`).

- Failing test first: `python -m pytest -q server/test_proof_wall.py` → **1 failed**, `Private turn must not enter the expert desk`.
- `python -m pytest -q server/test_proof_wall.py server/test_agent.py server/test_llm.py server/test_brain_local.py server/test_brain_openai_compat.py server/test_expert.py server/test_auth_fixes.py voice/test_safety.py voice/test_private.py voice/test_home_first.py` → **167 passed in 5.87s**.
- After final provider metadata isolation and fixture test: `python -m pytest -q server/test_proof_wall.py server/test_agent.py server/test_llm.py server/test_brain_local.py server/test_brain_openai_compat.py scripts/test_offline_check.py` → **55 passed in 4.97s**. Other previously passing modules were unchanged.
- `node --test client-web/` → **138 passed, 0 failed**, 861 ms. Includes proof model display and safety reset assertions in the existing real client handler harness. An initial run hung because the new interval used the global timer instead of the client window timer; corrected and rerun.
- Real Chromium smoke used a temporary authenticated loopback mock server with synthetic camera/mic and temporary memory: `env A_EYE_TOKEN=<fixture> uv run --offline --no-project --with playwright python scripts/browser_smoke.py http://127.0.0.1:18439`. First authenticated run: **BROWSER SMOKE PASS**, 2 frames, problems `[]`, longest find-card task 0 ms. Final run additionally asserts the proof count and server network result (see final summary below). Mock smoke establishes browser wiring, not GPU inference or physical devices.

### Local readiness output

`python scripts/offline_check.py` (exit 1 because vision is missing):

```text
WAN must be unplugged by the judge; this command does not change networking.
PASS | local talker | answered locally
SKIP | local vision | unavailable (ConnectError)
PASS | STT | answered locally
PASS | TTS | answered locally
PASS | router | answered locally
PASS | local memory search | answered locally
PASS | Private cloud boundary tests | 24 passed in 1.84s
OFFLINE CHECK: 5/6 services; guards=PASS
```

STT probe uses synthetic silence and checks a valid transcript response, not recognition accuracy. Vision requires a non-fake health response and synthetic scene inference. Memory checks exact recall and local semantic embedding. Full six-service offline readiness is **not** established: start/configure local vision and rerun with WAN disconnected.

### Rehearsal output

Real production HTTP/WebSocket server on an ephemeral loopback port; temporary fixture identity/token and text-only memory removed at exit. Every hello has Private=true, camera=false, Rewind=false, server TTS/STT. Router is off to exercise the existing deterministic recall path; router inference is checked separately by offline-check. Five trials each ask yesterday's memory, trigger the smoking power-strip gate, and GET the authenticated picture count. First-audio is receipt of nonempty server PCM; answer is receipt of the final spoken-text message (not playback completion). Typed input does not measure STT latency.

```text
trial 1 yesterday: PASS; first_audio=456ms; answer=684ms
trial 1 safety: PASS; first_audio=488ms; answer=4ms
trial 1 pictures: 0; PASS
trial 2 yesterday: PASS; first_audio=306ms; answer=546ms
trial 2 safety: PASS; first_audio=508ms; answer=4ms
trial 2 pictures: 0; PASS
trial 3 yesterday: PASS; first_audio=1011ms; answer=1319ms
trial 3 safety: PASS; first_audio=1044ms; answer=4ms
trial 3 pictures: 0; PASS
trial 4 yesterday: PASS; first_audio=291ms; answer=629ms
trial 4 safety: PASS; first_audio=396ms; answer=4ms
trial 4 pictures: 0; PASS
trial 5 yesterday: PASS; first_audio=304ms; answer=709ms
trial 5 safety: PASS; first_audio=543ms; answer=4ms
trial 5 pictures: 0; PASS
REHEARSAL: 5/5 PASS, 0/5 SKIP (missing local audio), 0/5 FAIL; text fixture removed
```

The first rehearsal used “Where were my keys yesterday?”, which the existing regex does not route to memory, and failed recall 5/5. Corrected the script to “Where did I leave my keys yesterday?” and reran all five. No recall production logic was changed. Missing Kokoro marks an otherwise successful trial SKIP and leaves first-audio unmeasured.

Final browser smoke (with the proof endpoint assertions): **BROWSER SMOKE PASS**, `frames_sent: 2`, `problems: []`, longest find-card task **0 ms**. `git diff --check` passed. Temporary smoke server stopped after verification.

## Changed files

- `Makefile`, `scripts/offline_check.py`, `scripts/test_offline_check.py`: six service probes, fixture helper and local fixture test.
- `scripts/proof_wall_rehearsal.py`: isolated real five-trial rehearsal.
- `server/proof_wall.py`, `server/app.py`: authenticated read-only count/connectivity route.
- `server/agent.py`, `server/llm.py`, `server/brain_local.py`, `server/brain_openai_compat.py`, `server/expert.py`: local expert fallback and actual turn provenance/safety metadata.
- `server/test_proof_wall.py`: fail-first expert regression, count/auth boundary, live-versus-cached server probe tests, model and safety provenance.
- `client-web/agent.html`, `client-web/agent.js`, `client-web/agent.css`, `client-web/turn.test.mjs`: quiet wrapping strip and handler checks.
- `scripts/browser_smoke.py`: real count/connectivity assertions in existing browser smoke.
- `RESULT.md`, `docs/results/proof-wall.md`: handoff and retained evidence.

Review holds: physical WAN-unplugged run; local vision service; secure-context LAN camera/mic setup. No commit, merge, push, deploy or auth relaxation.
