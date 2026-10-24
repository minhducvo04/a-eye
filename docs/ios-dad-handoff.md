# iPhone app: dad flow handoff

The dad flow works end to end on the web (`client-web/`) and the server does all the logic. The app needs the screens. Nothing in the server needs to change.

**Goal:** "A-eye can't be your dad. It helps you do the thing, then brings you back to the people who love you." The user fixes a dripping sink with A-eye watching, and A-eye then offers to send a short note to a parent.

## What to build (keep the existing design and components)

1. **Start:** the dad flow as the first screen, a calm "What are we fixing?" with **Sink** first.
2. **Talks back:** every step is spoken through the existing voice path, one step at a time.
3. **Guide attention without distracting:**
   - a box and a small arrow on the live camera, pointing at the target, from the box data the server already sends (the memory-aid boxes);
   - a soft pulse only when a step starts;
   - a thin "Step 2 of 5" line;
   - respect Reduce Motion.
4. **Valve card:** "Checking the valve...", then "Water is off", or "Show me again".
5. **Tell Dad? card:** the note text, read aloud, with Send and Cancel. Saying "send" also works.
6. **Reply bubble:** the parent's reply, shown and read aloud.
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
| `Home: complete` | Open the Tell Dad? card |

A new `received` stage starts a new turn; clear the stale valve state then (see `client-web/step-check.js`, 37 lines).

**Family note (REST, same auth as the rest of `/api/`):**
- `GET /api/family?session_id=...` returns contacts, tasks, replies, `pictures_sent`, `cloud_ai_calls`, and the latest draft.
- `POST /api/family/contact {name, relation, consent}` adds a person. The user adds contacts; there are no defaults.
- `POST /api/family/draft {log, contact}` returns the note (at most 3 sentences, ending with a question).
- `POST /api/family/heard {id}` is sent after the note has been read aloud.
- `POST /api/family/send {id, confirmation}` sends after the tap or the spoken "send".

The parent answers on a private web page from the link; the app only shows the reply. Reference: `client-web/family-note.js` (164 lines).

**Important (from the security review):** read the note and the reply through the same voice path the app uses for A-eye's own speech, so the echo filter ignores it. Otherwise a reply like "stop" can be heard by the mic as a command. Keep the mic input ignored until that speech ends.

## Run and test

1. Start the server on the Mac: `make dev`. Phone and Mac on the same Wi-Fi.
2. In the app's gear sheet, set the server (`192.168.x.x:8000`) and the token (see `ios/AEye/SETUP.md`).
3. Choose Private, then Sink. On a phone the valve step stays on "Show me again" until the checker is trained on real valve photos. That is expected and safe.

Details: `docs/results/dad-flow.md`, `home-fix.md`, `step-check.md`, `family-note.md`.
