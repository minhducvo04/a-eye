# Privacy: what leaves A-eye, and what the providers do with it

Researched 2026-10-24 against `main` at `d33395c`. Provider facts come from each provider's own page, fetched that
day; the page's own date is given next to each link. Where a page does not say something, this file says
"not stated on <page>" instead of guessing. Code facts cite `file:line` on that commit. Not checked: the live
server's `.env` (so which flags the demo actually runs with), the Cartesia or TwelveLabs account plan and settings,
and whether an Anthropic ZDR agreement exists. Assume none until someone checks.

## The answer to say out loud

> Your video and your voice go to our own GPU box first: speech recognition, object detection and the voice run
> there. Claude gets text: your question, the last few lines of the chat and a written description of the scene.
> Sometimes it also gets one small crop of one object, never the full camera view. Anthropic's commercial terms say
> they may not train on that, and they delete it within 30 days. Video leaves the box only if you turn on Rewind,
> which is off by default. Two honest caveats: our cloud voice, Cartesia, and our Rewind search, TwelveLabs, can
> use data for training unless the account opts out, and Rewind clips stay in TwelveLabs until we delete them.
> We are fixing both.

(123 words.) Do not say "nothing is ever trained on" or "nothing leaves the box": both are false today (see Gaps).
The iPhone app's speech recognition is on the phone; the web page may use the browser's own recognition (gap 4).

## Per provider

| Provider | Trained on by default? | Default retention | Deletion / ZDR | What A-eye sends |
|---|---|---|---|---|
| **Anthropic API** (Haiku 5.5 talker, Sonnet 5.5 planner, Opus 5.5 / Fable 5.1 expert) | **No.** Commercial Terms: "Anthropic may not train models on Customer Content from Services." | Inputs and outputs deleted "within 30 days". Up to 2 years if flagged for a Usage Policy violation; 5 years for submitted feedback. **Fable 5.1 is a Covered Model: at least 30 days, no ZDR.** | ZDR by agreement through Anthropic sales, per organization; not available for Fable 5.1 unless Anthropic authorizes it. Prompt caching and web search are ZDR eligible; web search "dynamic filtering" is not. | Text: transcript of the question, last 10 lines of conversation, scene caption, object labels and boxes, scene memory. Planner and expert may add **one crop** (at most 512 px, at most half the frame). Expert may run up to 3 web searches. |
| **Cartesia** (cloud TTS, used when `CARTESIA_API_KEY` is set) | **Yes, unless opted out.** Terms 5.3(c): Inputs and Outputs "may be used by Cartesia to train, enhance, evolve and improve" its models. Opt-out by the data-controls form, going forward only. | Not stated on the terms or privacy policy. | ZDR for **Enterprise plans only**, enabled by an org admin in the Playground. Account deletion: Cartesia "may, but is not obligated to, delete" content. | A-eye's own spoken sentences (the reply text), voice id. No user audio, no images. |
| **TwelveLabs** (Rewind search and recap, only while Rewind is on) | **Yes, unless opted out.** Terms: data may be used to "provide, maintain, enhance, train, and improve" the services "unless you opt out of training through your account settings". | Not stated; privacy policy: kept "for as long as you use the Twelve Labs Services". | API: `DELETE /v1.3/indexes/{index}/videos/{video}` (marked for deprecation), `DELETE /v1.3/indexes/{index}/indexed-assets/{id}`, `DELETE /v1.3/indexes/{index}`, each "cannot be undone". The docs do not say whether embeddings or the source file go too. | Silent MP4 clips (no audio) of the camera view around scene changes, 4 to 12 s, up to 60 per call, with call time metadata. Recap sends a base64 MP4 of kept frames to `/analyze`. Search queries derived from the user's question. |
| **Cloudflare Access + Tunnel** (`aeye.minhducvo.com`) | Responsible AI page: "we do not use our customers' content to train any LLMs." | Access logs: 24 hours on Free, 30 days on Standard, 180 days on Enterprise. Traffic: not stated on the privacy policy (deleted when "the data retention period expires"). | Cloudflare acts as processor for content passing through. | Everything on the wire: the Tunnel carries the web page, socket, frames and audio. The SSL modes page implies Cloudflare terminates TLS at its edge, so it can technically see that traffic; not stated outright. Access sees the sign-in email, IP and login method. |
| **Google** | Not used: Gemini is only in benchmark scripts (`voice/gemini_live.py`, `voice/voice_pick.py`), never imported by `server/`. **But see gap 4**: Chrome's built-in speech recognition. | n/a | n/a | Nothing from the server. |
| **Apify / Bright Data** (market prices) | Not researched. | | | Only when `MARKET_SOURCE` is `apify` or `brightdata`; the default is a local fixture (`market/search.py:75`). Sends a product category and query key, not user words. |

Sources (fetched 2026-10-24):
[Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (effective Jun 17, 2025);
[Anthropic: how long do you store my organization's data](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) (dated Jul 1, 2026);
[Claude API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) (no date shown);
[Covered Models](https://support.claude.com/en/articles/15425695-covered-models) (Sep 1, 2026);
[Cartesia terms](https://cartesia.ai/legal/terms.html) and [privacy](https://cartesia.ai/legal/privacy.html) (both last revised Jun 14, 2024);
[Cartesia ZDR](https://docs.cartesia.ai/enterprise/zero-data-retention) (no date);
[Cartesia trust center](https://trust.cartesia.ai) (no readable content when fetched);
[TwelveLabs terms](https://www.twelvelabs.io/terms-of-use) (Aug 25, 2026) and [privacy](https://www.twelvelabs.io/privacy-policy) (Jan 12, 2026);
TwelveLabs [delete video](https://docs.twelvelabs.io/v1.3/api-reference/videos/delete), [delete indexed asset](https://docs.twelvelabs.io/v1.3/api-reference/index-content/delete), [delete index](https://docs.twelvelabs.io/v1.3/api-reference/indexes/delete);
[Cloudflare responsible AI](https://www.cloudflare.com/trust-hub/responsible-ai/) (no date), [privacy policy](https://www.cloudflare.com/privacypolicy/) (Nov 4, 2025),
[Zero Trust logs](https://developers.cloudflare.com/cloudflare-one/insights/logs/) (Oct 15, 2026), [SSL modes](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/) (Apr 16, 2026).

## What A-eye sends where (code)

- **Talker** (Haiku): text only. The prompt is a JSON of caption, objects, scene memory, `conversation=session.history[-10:]`
  and the question (`server/agent.py:397-400`); model `claude-haiku-5-5` (`server/llm.py:53`).
- **Planner** (Sonnet, "duo" mode) and **expert** (Opus or Fable, `server/expert.py:16-17`, `:59`, prompt `:117`):
  same text plus `planner_crop` (`server/agent.py:297-301`). A crop is refused when it covers more than half the
  frame; it is at most 512 px and 200,000 base64 bytes (`server/crops.py:8-10`). `server/llm.py:133` and `:198` drop
  any image set over 400,000 bytes before the cloud. The expert adds the web search tool (`server/llm.py:324`).
- **Rewind tool results** sent back to Claude carry times and labels; the frame is stripped (`server/rewind_tools.py:61`).
- **`LOCAL_ONLY=1`** blocks Claude in every path: `server/llm.py:131`, `:200`, `:284`, crops at `server/agent.py:301`,
  duo at `server/ws2.py:341`, expert at `server/expert.py:59`. It does **not** touch Cartesia (`voice/adapter.py:101`)
  or Rewind (`server/rewind.py` has no `LOCAL_ONLY` check).
- **`LLM_PROVIDER=local`** ("brain local") makes `use_claude` false, so turns go to Ollama on the box (`server/llm.py:130`, `:193`).
- **Vision**: frames go to `VISION_URL` (default `127.0.0.1:8001`, `server/vision_client.py:16`), which runs local
  models on the box (Ollama over Tailscale).
- **Speech to text**: server STT posts PCM to the box's Whisper (`server/box_client.py:8`, `:19`). The iPhone app
  uses on-device recognition (`ios/AEye/App/Call/SpeechIn.swift:180`). The **web page defaults to browser STT**
  (`client-web/agent.js:158`, `client-web/voice.js:1340`) unless a mic is picked in Settings (`client-web/agent.js:181`).
- **Text to speech**: Cartesia when its key is set and the voice is auto (`voice/adapter.py:101`), sending the reply
  text (`voice/cartesia_ws.py:37`); otherwise Kokoro on the box, which logs only timing (`boxsvc/app.py:111`).
- **Rewind**: off by default (`client-web/agent.js:197`, `server/ws2.py:566`), toggled per call (`server/ws2.py:662`),
  notice text at `server/rewind.py:26`. Full camera frames from the session, not crops (`server/rewind.py:405`),
  encoded with no audio (`server/rewind.py:167`), uploaded to one shared index `a-eye-rewind` (`server/rewind.py:25`,
  `:106`, `:119`). The local temp MP4 is removed after upload (`server/rewind.py:293`). Turning Rewind off drops
  clips not yet sent (`server/rewind.py:213`). Call end uploads the rest (`server/rewind.py:457`, `server/ws2.py:463`).
  **No code deletes anything on TwelveLabs.**
- **Router**: off unless `ROUTER=on` (`server/routing.py:36`); runs local embeddings (`router/embed_local.py`) or
  the box's Ollama (`router/embed.py:6`).
- **Logs**: an allowlist of metadata fields only, no text field (`server/logs.py:8`); session ids hashed
  (`server/logs.py:16`); the Access email is logged as a 12-hex SHA-256 prefix (`server/auth.py:105`). The question
  text goes to the user's own screen as the "thinking" stage (`server/ws2.py:338`), not to a log. No raw transcript
  logging was found in `server/`, `voice/` or `boxsvc/`.

## What stays local

Camera frames for detection and captions, server speech recognition (Whisper), Kokoro voice, the local brain
(Ollama) when Claude is off, the router, scene memory, and every log. On iPhone, speech recognition stays on the phone.

## Gaps and honest risks

1. **TwelveLabs keeps Rewind clips forever, as far as the code goes.** Nothing calls a delete endpoint; all calls
   share one index. TwelveLabs may also train on them unless the account has opted out in settings (not checked).
2. **Cartesia may train on A-eye's replies** unless the account used the opt-out form or is on Enterprise ZDR (not
   checked). A reply can repeat what the user said ("your blood pressure cuff is on the left").
3. **`LOCAL_ONLY=1` is not "local only".** It stops Claude but not Cartesia or Rewind. `AGENTS.md` says it "blocks
   cloud models entirely" and that frames go only to the vision host; Rewind contradicts both.
4. **Web page speech recognition goes to the browser vendor.** The default `stt=browser` uses the Web Speech API. In
   Chrome that is generally Google's server recognition; not confirmed on a primary page today (Chrome's privacy
   whitepaper did not render). Safari's behaviour was not checked.
5. **Rewind can answer from another call.** `for_question` falls back to the newest call with clips when the
   current call has none (`server/rewind.py:449`), and the HTTP search takes any `session_id` (`server/rewind_api.py:35`).
   On a shared demo server one visitor could search the last visitor's clips.
6. **The expert can use Fable 5.1**, a Covered Model: at least 30 days of retention, no ZDR, for long or "research"
   questions (`server/expert.py:59`). Its web searches send model-written queries, which may contain user words.
7. **Cloudflare sees the traffic** through the Tunnel (implied by its TLS design, not stated outright), and keeps
   Access logs with the sign-in email for 24 hours to 180 days by plan.
8. **No ZDR anywhere** unless someone signs it: Anthropic keeps 30 days, Cartesia and TwelveLabs do not state a period.

## Recommended product changes

| Change | Status |
|---|---|
| Rewind off by default, with an on-screen notice | **Built** (`client-web/agent.js:197`, `server/rewind.py:26`) |
| Cloud brain sees crops only, never full frames; size and area caps | **Built** (`server/crops.py`, `server/llm.py:133`) |
| Logs carry metadata only, hashed ids and email | **Built** (`server/logs.py:8`, `server/auth.py:105`) |
| One-tap **Private mode**: local brain, no cloud vision crops, Kokoro instead of Cartesia, Rewind off and locked, server STT forced | Proposed |
| Make `LOCAL_ONLY=1` also block Cartesia and Rewind, and fix the `AGENTS.md` wording | Proposed |
| Rewind deletes its TwelveLabs videos at call end, and on "Forget" (voice or button); delete the index on a schedule as a backstop | Proposed |
| Rewind searches only the caller's own call; drop the newest-call fallback and bind HTTP search to the signed-in session | Proposed |
| Opt out of training on the TwelveLabs account settings and the Cartesia data-controls form; record the date here | Proposed (account action, owner) |
| No transcript logging, enforced by a test that greps log output for the question text | Partly built: no transcript logging found; the enforcing test is proposed |
| Private mode never picks a Covered Model (Fable) for the expert | Proposed |
| Ask Anthropic for ZDR on the non Covered Models | Proposed (account action) |
