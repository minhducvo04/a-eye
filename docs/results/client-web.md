# RESULT: client-web

Safari call page skeleton. Static files only (no build, no npm). Messages follow `contracts/schema.json` v1.

## Files changed

- `client-web/index.html`
- `client-web/call.js`
- `client-web/overlay.js`
- `client-web/style.css`
- `client-web/overlay.test.mjs`
- `client-web/README.md`
- `RESULT.md`

## Limitations

- `node --test` covers overlay math and a fake canvas context. It does not open a browser, a camera, or a WebSocket.
- Chrome was installed, but headless launch from this session died before a screenshot (sandbox could not open the Chrome app / Crashpad). The page was fetched over HTTP (`200` from `python3 -m http.server`) and the HTML includes the video, canvas, step card, caption, three buttons, upload input, and status dot. Safari on iPhone, a laptop camera, `getUserMedia`, JPEG `frame`/`photo` sends, button clicks, `speechSynthesis`, and a live `/ws` server were not exercised.
- Layout at 375px is styled for wrapping and `overflow-x: hidden`. It was not measured in a viewport.
- `speak(text)` uses `speechSynthesis` only. iOS may ignore speech that does not start from a tap. Cartesia audio is not wired. The optional overlay `diagram` image is not drawn. Mic audio is not sent.
- Frames are encoded in memory for the socket send and then dropped. Nothing is written to `localStorage` or downloaded by this page.

Test: node --test client-web/ - PASS (4 pass, 0 fail, 0 skipped)

Commit: not created. `git add` failed with `Unable to create '$HOME/Projects/a-eye/.git/worktrees/client-web/index.lock': Operation not permitted`. The files above are in the worktree and unstaged.
