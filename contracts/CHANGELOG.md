# Contract changelog and freeze

`schema.json` is the source of truth. Minor v2 revisions retain wire `v: 2`; market payloads still use `v: 1`. This inventory records the checked-in contract, not release dates or deployment status.

## Freeze rule

From now on, changes may only add optional fields or new message types. Do not remove or rename fields, make optional fields required, or change existing meanings. Add an entry here for every addition; update schema, TypeScript mirror and examples together through the contract PR process and run `make test-py`. Clients must ignore unknown response fields and unknown message types (and skip unknown draw kinds). Current server request validation remains strict; do not send speculative fields. A breaking change requires a separately negotiated major protocol, outside this freeze.

## v2.3: turn stages, streamed reply text, camera switch

- New `v2_turn` (server): required `v`, `type:turn`, `turn_id`, `stage`, `at_ms`; optional `text`, `detail`, `typical_ms`. Stages: received (the ack, sent at once), transcribing, thinking, backup, speaking, done, failed, cancelled. Every turn ends with exactly one of done, failed or cancelled.
- New `v2_reply_delta` (server): required `v`, `type:reply_delta`, `agent`, `turn_id`, `text`. Spoken reply text as it is generated, for captions only; `v2_say` stays the unit for speech.
- New `v2_camera` (client): required `v`, `type:camera`, `session_id`, `on`. Optional `v2_hello.camera`. Off means voice only: no frame stored, no scene calls.
- Added turn and reply_delta to `server_message_v2`, camera to `client_message_v2`.

## v2.2: server speech input

- Optional `v2_hello.stt`: `browser` or `server`.
- New `v2_audio_in`: required `v`, `type:audio_in`, `session_id`, `seq`, `pcm16_b64`; optional `sample_rate` (16000) and `final`. Input is 16 kHz mono PCM16; final ends an utterance.
- Added `v2_audio_in` to `client_message_v2`. No transcript response type was added.

## v2.1: streaming and tracking

- New `draw_anchor` object (`object_id`, `bbox`); optional `anchor` on every draw-op kind.
- Optional `turn_id`, `part`, `final` on `v2_say` for streamed speech parts.
- New `v2_metrics`: required `v`, `type`; optional `turn_id`, `seq`, `vlm_ms`, `brain_first_token_ms`, `first_audio_ms`, `turn_ms`, `track_ms` (milliseconds).
- New `v2_track`: required `v`, `type`, `seq`, `objects` (scene objects).
- Added metrics and track to `server_message_v2`.

## v2.0: general agent call

- Added `/ws2` vocabulary with wire `v:2`, while keeping `/ws` v1.
- Client messages: `v2_hello` (pack, optional board/client/TTS choice), `v2_frame`, `v2_user_text` (final and optional source), `v2_barge_in`, `v2_confirm`.
- Server messages: `v2_draw`, `v2_say`, `v2_audio` (optional sample rate and final chunk flag), `v2_agent_state` (optional focus), `v2_market_results`, `v2_error`; client/server v2 message unions.
- Draw kinds: box, highlight, circle, arrow, path, label, pin, clear. Required IDs; optional role, label and TTL. Coordinates normalized to the sent frame; bbox is top-left `[x,y,w,h]`.
- Agent IDs helper/shopper; packs general/pc_build/cooking/assemble; presence idle/listening/thinking/speaking; draw roles target/info/warn/ok.
- `scene_object` (`id`, `label`, `bbox`, `conf`), `scene_request` (`image_b64`, optional queries/max_objects), `scene_response` (caption/objects/ms, optional source).
- `brain_turn`: internal agent/say/draw intent with optional market_category; object-ID targets resolved by the server. Not a phone wire message.
- V2 errors: bad_message, power_off_required, refused, vision_unavailable, brain_unavailable, internal.

## v1: PC build flow and service boundaries

- `/ws` client messages: hello, project_open, frame, photo, confirm, user_text, parts_scan, market, audio.
- `/ws` server messages: overlay, say, step, verdict, parts, market_results, summary, annotated, error, audio. Client/server message unions.
- Step states SAFETY, IDENTIFY, LOCATE, GUIDE, AWAIT, VERIFY, DONE, RETRY; closed allowed-part set and power-off confirmation.
- Vision request/response pairs: identify, locate, verify; health_response; normalized boxes, confidence and pin geometry.
- Voice adapter messages: voice_say, voice_transcript, voice_barge_in, voice_spoken; 16 kHz mono PCM16 socket audio.
- Market definitions: part_category, part_specs, part, market_query, compat, offer, market_response. Compatibility is fits/no/unverified; unknown facts remain unverified.
- Header-table definition for checked board/header/pin mappings.

## Integration note (new tonight)

Token authentication, `/api/scene`, `/api/market`, `/api/status`, mock mode and HTTPS helper commands are parallel server additions. They do not change the v2 wire integer. REST scene/market reuse existing contracts; no status contract exists in this checkout. Their described behavior is in [the phone reference](../docs/api.md), pending integration verification.
