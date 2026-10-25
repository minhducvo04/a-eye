# Recall pipeline: cut in the background, cache on the call, upload on the fly or at save

2026-10-25, branch `pkg/recall-pipeline`. Server side only; no UI change. Verified with fakes and a local ffmpeg run
only. No real TwelveLabs call was made, so the timings below for TwelveLabs come from the 2026-10-24 live audit, not
from this branch.

## Answer

- **Keep "process on the fly" as the default.** Per-segment upload costs the same as the old 60 s batch, because
  every clip was already its own TwelveLabs video. Only *when* it is sent changes. Clips become searchable in about
  11 to 20 s after the event instead of 35 to 70 s.
- **"Process when I save"** holds clips in server memory for the whole call. They are uploaded at call end only if
  the existing "Keep clips after the call" flag is on, and dropped otherwise. You get no in-call cloud search in
  this mode.
- **No media file on our host any more.** Clips and the recap video are encoded to MP4 in memory (ffmpeg stdin to
  stdout, fragmented MP4) and uploaded from bytes. Before, a temp MP4 went to `$TMPDIR` for each clip.
- **Status polls back off.** The first poll comes after 6 s, then 3, 3, 3, 6, 12 and 24 s. That is 2 to 4 polls per
  clip instead of 4 to 6, with no added latency for a clip ready in 7 to 15 s.
- **Not done tonight:** caching segments on the user's device (browser or iOS). That needs client code and a
  different cutter (see below).

## Where segments are cut today

| Step | Where | Notes |
|---|---|---|
| Camera frames | client (web `client-web/agent.js` `FRAME_MS = 1000`, iOS `ClientMessage.swift`) | JPEG over `/ws2`, about 1 fps |
| Ring buffer (2 s pre-roll + 12 s) | server memory, `Rewind.add_frame` | sampled at most 4 fps |
| Clip cut (scene change, local motion) | server, `Rewind.observe` / `keyframe` | 4 to 12 s, at most 60 per call |
| Encode MP4 | server, `encode_mp4` | **was** a temp file on disk; **now** stdout bytes |
| Upload + index | TwelveLabs `POST /tasks`, poll `GET /tasks/{id}` | marengo3.0 visual |
| Kept frames for pointing | server memory, 6 per clip | dropped at Forget |
| Kept-call index | `data/.../rewind_kept.json` | video ids and times only, no media |

The client never cuts segments. The server owns the cutter because it already has the keyframe gate, which decides
where a moment starts.

## What can move to the client tonight

- **Browser: not tonight.** `MediaRecorder` can record fixed 10 s WebM segments and keep them in memory or
  IndexedDB. But it would need a new upload message, a server pass-through to TwelveLabs (the API key must stay on
  the server), and fixed-length cuts instead of change-triggered ones. That is a UI and client change plus a
  contract change: too big for the time left.
- **iOS: not tonight.** `AVAssetWriter` segments work the same way, and the same upload path is missing.
- **Realistic tonight (built):** "not persisted on our host". Raw frames and MP4s live only in the call's server
  memory and go straight to TwelveLabs or get dropped. A host crash loses them; nothing is left on disk.

## Segment length

Unchanged: 2 s before the change plus 3 s after, extended by continued motion up to 12 s. A new event after 2.5 s of
quiet starts a new clip. The minimum is 4 s, because TwelveLabs needs 4 s per video (`encode_mp4` pads the last
frame). Fixed 10 s segments would only matter for a client-side cutter.

## The two modes (built)

| | Process on the fly (`live`, default) | Process when I save (`save`) |
|---|---|---|
| How to pick | `REWIND_MODE=live` or `/ws2?rewind_mode=live` | `REWIND_MODE=save` or `/ws2?rewind_mode=save` |
| During the call | each clip is uploaded in the background as soon as it closes | clips held in server memory, nothing uploaded |
| Past-moment search in the call | yes, once a clip is indexed | no cloud search; it says so ("processed only when you save it"); local memory still answers |
| Call end, kept | the rest is uploaded, ids recorded (unchanged) | every clip is uploaded, indexed and recorded for later calls |
| Call end, not kept | cloud videos deleted (unchanged) | clips dropped; nothing ever left the host |
| Memory held | 6 frames per uploaded clip | every frame of every clip until the end: about 12 frames x 60 clips x about 60 KB, so about 45 MB worst case per call at 1 fps |

The mode is a `/ws2` query setting so the frozen hello schema stays the same, as for `mode=gemini-live`. "Keep" is
the existing `rewind.keep` flag from the "Keep clips after the call" checkbox.

### UI needed (for the owner's yes, not built)

One radio pair in Rewind settings next to "Keep clips after the call": "Search during the call (uploads as it
goes)" and "Upload only if I save the call". The web client would add `&rewind_mode=save` to the `/ws2` URL. With
"save", the keep checkbox becomes the save question at call end ("Save this call's clips?"). Without the toggle,
the server uses `REWIND_MODE`.

## Cost per minute

Prices: [TwelveLabs overage pricing](https://www.twelvelabs.io/overage) (fetched 2026-10-25): Marengo 3.0 Index
Search $4 per 1,000 queries ($0.004 each), Pegasus 1.6 Analyze video input $1.75 per hour ($0.029 per minute of
video), storage $0.065 per GB-month. [Plans and allowances](https://docs.twelvelabs.io/docs/get-started/plans-and-billing/plans-allowances-and-overage):
video embedding is billed by duration, rounded up to the second for each event. **The Marengo indexing rate per
minute is not printed on either page.** It sits inside the plan's workload allowance. Status polls are not a
billed operation; they only count against the rate limit.

Assume a busy hands-on minute: about 6 clips of about 6 s, 2 questions.

| Item | Real TwelveLabs (from the pages) | Our meter (`TWELVELABS_REQUEST_USD`, $0.10 per non-DELETE request) |
|---|---|---|
| Indexing about 36 s of video | allowance, rate not published; per-segment rounding adds at most 1 s per clip | 6 uploads = $0.60 |
| Status polls, old (poll at 0 s, then every 3 s; ready at 7 to 15 s) | free | 4 to 6 per clip = $2.40 to $3.60 |
| Status polls, new (6, 3, 3, 3, 6, 12 s...) | free | 2 to 4 per clip = $1.20 to $2.40 |
| 2 searches | $0.008 | $0.20 |
| Storage of 6 clips (about 300 KB each) | about $0.0001 per month | 0 |
| Recap (Pegasus) over about 30 s of kept frames, if asked | about $0.015 | $0.10 |
| **Metered total per busy minute** | | **old about $3.20 to $4.40; new about $2.00 to $3.20** |

The meter, not the provider, is the expensive part: polls are 75 to 82 % of the metered TwelveLabs spend, and the
provider does not bill them. Backoff cuts that by about a third. The real fix is to price `GET /tasks/{id}` at $0
in `cloud_meter.request_cost`. That is a budget call, so it is left for the owner.
"Save" mode does not save money when the call is kept. It saves everything when the call is not kept.

## Latency (live mode, expected; not measured on the real API)

A clip closes 3 s after the last change (up to 12 s). Encode and upload take about 1 to 2 s, and indexing 7 to 15 s
(audit). The status is seen within 3 s of ready. So a clip is searchable about **11 to 20 s after the event**,
against 35 to 40 s in the audit (60 s flush) and 65 to 70 s for a call's first clip. `REWIND_FLUSH_S` now defaults
to 0 (upload as cut); set it to batch again. Uploads now run in the background, so the frame sampler no longer
stalls during an upload.

## What changed (code)

- `server/rewind.py`: `recall_mode()`, `poll_delays()` (`REWIND_POLL_S`), `encode_mp4(frames) -> bytes`,
  `TwelveLabsClient.upload(index_id, video_bytes, metadata)`, and `Rewind.recall_mode`, `uploads_live()`,
  `flush_soon()` and `close_due()`. `follow()` uploads each clip as it is cut, in live mode only. `answer()` and
  `recap_call()` do not upload in save mode. The recap is encoded in memory. The public search API
  (`search`, `search_kept`, `answer`, `search_past`, `recap_call`) is unchanged.
- `server/ws2.py`: sets the call's mode from `?rewind_mode=`.
- `conftest.py`: `REWIND_POLL_S=0` in tests, and `REWIND_MODE` / `REWIND_FLUSH_S` cleared.
- Tests: `server/test_recall_pipeline.py` covers both modes, the no-disk rule (real ffmpeg, with file writes and
  temp files trapped) and the backoff.

## Risks

- **Fragmented MP4 is not yet proven against TwelveLabs.** ffprobe reads it as valid H.264 MP4 (480x360, 5.0 s).
  TwelveLabs says it accepts FFmpeg-decodable files, but no real upload was made. Check one real upload before the
  demo. If it is rejected, the upload fails and the clip shows `failed`.
- Save mode holds up to about 45 MB per call in server RAM, and a crash loses the call's clips (by design).
- ffmpeg's own process could write temp files. The test checks that cwd and `TMPDIR` stay empty, but it cannot see
  every path the process might use.
