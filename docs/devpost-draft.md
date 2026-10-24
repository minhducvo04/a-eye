# A-eye: Devpost draft (memory aid)

Draft for the Devpost page. A humanizer pass comes later. Every number here is copied from a repo doc; the
sources are listed in the comment at the end. Unfinished work is marked **(in progress)**.
Built does not mean verified on a physical device.

## Inspiration

Everyone loses their keys. For a person with early memory loss, it happens more often. Each search can end in
worry, or in a call to the family member who helps them.

A camera answer alone was not enough for what we wanted. We wanted a quiet memory of where things were put,
a way to show the moment they were seen, and a way to forget them on request.

We wanted a helper for the home that does those three things. It assists. It does not diagnose or treat.

## What it does

A-eye is a video call with an AI that sees, points and talks back.

- **Ask where something is.** "Where are my keys?" A-eye finds the moment it saw them. It shows that earlier
  frame with the keys boxed and the time, next to the live camera view with an arrow to where they are now. It
  says the answer out loud, for example "Your keys are in the blue bowl, where they live."
- **It says when it is not sure.** If our own vision model cannot confirm the object in the frame, A-eye says
  "I'm not sure I saw it" and gives its best guess.
- **Forget that.** With local memory, this deletes the item just discussed: its notes, crops and tag.
  "Forget today" also works. With Rewind alone, Forget deletes this call's clips and clears the clip count.
- **Private mode.** The listed server paths stay on our machines: the local brain, Kokoro and our speech
  recognition run there, and Rewind is locked off. Tunnel traffic still goes through Cloudflare.
- **Cloud switches.** Settings has separate Claude, Cartesia and TwelveLabs switches and a "What leaves your
  home" panel. Private mode turns all three off for the call.
- **Calm memory voice.** The Memory pack speaks in short, calm sentences. It gives the same answer to a
  repeated question. It never says "you already asked". For "did I take my pill?" it gives one fixed line and
  asks the person to check the box or their caregiver. It never gives dosing advice.
- **A caregiver page.** The person and caregiver both consent to local memory. The page saves tags, rooms,
  keep-days and a stop switch on the server. A tag can say "the keys live in the blue bowl". Local memory
  refuses bedrooms and bathrooms. Rewind is a separate opt-in and has no room filter.
- **Memory across calls.** Notes and tagged object crops stay on the home server. Crops from frames with
  people are not stored. A later call can find the item. Spoken dates across days are unit-tested only.
- **Phone camera and mic.** A phone can pair by code or QR. The code and QR were shown; a real phone join was
  not verified. "Remember this phone" lets a phone signed in to the same account join the next call without
  a new code. Keep its camera page open.
- **Shopping help.** The helper reads the product from the local scene, ranks offers in code and shows prices,
  delivery and links. Compatibility stays unverified. Private mode and the Claude switch block lookup.
  Tests used supplied offers; live cloud shopping was not verified.

A-eye has no face recognition and does not identify people.

## How we built it

- **Two loops.** A slow loop sends a camera frame to vision on our own GPU box (Qwen 3.5 9B, Qwen 2.5-VL 7B as
  fallback) about once a second. A fast loop in the browser tracks the drawn boxes and arrows between updates.
- **Three Claude roles.** Claude Haiku 5.5 gives short answers from text only. Claude Sonnet 5.5 plans what to draw
  and sees one small crop at most, never the full frame. Claude Opus 5.5 or Fable 5.1 handles rare hard questions.
  The expert may also see a small crop.
- **A trained router.** A small classifier on EmbeddingGemma embeddings decides per question: answer from the
  live view (now), search earlier footage (past), or call the expert. It runs on the Mac CPU. It is off by
  default. With `ROUTER=on`, it labels the question before memory or Rewind. Regex is the fallback when the
  router is off or unsure.
- **Memory.** Rewind keeps short silent clips around scene changes and searches them with TwelveLabs Marengo.
  It is off by default. Our own vision model double-checks each hit before A-eye claims it.
- **Voice.** Cartesia Sonic 3.6 over a WebSocket, one context per turn, cancelled when the person cuts in.
  The web default is browser speech recognition. Whisper on our box handles server speech recognition,
  used in Private mode or when a mic is picked in Settings. It can return partial results while a person talks.
- **Clients.** A web call page and a native iPhone app (SwiftUI) speak the same message contract. Every message
  is defined once in a JSON Schema. A native Vision Pro client uses photos instead of a live camera.
- **Vision Pro browser demo.** Safari can use the paired phone for camera input and speech. Replies play on
  the headset. Drawings appear on a dark canvas because the server does not relay the phone picture.
  Chromium emulation was checked; physical Vision Pro Safari still needs a run.
- **Device client.** A headless camera client starts on a button press or local motion. Private mode is on by
  default. A synthetic turn passed on a Mac against a real local server. It has not run on a Raspberry Pi.
- **Hosted open-model brain.** `BRAIN=openai_compat` selects a hosted text-only API for the talker, planner and
  expert. Private mode or the Claude switch blocks hosted calls. The adapter is built and tested with a fake
  provider. No hosted provider was contacted, and costs are unknown.
- **Readiness check.** `make ready` reports PASS, FAIL or SKIP with fixes. It checks services, models, pairing,
  the device mock turn and the simulator build. The recorded run passed with skips for authenticated status
  and pairing, Access settings and cloud keys. It does not prove a physical device works.
- **Team.** A small human team worked with AI coding agents: Claude in Claude Code coordinated and built most
  packages, Codex built several core packages. Every change had one owner, its own tests and a human push.

## Challenges we ran into

- **Being sure.** Video search returns a rank, not a score, so a weak match can still rank highest. We added a
  check by our own vision model and an "I'm not sure" answer. The latest keys rehearsal found the keys with a box.
  Audio started 0.34 to 0.61 s after the
  question in the reported Rewind runs, using a TwelveLabs stand-in. The older unboxed guess was before the fix.
- **A loud hall.** Crowd noise started fake turns and cut off replies. We added a minimum speech duration before
  anything is sent, and a longer barge-in rule in a loud room.
- **Privacy that holds in code.** An earlier `LOCAL_ONLY` switch stopped Claude but not the cloud voice or
  Rewind. Private mode now covers all of them.
- **Deletion you can trust.** Rewind clips used to stay in TwelveLabs. Now A-eye deletes the call's videos at
  call end and on Forget, and a call can only search its own clips. We tested the delete against a stand-in; a
  live run is **(in progress)**.

## Accomplishments that we're proud of

- The trained router scored 96% on our 100-question held-out set, at 43 ms on the Mac CPU and $0 per call.
  The same agent wrote the generation prompt and held-out labels; these were not Duc's questions.
- Local memory found the keys in a later call in 751 ms, using synthetic frames and real local vision.
- The TwelveLabs training opt-out is done. The owner also submitted Cartesia's training opt-out form.
  Both apply going forward, not to earlier data.
- First audio about 1 second after the last audio chunk (1008 ms, synthetic speech), with partial speech
  recognition and Cartesia.
- A full local path: with the local brain, first audio came at a median of 1630 ms, against 3290 ms with the
  Claude Sonnet brain in the same test.
- Forget works end to end in rehearsal: the clip count went to 0 and the delete call was made (against our
  TwelveLabs stand-in; the live delete has not been run yet).
- Hard rules live in code, not only in prompts: the pill line, no dosing, crop size limits, Private mode.
  The caregiver page refuses bedrooms and bathrooms.

## What we learned

- Speed and "it sees" are table stakes. What matters is what the assistant remembers, what it shows as proof,
  and what it forgets.
- "I'm not sure" is a feature. A calm best guess is safer than a confident wrong answer.
- Privacy words must match the code. We wrote down exactly what leaves our machines and fixed the gaps we found.
- A small trained router came close to Claude Haiku at picking the route (96% against 97% on our held-out
  set of 100 questions), in 43 ms instead of 803 ms, with no API charge. The same agent wrote the generation
  prompt and held-out labels. These were not Duc's questions.

## What's next

- Verify spoken dates across days in real calls. Local memory and "forget today" are built; multi-day date
  wording has only unit tests.
- A measured find rate: hide an item under one of three cups many times, count right, wrong and "can't be
  sure" **(in progress)**.
- Talk with caregivers and clinicians. We have not done that yet; it is our next step after the event.
- A reminder in the person's own voice, recorded with their consent, using Cartesia voice cloning
  **(in progress)**.
- Ask Anthropic about zero data retention. The Cartesia and TwelveLabs training opt-outs are done.

## Built with

Python, FastAPI, WebSocket, JavaScript, HTML, CSS, Swift, SwiftUI, Claude Haiku 5.5, Claude Sonnet 5.5,
Claude Opus 5.5, Fable 5.1, Cartesia Sonic 3.6, TwelveLabs Marengo, TwelveLabs Pegasus, Qwen 3.5 9B, Qwen 2.5-VL 7B,
Whisper, Kokoro, EmbeddingGemma, Ollama, Cloudflare Access, Cloudflare Tunnel, Tailscale, Playwright, JSON
Schema.

## 2-minute demo script

Setup: a phone on a stand points at a table with three cups. The laptop shows the call page on the projector.
Normal mode (Cartesia voice), Memory pack, Rewind on. Private mode off.

| Time | On screen | Said |
|---|---|---|
| 0:00 to 0:08 | The call, three cups on the table | "This is A-eye. It helps you find things you put down, and it forgets when you ask." |
| 0:08 to 0:20 | A judge hides the keys under one cup while the phone watches | "Go ahead, hide the keys under any cup." |
| 0:20 to 0:35 | The cups get shuffled back into a row; the call keeps running | "Now we talk about something else for a moment." |
| 0:35 to 0:42 | The judge asks "Where are my keys?" | The question, by voice |
| 0:42 to 0:58 | The split answer: the earlier frame with the keys boxed and its time, next to the live view with an arrow to the cup | A-eye answers in the calm voice, about a second after the question. If it is not sure, it says so and gives its best guess. |
| 0:58 to 1:10 | The judge lifts the cup | "It shows you the moment it saw them, and where they are now." |
| 1:10 to 1:22 | The person says "forget that"; the count drops to 0 | A-eye: "Done. I deleted 1 clip of this call." (the number is whatever was kept) |
| 1:22 to 1:38 | Settings, Private mode on; the green Private badge in the call pill; ask a question | "Private mode keeps the call's AI on our machines. Kokoro speaks. Cloudflare still carries tunnel traffic." |
| 1:38 to 1:52 | Private mode off; ask again | "Cartesia gets only the reply sentence. Frames stay on our GPU unless Rewind is on. With Rewind on, silent clips go to TwelveLabs." |
| 1:52 to 2:00 | The caregiver page | "Both consent to local memory. Settings save here. Rewind is separate. A-eye assists. It does not diagnose." |

Notes for the run:

- The boxed keys answer passed in the latest rehearsal with a TwelveLabs stand-in. It is not a live
  TwelveLabs result. If the stage answer is unsure, keep it in and say so. A real phone join still needs verification.
- Use Rewind without local memory attached for this script. Then "forget that" deletes the call's clips.
  With local memory attached, it deletes the item just discussed instead.
- Run the main demo in normal mode. Private mode switches Cartesia off, so show it only for its own beat.

## Prize paragraphs

**Cartesia.** Voice is how a person with memory loss uses A-eye. They talk, and it talks back while it points.
Cartesia Sonic 3.6 streams each answer over one WebSocket per call, one context per turn, and A-eye cancels it
the moment the person cuts in. First audio came about 1 second after the last audio chunk (1008 ms,
synthetic speech). The Memory pack uses a gentle Cartesia voice and calm, short sentences. Limits we state
plainly: Private mode uses Kokoro instead of Cartesia, and the latency was measured with synthetic speech, not a
person in the hall. A reminder in the person's own cloned voice is **(in progress)**.

**Microsoft: Built for the Real World.** A-eye is a memory aid a family could set up at home: a phone on a
stand, a caregiver page with two consents, refused private rooms for local memory, a keep-for setting and a stop switch. It
admits doubt instead of guessing with confidence. With Rewind alone, Forget deletes the call's clips locally
and asks TwelveLabs to delete them. That delete was tested against a stand-in.
We measured what we could: the router's accuracy and speed, voice latency, and the local brain against the cloud
brain. Caregiver settings save on the server. The find-rate measurement over many hides is **(in progress)**.

**Anthropic.** A-eye is for adults with early memory loss living at home, and the family member who helps
them. Claude Haiku 5.5 answers from text: the question, recent chat and a scene note. Claude Sonnet 5.5
plans the drawing. Claude Opus 5.5 or Fable 5.1 handles rare hard questions. The planner and expert may see
one small crop, never the full frame. We wrote down where Claude could go wrong and
guarded each case in code: a confident wrong location (our vision model checks the hit, and A-eye says "I'm not
sure"), medical questions (a fixed pill line and no dosing advice), and data sent to Claude (text and small crops,
blocked by Private mode). Anthropic's commercial terms say it may not train on this content. We have not yet spoken with a
caregiver; that is our next step.

**Best People-First Hack.** A-eye is built around the person, not the camera. It speaks calmly, repeats the
same answer to a repeated question, and never says "you forgot". It assists and does not diagnose or treat. It
has no face recognition. Local memory needs both consents and refuses bedroom and bathroom rooms. Rewind is a separate opt-in
and has no room filter. "Forget that" deletes the item just discussed in local memory, or this call's clips
when only Rewind is attached.

<!--
Sources for claims and numbers in this draft:
- Router 96%, Haiku 97%, 100 held-out questions, 43 ms vs 803 ms, Mac CPU, $0 router calls, and the same-agent
  labels caveat (not Duc's lines): docs/results/router-train.md. Its unwired status is superseded by
  docs/results/demo-rehearsal.md, "Router first, and ten more runs". Off unless ROUTER=on: docs/privacy.md.
- 1008 ms (about 1 second) to initial audio, synthetic speech, partial STT, Sonic 3.6, socket/context and
  cancellation: README.md, "Voice: Cartesia", and docs/voice-options.md.
- 1630 ms vs 3290 ms audio medians: docs/results/wave6-turn-latency.md.
- Model names and versions, local vision, Claude roles, Fable 5.1, embeddings and hosted open-model adapter:
  docs/model-choices.md. Text-only Haiku, crop-only planner/expert images: docs/privacy.md.
- Hosted adapter fake-provider checks, no live provider, unknown costs, privacy gates, make ready checks,
  actual PASS/SKIP limits and no physical-device proof: docs/results/ready.md.
- Caregiver server saving, two consents, tags and homes, rooms, keep-days, stop, local notes and tagged crops,
  person-frame exclusion, later-call search, 751 ms synthetic two-call result, Forget scopes, and unit-only
  multi-day dates: docs/results/memory-aid.md; built status: docs/features.md.
- Private mode's listed server paths, Cloudflare tunnel caveat, three cloud switches, What leaves your home,
  browser STT default and server Whisper conditions: docs/privacy.md, "What A-eye sends where (code)".
- Training opt-outs: docs/privacy.md, "Gaps and honest risks", items 1 and 2. TwelveLabs account opt-out done;
  Cartesia form submitted by the owner. Both apply going forward. The opening summary there is stale.
- Anthropic commercial no-training terms and the unresolved retention request: docs/privacy.md.
- Rewind silent clips, off by default, Marengo search, rank without score and vision check:
  docs/results/rewind.md. Separate Rewind switch and no room filter: docs/privacy.md;
  local-only room restrictions: docs/results/memory-aid.md.
- Boxed keys rehearsal and 0.34 to 0.61 s to audio: docs/results/demo-rehearsal.md, latest single run
  and later plain Rewind batch. TwelveLabs was a stand-in. Forget cleared clips and called delete.
- Rewind deletion scope and live-delete limitation: docs/privacy.md. Script's sample deleted-clip count
  is illustrative and must match the actual reply; see docs/results/demo-rehearsal.md.
- Split answer and memory count: docs/features.md; blue-bowl spoken example: docs/results/memory-aid.md.
- Phone code/QR shown but no real join: docs/features.md. Remembered phone with the same verified identity:
  contracts/CHANGELOG.md v2.9; keeping the camera page open: docs/headset-demo.md.
- Native Vision Pro photo client: docs/features.md. Browser mode, paired phone mic, headset audio, dark canvas,
  Chromium-only check and pending physical Safari run: docs/headset-demo.md.
- Headless device, button/motion, Private default, synthetic Mac/local-server proof and no Pi run:
  docs/device.md, docs/results/device.md.
- Shopping scene input, ranking, offers sheet, unverified compatibility, privacy gates and no live cloud search:
  docs/results/shopping.md.
- Memory voice and medical refusals: docs/privacy.md. No face recognition/person tagging:
  docs/results/rewind.md; local person-frame crop exclusion: docs/results/memory-aid.md.
- Speech floor and loud-room barge-in: existing draft's source commit 7e1b07c; no duration claimed here.
- Two loops and about one vision frame per second: README.md, "Architecture".
- Client contract and team roles: docs/build-credits.md, docs/features.md, contracts/schema.json.
- Three cups: docs/results/memory-aid.md. The two-minute script and its timestamps are the retained demo
  schedule from this repo's previous draft, not measured performance. Its audio estimate is supported by
  docs/voice-options.md. Future cup trials and interviews are plans, not claimed results.
To verify before submitting: re-check each "(in progress)" item; run the real TwelveLabs delete before
saying "deleted in TwelveLabs" on stage. Run the pending humanizer pass before submission.
-->
