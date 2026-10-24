# Eval

Replays held-out frames through the vision service and writes an accuracy table for the demo.

```sh
python -m eval.run --manifest <path> --vision-url http://127.0.0.1:8001
python -m eval.run --manifest <path> --vision-url http://127.0.0.1:8001 --split all --out eval/out
```

The manifest is a JSON list. Each case has `case_id`, `split` (`train` or `heldout`), `board_id`, `image` (a path relative to the manifest), `task` (`identify`, `locate`, or `verify`), `header`, `item`, `pins`, and `truth`. The default split is `heldout`.

`truth` is `{"item"}` for identify, `{"bbox": [x, y, w, h]}` for locate, and `{"pass": bool}` for verify. A locate case with no bbox means the header is not in the frame. A locate hit needs IoU of at least 0.3, or both sides say not found.

The harness reads each image, base64-encodes it, and POSTs `/identify`, `/locate`, or `/verify`. Requests and responses are checked with `contracts.validate`. Rows record `case_id`, `task`, `header`, `expected`, `got`, `correct`, `conf`, and `ms`.

An abstention is `abstain: true`, or a locate response with `found: false` and `blur: true`. Abstentions are never correct. Accuracy for a task and header is correct answers divided by answers that were not abstentions. The abstain rate is abstentions divided by all rows in that group. `Wrong plugs caught` counts verify cases whose truth is `pass: false` and whose answer is `pass: false`, excluding abstentions.

Outputs, both gitignored:

- `eval/out/<git short sha, or local>.csv`
- `eval/out/table.md` (one row per task and header, plus the wrong-plug count)

`eval/sample/manifest.json` is three held-out cases. It points at jpeg names only. Tests write those bytes in a temp directory. Do not commit frames. Real clips stay outside the repo, for example `~/a-eye-private/clips/`.

```mermaid
flowchart LR
  manifest[manifest and local jpg] --> run[eval.run]
  run -->|POST base64 JSON| vision[vision service]
  vision --> run
  run --> table[csv and table.md]
```
