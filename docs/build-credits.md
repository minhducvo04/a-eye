# Who built what

A-eye was built at Cal Hacks 13.0 by a small human team working with AI coding agents. This page records which
agent or person did which work, from the git history and the build logs, so we can answer "how did you build it?"
honestly. Updated 2026-10-24.

## People

- the team: product, architecture decisions, testing on real devices, every push to GitHub.
- Teammate (iOS): the native iPhone app in `ios/AEye` and `ios/AEyeCore` (commits by `the team`).

## AI agents

Every change still went through the team's flow: one owner per package, the builder runs the tests for what it
changed, a minimal check of the result before merge, and a human push.

| Agent | Role | Examples of work (commit messages say "built by Codex" where Codex wrote the code) |
|---|---|---|
| Claude (Opus 5.5 coding agents in Claude Code) | Coordinator, most packages, reviews, benchmarks | Web call page and iOS parity, Cartesia voice path, hall-noise handling, Rewind (TwelveLabs), Cloudflare Access login, phone as camera + mic, Vision Pro app, trained router, benchmarks and docs |
| Codex (OpenAI coding agent) | Builder for several core packages | /ws2 agent and skill packs, GPU box service (Whisper, Kokoro, YOLO), streaming turns, change-triggered keyframes, Qwen grounding, phone pairing server and Vision Pro pairing, API reference |
| Grok (xAI) | Planned reviewer and writer; also benchmarked as a backend (`grok -p`) | No merged A-eye code yet |

Counts at the time of writing (`git log`): 144 commits on main; 14 marked "built by Codex"; 106 carry a Claude
co-author line; 4 by the iOS teammate. Counts are approximate: some Claude-led packages dispatched Codex for parts.

## Models used inside the product

See [model-choices.md](model-choices.md): Claude Haiku 5.5 (talker), Claude Sonnet 5.5 (planner), Claude Opus 5.5 and
Fable 5.1 (rare expert), Qwen 3.5 9B and Qwen 2.5-VL 7B (local vision), Whisper and Kokoro (local speech),
Cartesia Sonic 3.6 (voice), TwelveLabs Marengo and Pegasus (Rewind), EmbeddingGemma (router).
