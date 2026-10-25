# Vision Pro dad-guide demo

Fastest path: Safari on the headset (`client-web`) with the phone as camera. Do not install the visionOS app for this run. Regular visionOS apps cannot read the main camera; the web page never opens a headset camera.

Keep `?device=headset` in the URL. Vision Pro Safari can identify itself as a Mac.

## What you should see

After Sink or General starts and the phone joins:

- a large caption of what A-eye is saying
- a step card (`SINK` or `GENERAL`) with the current instruction
- a box and arrow on the dark canvas when the server draws
- a large red end-call button that stays on screen

The phone picture is not relayed back to Safari. Drawings sit on a dark canvas.

## 1. Start the server (Mac)

From this repo, with dependencies already installed:

```sh
make mock
```

That serves `client-web` at `http://127.0.0.1:8000` with canned vision. For a real home brain and speech, use `make server` instead (needs the vision service on `:8001`).

Phone and headset cameras need HTTPS. After `A_EYE_TOKEN` or Cloudflare Access is configured:

```sh
make phone
```

Then run the printed Tailscale Serve command yourself. Open the HTTPS host it prints, not localhost, on the headset and the phone.

## 2. Headset (Vision Pro Safari)

1. Open `https://<the A-eye hostname>/agent.html?device=headset`.
2. If the server uses a token, add `&token=<A_EYE_TOKEN>` (do not paste the token into chat or logs).
3. Sign in with the same account as the phone if Access is on.
4. Optional: Settings → turn **Private mode** on for the sink guide.
5. Tap **Sink guide** (dad-guide) or **Call** (General). Phone and desktop show only **Call**.
6. Tap **Enable sound** so Safari may play the reply.
7. If the phone does not join on its own, tap **Pair phone · show QR**.

## 3. Phone camera

Leave the phone on a stand, pointed at the sink or object.

- **Remembered phone:** keep the A-eye camera page open. If it reloaded, tap **Start**. Keep **Always use this phone as my camera** on.
- **QR pair:** scan the headset QR, tap **Start**.

The headset status becomes **Phone camera connected**. The phone is then the camera and the mic.

## 4. Run Sink

1. The step card should read **SINK** with the first instruction (or “Show the sink. Say next when you are ready.”).
2. Ask on the phone, or type `next` in the headset field, to walk the shutoff steps.
3. Watch the caption, the step card, and any box/arrow on the canvas.
4. The valve card may stay on **Show me again** until the checker has real valve photos. That is expected.
5. Pinch **End call** when finished.

## 5. Run General

1. Start a new call by tapping **Call**.
2. Enable sound if asked.
3. Point the phone at an object and ask “what am I looking at?”
4. Read the **GENERAL** step card and the caption. A box and arrow appear when the server grounds a visible object.
5. End the call.

## Missing for a good demo

- Live phone video on the headset (server would need to relay frames or at least frame size).
- A real Vision Pro Safari run (Chromium UA emulation is not device proof).
- Gaze and pinch checks on the large controls.
- Main-camera frames in the native visionOS app (Apple enterprise entitlement).
- A trained valve checker; presenter test mode is laptop-only (`LOCAL_ONLY=1`).
- Step numbers (`Step 2 of 7`) from the server; the card shows the spoken line.
- Overlay aligned to the phone picture (drawings stretch across the window).
- Remembered-phone join through Access, verified on a headset.
- Spatial window placement; this is a Safari window, not an immersive space.
