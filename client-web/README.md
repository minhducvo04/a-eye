# client-web

Static Safari call page for A-eye. No build step and no npm packages. The server is meant to serve this folder at `/`.

## What it does

- Opens `ws://` or `wss://` on the same host at `/ws` and sends `hello` (`board_id` `demo-b650`, `mode` `live`, `client` `web`).
- **Start camera** calls `getUserMedia` from the tap (iOS Safari will not start the camera on page load). The video element is `playsinline`, `muted`, and `autoplay`, with the back camera (`facingMode: "environment"`, ideal 1280×720, no audio).
- If the page is not a secure context (`window.isSecureContext`: HTTPS or localhost), or the camera is blocked, the page says so. **Upload photo** still sends one `photo`.
- Live mode (`client-web/live.js`) sends a JPEG `frame` at 2 fps max. The long side is at most 640 px, quality 0.7, with `seq`, `ts_ms`, `w`, `h`, and `orientation`. It waits for a server message whose `seq` is at least the one just sent, or 1.5 s, and it skips a tick when `bufferedAmount` is above 0. Hiding the tab pauses the loop. **Pause** / **Resume** does the same until you tap again.
- A small line shows frames sent in the last second, the last round-trip in milliseconds, and the socket state.
- **Send photo** sends one `photo` from the current camera frame. **Power is off** and **Check again** send `confirm`.
- The video uses `object-fit: cover`. Overlay boxes are normalized 0..1 of the sent frame and drawn through that cover crop. A box for an older `seq` is ignored. The drawing clears 3 s after the last overlay.
- Speaks `say` with `speechSynthesis` through `speak(text)` until Cartesia audio arrives. Shows `step`, a green/red/`Can't tell` `verdict`, and `error` text.

Frames are not stored: no `localStorage`, no downloads, no logging of the JPEG payload.

## Run

From the repo, start the orchestrator (`make server`) and open `http://localhost:8000`. To look at the page alone:

```sh
python3 -m http.server 8000 --directory client-web
```

The socket stays down until something listens on `/ws`. The red status dot means the socket is closed. Localhost counts as a secure context, so the laptop camera can start there.

## iPhone Safari

Safari on an iPhone only exposes the camera on a secure page. `http://` to a LAN address is not enough. `http://localhost` works on the computer that is serving the page, not on the phone.

From the machine that is already serving port 8000, Tailscale can put HTTPS in front of it:

```sh
tailscale serve 8000
```

A public URL from the same tool:

```sh
tailscale funnel 8000
```

A Cloudflare quick tunnel is the other easy option:

```sh
cloudflared tunnel --url http://localhost:8000
```

Open the `https://` URL in Safari on the phone, tap **Start camera**, and allow the camera. **Pause** stops frames; leaving the tab does too. If you deny the camera, use **Upload photo**.

## Test

```sh
node --test client-web/
```

The Node tests cover overlay scaling, the cover-crop map, stale-overlay clearing, and the frame scheduler with a fake clock. They do not open Safari, a camera, or a WebSocket.
