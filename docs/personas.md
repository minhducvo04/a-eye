# Dad personas

Owner decision, 2026-10-24: **“Dad, how do I?”** is an AI dad, A-Eye, helping people do things. Sink is the hero task. Dad/father persona wording is allowed; claiming to be someone's actual parent, romance, dependence and isolation are not. Family venting keeps its fixed neutral reply.

## Add a persona

Drop a JSON file into `server/personas/`. No server or client code change is needed. Files are loaded on each registry request and new hello; existing calls keep their selected settings. Refresh the page or reopen iPhone Settings to discover new entries.

```json
{
  "id": "patient-dad",
  "display_name": "Patient dad",
  "voice_style": {
    "tone": "warm",
    "humor_level": "light",
    "strictness": "gentle",
    "praise_style": "factual",
    "catchphrases": ["One step at a time."]
  },
  "tts_voice": "am_michael",
  "gemini_live_voice": "Orus"
}
```

The ID must be unique, lowercase, start with a letter, contain only letters/digits/hyphens, and be at most 48 characters. Display names are 1–60 characters. All five `voice_style` fields are required:

| Field | Values |
|---|---|
| `tone` | `direct`, `warm`, `relaxed` |
| `humor_level` | `none`, `light`, `playful` |
| `strictness` | `firm`, `balanced`, `gentle` |
| `praise_style` | `factual`, `quiet` |
| `catchphrases` | Zero to five short phrases, at most 100 characters each |

Unknown fields, duplicate IDs and catchphrases rejected by `product_rules.allowed()` fail validation. Invalid files fail registry loading rather than being silently ignored. Keep catchphrases ordinary wording, with no instructions, task facts, promises, or safety advice. This is trusted teammate configuration, not an end-user prompt editor.

The marked `[PERSONA STYLE ONLY]` block is appended to the classic talker system prompt and Gemini Live system instruction. It changes tone only. Strict means clear, never pressuring; humor must not obscure steps. Praise stays factual and earned. Existing generic praise bans remain. Coded refusal, power, confidence, freshness, verification and compatibility gates remain outside persona configuration. Sink's fixed instructions are not rewritten for a persona.

## Selection and voices

Authenticated `GET /api/personas` returns `{ "personas": [...], "default": "chill-dad" }`, including style and optional voice fields. Web and iPhone Settings populate their picker from this response and remember the selected ID. Changing persona ends an active call; the next hello carries it:

```json
{"v":2,"type":"hello","session_id":"example","pack":"home","persona":"funny-dad"}
```

`persona` is optional and additive to v2. Omission selects Chill dad. Unknown IDs reject hello without replacing a valid session. TypeScript, Swift and the reference Swift socket mirror the optional field.

| Starter | Delivery | Classic TTS | Gemini Live |
|---|---|---|---|
| Strict dad | Direct, firm, no humor | `bm_george` | `Charon` |
| Funny dad | Warm, playful, balanced | `am_puck` | `Puck` |
| Chill dad (default) | Relaxed, gentle, light humor | `am_michael` | `Orus` |

Both voice fields are optional. Classic voice precedence is explicit `hello.voice`, persona `tts_voice`, pack voice, adapter default. The web's “Persona voice” option clears the explicit override; changing persona also clears it. Test Voice samples the selected classic voice. Browser speech remains an explicit alternative. The iPhone requests server TTS for classic turns while keeping its local recognizer; absent/empty server audio falls back to native speech. Out-of-turn native notices keep immediate native speech. Classic turn audio is queued with a 60-second cap; no audio is persisted.

`tts_voice` uses an existing adapter voice ID (`/api/voices`), such as a Kokoro name or `cartesia:<id>`. Adapter availability and existing privacy settings can cause fallback; setting a name does not install a voice. `gemini_live_voice` sets `generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`; omission leaves the provider default. See Google's [Live API capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities). Provider acceptance and physical-device playback of these choices were not tested in this change.

## Mode and shopping switches

Both rings default to **Sink → General → Memory**, with Sink selected. General uses Gemini Live when Google is enabled and Private mode is off; existing consent/private fallback behavior remains. The duplicate Gemini Live ring entry is removed; the old web `?mode=gemini-live` link selects General.

`ENABLE_EXTRA_MODES=1` exposes PC Build, Cooking, Assembly, Mechanic and Engineering through authenticated `GET /api/features`. Their implementation stays in the tree; existing unavailable placeholders remain unavailable. This flag controls ring visibility, not authorization to skill packs.

Shopping is independently off unless `SHOPPING=1`. Disabled shopping refuses before search/vision calls, ignores model/planner market requests, blocks the v1 route, and makes `/api/market` return 403 with `shopping_disabled`. Other flag values, including `true`, stay off. Existing privacy/compatibility checks still apply when enabled.

To check a new JSON file, run `python -m pytest -q server/test_personas.py server/test_product_rules.py`. The registry tests allow additional personas; they require the three shipped starters to remain present. Use the project's Python environment.
