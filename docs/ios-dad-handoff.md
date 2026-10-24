# iPhone app: growth flow handoff

The growth flow works end to end on the web (`client-web/`) and the server does all the logic. The app needs the screens. Keep the existing API routes; the server now owns the growth rules.

**Goal:** A-eye helps people practice until they need fewer hints. It supports independence and human relationships. After a task, sharing is offered only when the user has explicitly added a consenting contact. The person can be a friend, sibling, relative or coach. No contact means no suggestion or composer.

## What to build (keep the existing design and components)

1. **Start:** the growth flow as the first screen, a calm "What are we fixing?" with **Sink** first.
2. **Talks back:** level 1 speaks full steps; level 2 speaks one short hint, then waits; level 3 stays quiet during practice. Safety stops and valve checks never fade. A turn can finish without speech.
3. **Guide attention without distracting:**
   - a box and a small arrow on the live camera, pointing at the target, from the box data the server already sends (the memory-aid boxes);
   - a soft pulse only when a step starts;
   - a thin "Step 2 of 5" line;
   - respect Reduce Motion.
4. **Valve card:** "Checking the valve...", then "Water is off", or "Show me again".
5. **Want to show someone? card (hidden until a contact exists):** the note text, read aloud, with Send and Cancel. Saying "send" also works.
6. **Reply bubble:** the recipient's reply, shown and read aloud.
7. **Proof strip, small:** Pictures saved, Pictures sent, Cloud AI calls.

## How the server talks to the app

Start: send the pack `home` in `hello` (contract enum, see `contracts/schema.json`), or the user says "sink".

Signals arrive as `turn` messages; read `detail`:

| `detail` | Show |
|---|---|
| `Home: sink` | The Sink flow is active |
| `Valve: checking` | Valve card: "Checking the valve..." |
| `Valve: closed` | "Water is off" |
| `Valve: unsure`, a failed or cancelled stage, or `Stopped by code` | "Show me again" |
| `Valve: test closed` | "TEST MODE" label (presenter laptop only, never on phones) |
| `Stopped by code` | The safety stop label |
| `Brain: ...` | The small brain label |
| `Home: complete` | Open “Want to show someone?” only if a contact exists |

A new `received` stage starts a new turn; clear the stale valve state then (see `client-web/step-check.js`, 37 lines).

**Sharing (REST, same auth as the rest of `/api/`):**
- `GET /api/family?session_id=...` returns contacts, tasks, replies, `pictures_sent`, `cloud_ai_calls`, and the latest draft.
- `POST /api/family/contact {name, relation, consent}` adds a person. The user adds contacts; there are no defaults.
- `POST /api/family/draft {log, contact}` returns the note (at most 3 sentences, ending with a question).
- `POST /api/family/heard {id}` is sent after the note has been read aloud.
- `POST /api/family/send {id, confirmation}` sends after the tap or the spoken "send".

The recipient answers on a private web page from the link; the app only shows the reply. Reference: `client-web/family-note.js` (164 lines).

**Important (from the security review):** read the note and the reply through the same voice path the app uses for A-eye's own speech, so the echo filter ignores it. Otherwise a reply like "stop" can be heard by the mic as a command. Keep the mic input ignored until that speech ends.

## Run and test

1. Start the server on the Mac: `make dev`. Phone and Mac on the same Wi-Fi.
2. In the app's gear sheet, set the server (`192.168.x.x:8000`) and the token (see `ios/AEye/SETUP.md`).
3. Choose Private, then Sink. On a phone the valve step stays on "Show me again" until the checker is trained on real valve photos. That is expected and safe.

Details: `docs/results/dad-flow.md`, `home-fix.md`, `step-check.md`, `family-note.md`.

## Growth commands and storage

“Walk me through it” restores full steps for the current task without bypassing safety checks. “Forget my progress” deletes all task progress for the authenticated user and resets guidance. No new API or contract fields are needed: send these as ordinary final user text or speech.

The local growth log records UTC date, task, tries, elapsed minutes, spoken hint sentences, safety-stop flag and completion. It uses the local-memory encryption key; without a key it stays in process memory and is lost at restart. Only completed runs advance levels. The end of a run may include one numeric comparison, never invented praise. The log measures guide use, not proof of a completed physical repair.
