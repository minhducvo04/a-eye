# A-eye: Devpost draft (memory aid)

Draft for the Devpost page. A humanizer pass comes later. Every number here is copied from a repo doc; the
sources are listed in the comment at the end. Anything not on `main` yet is marked **(in progress)**.

## Inspiration

Everyone loses their keys. For a person with early memory loss, it happens more often. Each search can end in
worry, or in a call to the family member who helps them.

Assistants that can see are common now. They answer questions about the camera view. But they do not keep a
quiet memory of where things were put. They do not show the moment they saw something. They do not forget when
you ask.

We wanted a helper for the home that does those three things. It assists. It does not diagnose or treat.

## What it does

A-eye is a video call with an AI that sees, points and talks back.

- **Ask where something is.** "Where are my keys?" A-eye finds the moment it saw them. It shows that earlier
  frame with the keys boxed and the time, next to the live camera view with an arrow to where they are now. It
  says the answer out loud, for example "Seen 2:10 ago, in the blue bowl."
- **It says when it is not sure.** If our own vision model cannot confirm the object in the frame, A-eye says
  "I'm not sure I saw it" and gives its best guess.
- **Forget that.** Say "forget that" or tap Forget. A-eye deletes this call's clips and says how many it
  deleted. The "Remembering N things today" count on screen goes to 0.
- **Private mode.** One switch keeps the whole call on our own machines: the local brain answers, Kokoro speaks
  on our GPU box, and memory search in the cloud stays off.
- **Calm memory voice.** The Memory pack speaks in short, calm sentences. It gives the same answer to a
  repeated question. It never says "you already asked". For "did I take my pill?" it gives one fixed line and
  asks the person to check the box or their caregiver. It never gives dosing advice.
- **A caregiver page.** Both people give consent. The caregiver tags things and their homes ("keys -> blue
  bowl"), picks the rooms A-eye may remember (bedrooms and bathrooms are always refused), and sets how long
  memory is kept. A switch stops remembering at once. The page is built; saving it on the server is
  **(in progress)**.
- **Any phone is the camera and mic.** A phone on a stand in the kitchen can pair with the call by code or QR.
  It sends the camera and the mic; the laptop plays the voice.

A-eye has no face recognition and does not identify people.

## How we built it

- **Two loops.** A slow loop sends a camera frame to vision on our own GPU box (Qwen 3.5 9B, Qwen 2.5-VL 7B as
  fallback) about once a second. A fast loop in the browser tracks the drawn boxes and arrows between updates.
- **Three Claude roles.** Claude Haiku 5.5 talks first with short answers. Claude Sonnet 5.5 plans what to draw
  and sees one small crop at most, never the full frame. Claude Opus 5.5 is a rare expert for hard questions.
- **A trained router.** A small classifier on EmbeddingGemma embeddings decides per question: answer from the
  live view (now), search earlier footage (past), or call the expert. It runs on the Mac CPU.
- **Memory.** Rewind keeps short silent clips around scene changes and searches them with TwelveLabs Marengo.
  It is off by default. Our own vision model double-checks each hit before A-eye claims it.
- **Voice.** Cartesia Sonic 3.6 over a WebSocket, one context per turn, cancelled when the person cuts in.
  Whisper on our box turns speech into text, with partial results while the person is still talking.
- **Clients.** A web call page and a native iPhone app (SwiftUI) speak the same message contract. Every message
  is defined once in a JSON Schema.
- **Team.** A small human team worked with AI coding agents: Claude in Claude Code coordinated and built most
  packages, Codex built several core packages. Every change had one owner, its own tests and a human push.

## Challenges we ran into

- **Being sure.** Video search returns a rank, not a score, so a weak match can still come first. We added a
  check by our own vision model and an "I'm not sure" answer. In our latest rehearsal of the keys demo the answer
  was a best guess, not a sure find, and the hit frame had no box. Making that answer sure and boxed is
  **(in progress)**.
- **A loud hall.** Crowd noise started fake turns and cut off replies. We added a 400 ms speech floor before
  anything is sent, and a longer barge-in rule in a loud room.
- **Privacy that holds in code.** Our first `LOCAL_ONLY` switch stopped Claude but not the cloud voice or
  Rewind. Private mode now covers all of them.
- **Deletion you can trust.** Rewind clips used to stay in TwelveLabs. Now the call's videos are deleted at call
  end and on Forget, and a call can only search its own clips.

## Accomplishments that we're proud of

- The trained router labels questions correctly 96% of the time on a held-out set, in 43 ms, at no cost per call.
- First audio about 1 second after the last audio chunk (1008 ms, synthetic speech), with partial speech
  recognition and Cartesia.
- A full local path: with the local brain, first audio came at a median of 1630 ms, against 3290 ms with the
  Claude Sonnet brain in the same test.
- Forget works end to end in rehearsal: the clip count went to 0 and the TwelveLabs delete was called.
- Hard rules live in code, not only in prompts: the pill line, no dosing, crop size limits, Private mode.
  The caregiver page refuses bedrooms and bathrooms.

## What we learned

- Speed and "it sees" are table stakes. What matters is what the assistant remembers, what it shows as proof,
  and what it forgets.
- "I'm not sure" is a feature. A calm best guess is safer than a confident wrong answer.
- Privacy words must match the code. We wrote down exactly what leaves our machines and fixed the gaps we found.
- A small trained router came close to Claude Haiku at picking the route (96% against 97% on our held-out
  set), in 43 ms instead of 803 ms, and for free.

## What's next

- Memory across days, kept in the home, with "forget today" **(in progress)**.
- Saving the caregiver settings on the server **(in progress)**.
- A measured find rate: hide an item under one of three cups many times, count right, wrong and "can't be
  sure" **(in progress)**.
- Talk with caregivers and clinicians. We have not done that yet; it is our first step after the event.
- A reminder in the person's own voice, recorded with their consent, using Cartesia voice cloning
  **(in progress)**.
- Opt out of training at Cartesia and TwelveLabs on our accounts, and ask Anthropic about zero data retention.

## Built with

Python, FastAPI, WebSocket, JavaScript, HTML, CSS, Swift, SwiftUI, Claude Haiku 5.5, Claude Sonnet 5.5,
Claude Opus 5.5, Cartesia Sonic 3.6, TwelveLabs Marengo, TwelveLabs Pegasus, Qwen 3.5 9B, Qwen 2.5-VL 7B,
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
| 1:22 to 1:38 | Settings, Private mode on; the green Private badge in the call pill; ask a question | "Private mode keeps everything on our own machines. The voice you hear now is Kokoro on our GPU box." |
| 1:38 to 1:52 | Private mode off; ask again | "Cloud on: now Cartesia speaks. Only the sentence it speaks goes to Cartesia. The camera frames stay on our GPU." |
| 1:52 to 2:00 | The caregiver page | "A caregiver sets it up with the person, and both agree first. A-eye assists. It does not diagnose." |

Notes for the run:

- The confident, boxed answer at 0:42 is **(in progress)**: our latest rehearsal gave a best guess without a box.
  If it is still a best guess on the day, keep it in and say so; that is the honest behaviour.
- Run the main demo in normal mode. Private mode switches Cartesia off, so show it only for its own beat.

## Prize paragraphs

**Cartesia.** Voice is how a person with memory loss uses A-eye. They talk, and it talks back while it points.
Cartesia Sonic 3.6 streams each answer over one WebSocket per call, one context per turn, and A-eye cancels it
the moment the person cuts in. First audio came about 1 second after the last audio chunk (1008 ms,
synthetic speech). The Memory pack uses a gentle Cartesia voice and calm, short sentences. Limits we state
plainly: Private mode uses Kokoro instead of Cartesia, and the latency was measured with synthetic speech, not a
person in the hall. A reminder in the person's own cloned voice is **(in progress)**.

**Microsoft: Built for the Real World.** A-eye is a memory aid a family could set up at home: a phone on a
stand, a caregiver page with two consents, refused private rooms, a keep-for setting and a stop switch. It
admits doubt instead of guessing with confidence. Forget deletes the call's clips, locally and in TwelveLabs.
We measured what we could: the router's accuracy and speed, voice latency, and the local brain against the cloud
brain. The find-rate measurement over many hides and server storage for the caregiver settings are
**(in progress)**.

**Anthropic.** A-eye is for adults with early memory loss living at home, and the family member who helps
them. Claude Haiku 5.5 answers from what the camera saw, as text, with at most one small crop. Claude Sonnet 5.5
plans the drawing. Claude Opus 5.5 handles rare hard questions. We wrote down where Claude could go wrong and
guarded each case in code: a confident wrong location (our vision model checks the hit, and A-eye says "I'm not
sure"), medical questions (a fixed pill line and no dosing advice), and data leaving the home (crops only,
Private mode). Anthropic's commercial terms say it may not train on this content. We have not yet spoken with a
caregiver; that is our next step.

**Best People-First Hack.** A-eye is built around the person, not the camera. It speaks calmly, repeats the
same answer to a repeated question, and never says "you forgot". It assists and does not diagnose or treat. It
has no face recognition. The person and the caregiver both agree before it remembers anything, bedrooms and
bathrooms are never remembered, and "forget that" deletes this call's clips.

<!--
Sources for every number and claim (repo at main c9fb212, 2026-10-24):
- 96% held-out, 43 ms on the Mac CPU, $0 per call; Haiku tool choice 97% at 803 ms p50: docs/results/router-train.md (n = 100, held-out set written by
  the same agent as the generation prompt; noted there).
- 1008 ms first audio with Cartesia Katie, synthetic speech; Sonic 3.6, one context per turn, cancel on barge-in,
  one socket per call: README.md, "Voice: Cartesia".
- 1630 ms vs 3290 ms first audio median, local brain vs Claude Sonnet brain: docs/results/wave6-turn-latency.md.
- Qwen 3.5 9B and Qwen 2.5-VL 7B on the GPU box, Haiku talker, Sonnet planner with crops only, Opus expert,
  EmbeddingGemma router, Whisper partials, Kokoro: docs/model-choices.md.
- Crop limits, Anthropic "may not train", 30-day deletion, Cartesia and TwelveLabs train unless opted out:
  docs/privacy.md (dated before Private mode and Rewind deletion landed; its "Proposed" rows for those are stale).
- Rewind: silent clips around scene changes, Marengo search, off by default, vision double-check, rank and no
  score: docs/results/rewind.md.
- Keys rehearsal: best guess not sure, no box on the hit frame, forget set clips to 0 and called the TwelveLabs
  delete, "Done. I deleted 1 clip of this call.": docs/results/demo-rehearsal.md.
- Private mode (local brain, Kokoro, Rewind cloud locked, green Private badge): commit 9c5b4f2; screenshots
  docs/ui-parity/badge-private-390.png.
- Rewind deletion at call end and on Forget, own call only: commit 6078b85; spoken "forget that": commit 722a745.
- Memory pack rules (pill line, no dosing, same answer to a repeat, no "you already asked", gentle Cartesia
  voice): commit 58cbe9c.
- 400 ms speech floor and loud-room barge-in: commit 7e1b07c.
- Split answer, "Seen 2:10 ago", count badge, caregiver page (server storage not on main, preview only):
  commit 29dfc06, docs/ui-parity/memory-*.png.
- Phone as camera and mic: commit 098be75, docs/ui-parity/phone-mic-*.png; build-credits.md lists it.
- Team and agents: docs/build-credits.md.
- No face recognition: none in the code; docs/results/rewind.md tested with no faces and no person tagging.
To verify before submitting: re-check each "(in progress)" item against main; update docs/privacy.md so the
privacy claims here have a current doc behind them.
-->
