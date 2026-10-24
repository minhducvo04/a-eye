# client-web

Static Safari call page for A-eye. No build step and no npm packages. The server is meant to serve this folder at `/`.

## What it does

- Opens `ws://` or `wss://` on the same host at `/ws` and sends `hello` (`board_id` `demo-b650`, `mode` `live`, `client` `web`).
- Shows the back camera full screen with a canvas overlay. If the camera is blocked, **Upload photo** still sends one `photo`.
- Live mode sends a JPEG `frame` about once a second (max width 640). **Send photo** sends one `photo` from the current camera frame.
- **Power is off** and **Check again** send `confirm`.
- Draws `overlay` boxes, an arrow, and pin dots. Speaks `say` with `speechSynthesis` through `speak(text)` until Cartesia audio arrives. Shows `step`, a green/red/`Can't tell` `verdict`, and `error` text.

Frames are not stored: no `localStorage`, no downloads, no files written by this page.

## Run

From the repo, start the orchestrator (`make server`) and open `http://localhost:8000`. To look at the page alone:

```sh
python3 -m http.server 8000 --directory client-web
```

The socket stays down until something listens on `/ws`. The red status dot means the socket is closed.

## Test

```sh
node --test client-web/
```

`overlay.test.mjs` checks scaling, clamping, role colors, and drawing against `contracts/examples.json`. Camera, Safari, and the live socket are not covered by that command.
