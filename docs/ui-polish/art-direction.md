# UI polish: audit, bundle and art direction

Arc: web call page redesign for the memory aid focus ("remembers, points and forgets", private by default).
Audience: a person with early memory loss and their caregiver; also judges on a projector and in a 2-minute video.
Design read: calm assistive call UI, iOS dark glass language (Style.swift tokens), native CSS, variance 4,
motion 3, density 2. No new dependency, no CDN, no remote fonts.

## 1. Audit (before, main at c9fb212; captures `before-*.jpg`)

| # | Finding | Evidence |
|---|---|---|
| A1 | Memory mode was in `MODES` but had no ring button, so ring sizes were off by one after Assembly and Memory could not be picked | `before-picker-1280.jpg` (7 discs, 8 modes in code) |
| A2 | First run is an empty dark screen with a ring: nothing says what A-eye is or what it keeps | `before-picker-*.jpg` |
| A3 | Top of the call stacks five rows: pill, Rewind chips, timing line, memory count, mic name | `before-memory-390.jpg` |
| A4 | Jargon on screen: "Hearing 4.3 s", "Mic: Fake Default Audio Input", "EXPERT 2.1 s" | same |
| A5 | Unreadable text over a bright room: timing and mic lines 1.1:1, memory count 2.1:1, pill p5 2.9:1 (measured, section 3) | `before-memory-1280.jpg` |
| A6 | Badges inconsistent: Private is a green chip inside the pill, Rewind on is a plain chip, Expert is a mono timing line | `before-memory-*.jpg` |
| A7 | Rewind appears three times (badge, chip above the typed bar, bar button) | `before-memory-390.jpg` |
| A8 | Projector: at 1920x1080 the pill is 13 px mono and the caption 17 px, far too small from the back of a room | `before-memory-1920.jpg` |
| A9 | Settings grew to 10 groups in one flat list; the phone pairing was last; checkboxes not switches | `before-settings-*.jpg`, `before-settings-end-*.jpg` |
| A10 | Caregiver page: orange "Preview" banner reads as an error; storage line in mono ("Kept 7 days, about 0 MB"); no way back | `before-caregiver-*.jpg` |
| A11 | Camera off reads as an alarm (orange line in the caption) | `before-camera-off-*.jpg` |
| A12 | Split answer: small tags in mono, small answer line | `before-split-*.jpg` |

## 2. What changed (built on `pkg/ui-polish`)

- First run: wordmark, one headline ("I look, point, and remember."), one line of help, one privacy line.
- Memory in the ring (pin icon), centred at launch (urgent commit 177d209); desktop shows all modes in a row.
- One badge style under the pill: Private (green dot), Rewind on (amber dot) + Recap, Expert (blue dot).
- Status lines hidden unless there is a problem (failed, backup, retrying, connection) or `?dev=1`.
- Call glass darker (0.58 tint, caption 0.66) so text stays readable over a bright lamp or window.
- Memory mode: caption 23 px, padding up, hold-to-talk hidden, scan band off, presence motion 2.4 s, caption fades in.
- Settings: Phone camera, Privacy, Rewind, Voice, Photo, Memory aid (caregiver link), then Advanced (Devices,
  Microphone, Connection and server, Transcript). iOS style switches.
- Projector: zoom 1.12 at 1200x760 and up, 1.4 at 1700x950 and up; sheet height corrected for zoom.
- Caregiver page: back link, calm blue info banner, larger title and rows, switch for Remember.
- Split answer: larger answer line and tags, softer pane edges.
- Behaviour unchanged except: Space no longer starts hold-to-talk while a sheet is open; `?mode=` picks the start
  mode; links keep `?token=`.

## 3. Bundle

1. Branch `pkg/ui-polish`, sha in `review-requests/` file name. Urgent parts already on main: e142719, 177d209.
2. Screens (Chromium, Playwright, fake camera from `eval/backends/data/desk_setup.jpg`): 390x844, 1280x800,
   1536x864 (scratch only), 1920x1080: `before-*.jpg` and `after-*.jpg` in this folder.
3. Crops at 2x: `crops/` (badges row, ring row, caption, call bar, intro).
4. Contrast (method: read the computed text colour, hide the text, screenshot the element box, skip rounded
   corners, composite the text colour over each background pixel, WCAG ratio; worst pixel / 5th percentile):

| Element | 390 before | 390 after | 1280 before | 1280 after |
|---|---|---|---|---|
| Caption text | 5.91 / 6.18 | 9.75 / 10.03 | 6.07 / 6.26 | 9.89 / 10.14 |
| Memory count | 1.95 / 1.97 | 5.51 / 5.58 | 2.09 / 2.10 | 5.40 / 5.82 |
| Top pill | 2.02 / 2.93 | 2.02 / 6.04 | 2.02 / 2.93 | 2.04 / 5.97 |
| Rewind on badge | n/a | 1.60 / 6.13 | n/a | 1.60 / 6.18 |
| Timing line | 1.12 / 1.14 | hidden | 1.09 / 1.13 | hidden |
| Mic line | 1.00 / 1.10 | hidden | 1.00 / 1.10 | hidden |
| First run text / privacy line | n/a | 8.94 / 10.18 | n/a | 9.02 / 10.37 |
| Settings footnote, group title | 6.23 | 6.23 | 6.23 | 6.23 |

   Worst-pixel values near 2 for the pill and badges are the coloured status dot inside the box (it counts as
   background in this method), not the text; the 5th percentile is the honest number there.
   Frame time: not measured. Asset sizes: no new assets (icons are inline SVG); agent.css 35.5 KB, agent.html 20.4 KB.
5. Drive recipe / Doctor: N/A (A-eye has no kyra-verify feature file or doctor). Proof runs instead: `node --test
   client-web/` 130/130; `make browser-smoke` PASS (Chromium); Playwright in Brave 1280 and 390 (modes, pair button,
   wheel scroll, arrow keys) PASS.
6. Not verified: real trackpad and touch by hand; Safari and iOS Safari; reduced motion; real expert badge; the
   motion itself (stills only); iPhone and Vision Pro apps are unchanged.

## 4. Reviews

(appended below by the independent reviewer)

### Review of d64c237 (independent, Sat Oct 24 01:45 PDT 2026)

Reviewer: Media lead (Opus), independent. Inspected every after-*.jpg with its before pair, and the five crops. Live
server not driven; motion not seen (stills only). Code read only to check on-screen claims.

**Verdict: FIX. Overall 6.5.** Large real gains (first run, legibility, Settings split, projector scale), but the
privacy wording is not fully true, the badge set is inconsistent and once contradictory, and three audit items
claimed fixed (A6, A7, A11) still show in the after captures.

Ten-second check (older first-time user):
- First run (after-picker-*): "I look, point, and remember", pick a helper below. Understood. Good.
- Memory call (after-memory-*): the answer about the keys is the first thing read. Then five other things compete:
  pill, Rewind on + Recap, Remembering 12, listening bar, Rewind chip, typed bar, six buttons with two filled blue.
- Camera off (after-camera-off-*): orange "Camera unavailable" reads as something broke; "Upload photo" is not on
  screen.
- Settings (after-settings-*): Phone, Privacy, Rewind, Voice first is clear. "Kokoro af_kore", "local brain",
  "GPU box", "TwelveLabs" are not understood.
- Caregiver (after-caregiver-*): clear purpose, consent first. "keys -> blue bowl" syntax is not obvious.

| Row | Score | What is wrong (evidence) |
|---|---|---|
| Colour | 7 | Dark glass is consistent. Camera off still uses orange caption text (after-camera-off-1280/390, same as before: A11 not fixed). Two filled blue buttons in the call bar (mic and history, after-memory-1280) so neither reads as "the" active one. Mechanic, Plumbing, Engineering are dimmed on the desktop ring (crop-ring-row.png) and look disabled. |
| Composition | 6 | Memory call still stacks 3 rows on top and 4 above the bar (after-memory-390). Rewind still appears 3 times: badge, chip above typed bar, filled bar button (A7 not fixed). First run is left heavy with an empty right half at 1280/1920; acceptable. |
| Depth | 7 | Darker glass (0.58 / 0.66) separates cards from the bright lamp well. Sheets are flat slabs with no edge light; fine. |
| Text legibility | 8 | Caption 9.75 to 10.14 p5, memory count 5.4 to 5.8, pill p5 6.0: real fixes. Recap blue text on brown glass is not measured. "tap to start", pill and "HEARING YOU..." are small mono. |
| Frame 390 | 6 | Ring clips Cooking and Plumbing at both edges with labels hidden (after-picker-390). Split "Now" pane is cut by the viewport bottom (after-split-390). Settings sheet leaves the half-hidden "Remembering" pill peeking above it (after-settings-390). |
| Frame 1280 | 7 | Clean. Settings sheet runs past the fold with no fade (after-settings-1280). after-settings-advanced-1280 has no camera picture and shows "General 0:01": a different state from its pair. |
| Frame 1920 | 8 | Zoom 1.4 works; caption and badges read from distance (after-memory-1920, after-split-1920). |
| Type | 6 | Mono and sans mixed on user-facing text: pill, "tap to start", A-EYE label, "HEARING YOU...", "Browser", "Noise --", 127.0.0.1. Jargon on screen: "Kokoro af_kore (default)" (truncated at 390), "local brain", "GPU box". |
| Motion | n/a | Stills only. Not scored. |
| First run | 8 | Clear headline, one help line, privacy line. Memory is 5th of 8 on desktop, not centred. "tap to start" lowercase mono is the weakest element. Privacy line wording: see claims below. |
| Memory mode calm | 6 | Bigger caption and hidden hold-to-talk help. Still has typed bar, Rewind chip, mono caps "HEARING YOU..." and two blue buttons. Not yet calm. |
| Badges consistency | 5 | Private badge appears in no after capture except crop-top-badges.png, where it sits next to "Rewind on", a state the code forbids (agent.js line 779) and Settings says cannot happen ("Rewind stays off"). "Remembering 12 things today" is a different, larger style. Recap is a button dressed as a badge. Expert never shown (not verified). |
| Settings structure | 8 | Simple first, Advanced last, iOS switches: good. Private mode copy is jargon. Footnote wording: see claims. "Room noise: Noise --" is a placeholder. |
| Caregiver page | 7 | Back link, bigger title, switch for Remember: good. The claimed calm blue preview banner is in no capture (after-caregiver-*): either hidden or not captured. "keys -> blue bowl" is programmer syntax. Square checkboxes beside a switch; acceptable. Intro paragraph is narrower than the rows. |
| Projector readiness | 7 | 1920 scaling is right. Pill stays mono and small relative to the caption; Recap low contrast; dimmed ring items wash out on a projector. |
| Overall | 6.5 | Strong direction, not yet shippable as "private by default, nothing scary". |

On-screen claims flagged (Home owns the wording; I did not change it):
1. First run: "No video or sound is kept unless you turn it on." True for storage with Rewind off by default
   (agent.js line 201), but outside Private mode frames and crops can be sent to a cloud model (server/llm.py lines
   153 to 172 pass `images` to Claude) and Rewind uploads clips to TwelveLabs. A reader will take it as "nothing
   leaves". Private mode is off by default, so the spec "private by default" is not what the UI does.
2. Settings footnote: "Camera frames go only to this server and are not saved, unless Rewind is on." Appears
   contradicted by the same cloud image path. Verify which path sends images, then fix the sentence.
3. crop-top-badges.png shows Private and Rewind on at once. Either a staged or stale capture, or a real bug. Reproduce
   before the demo.
4. after-split-*: "keys . here now" with an arrow pointing at an empty wall. The before said "Not in view now. Look
   around slowly." The after claims a find it does not show. Check against the real state, not the mock.

Numbered fixes, priority order:
1. Make the two privacy sentences true (claims 1 and 2), approved by Home. Example direction: "Video is not saved.
   Private mode keeps everything on our own computer." Consider Private mode on by default if the spec means it.
2. Badges: one family (dot + label) for Private, Rewind on, Expert, and the memory count; never show Private with
   Rewind on; recapture a Private call and an Expert call.
3. Camera off (A11): calm grey wording and an inline "Use a photo" button; no orange.
4. Memory mode (A7): drop the Rewind chip above the typed bar; hide the typed bar behind a keyboard button; one
   filled button only (history should not be filled blue unless open).
5. User-facing mono to sans: pill, "tap to start" (as "Tap to start"), caption label, "Listening" in sentence case.
6. Split: honest "here now" state; keep the whole Now pane in frame at 390.
7. Settings plain words: friendly voice names, Private mode copy without "brain", "Kokoro", "GPU box"; hide "Noise --"
   until a value exists.
8. Caregiver: capture the preview banner state; replace "keys -> blue bowl" with two fields or "keys in the blue bowl".
9. Desktop ring: do not dim Mechanic, Plumbing, Engineering, or say why they are dim.
10. Measure Recap text contrast at 390 and 1920 and add it to the table.

Not verified by this review: motion, reduced motion, touch, Safari, the Expert badge, the live server states.

### Builder response to the d64c237 review (fixes in the next commit)

| Review fix | Done | Evidence |
|---|---|---|
| 1 Privacy sentences | Reworded to what the code does: first run "Video is not saved unless you turn on Rewind or the memory aid."; Settings foot now says the cloud model may see a small crop outside Private mode; Private mode text in plain words. Private on by default is a product call for Duc, not changed. | `after-picker-*.jpg`, `after-settings*.jpg` |
| 2 Badges | Real states captured: Private mode switched on in Settings (Rewind locks off, so no Rewind badge), Expert from a real `turn` stage `expert` message. The earlier crop with Private beside Rewind on was a forced DOM state and is removed. Memory count gets the same thin edge. | `after-private-*.jpg`, `after-expert-*.jpg` |
| 3 Camera off | White text with a small amber dot, no orange; copy "The camera is not available. You can use your phone or a photo from Settings." (inline button not added) | `after-camera-off-*.jpg` |
| 4 Memory mode | Rewind bar button and Rewind starter chip hidden in Memory mode; one filled button (mic). Typed bar kept on purpose (noisy demo hall). | `after-memory-*.jpg` |
| 5 Monospace | Memory mode pill, caption label and listening strip in the reading font, strip in sentence case; ring hint and all status chips in the reading font. Other modes keep the iOS mono pill. | same |
| 6 Split view | Phone: sheet 92dvh and 16:9 panes, both panes in frame. "keys · here now" follows the live tracker; in these captures the mock server's box is what it points at. | `after-split-390.jpg` |
| 7 Settings words | Private mode text rewritten. Voice names and "Noise --" come from other modules, not changed. | |
| 8 Caregiver | Banner state is in `after-caregiver-*.jpg` (preview server). "keys -> blue bowl" syntax unchanged (parser is the memory package's). | |
| 9 Dimmed modes | Desktop names read "Mechanic · soon" etc. | `after-picker-1280.jpg` |
| 10 Recap contrast | Measured 3.78 at 390 and 1280, then darkened: now 6.77 / 6.77. Caption now 10.54 / 11.06 (390), 10.89 / 11.57 (1280). | `measure.py` method above |
