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
