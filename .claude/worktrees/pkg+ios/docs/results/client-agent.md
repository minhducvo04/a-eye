# client-agent

The call page is `client-web/agent.html` (`/agent.html`). It speaks WebSocket `/ws2` with the v2 messages: pack hello, 1 fps `v2_frame` (long side 640, JPEG 0.7, newest only), typed and browser-speech text, barge-in, draw ops, presence, and a dismissible shopper card.

## Files

- `client-web/agent.html`
- `client-web/agent.js`
- `client-web/agent.css`
- `client-web/draw.js`
- `client-web/presence.js`
- `client-web/draw.test.mjs`
- `client-web/presence.test.mjs`
- `RESULT.md`

`voice.js` is loaded with a dynamic import. If that module is missing, the page still sends typed text. `contracts/` and the existing call page were not edited.

## Limits

No real browser, camera, mic, or iPhone was tested. Drawing and presence were checked as pure functions in Node. The live camera, microphone, speech, WebSocket, and small-screen layout were not exercised in a browser. `voice.js` was not in this worktree, so the mic path is untested here. Server `/ws2` was not running.

Test: node --test client-web/ - PASS (22 pass, 0 fail)
