# Eval package

The held-out harness is in place. `python -m eval.run` reads a local manifest, posts each image as base64 to `/identify`, `/locate`, or `/verify`, checks the body with `contracts.validate`, and writes `eval/out/<git short sha>.csv` plus `eval/out/table.md`.

## Files changed

- `eval/run.py`
- `eval/table.py`
- `eval/sample/manifest.json`
- `eval/test_eval.py`
- `eval/README.md`
- `RESULT.md`

## Limitations

- Accuracy is correct answers divided by non-abstentions. Abstentions stay in `n` and in the abstain rate, and they are never marked correct. A group that only abstained has a blank accuracy.
- A locate abstention is `found: false` with `blur: true`. Glare alone is not an abstention unless the response sets `abstain: true`.
- A locate truth with no bbox means the header is not in the frame. IoU of 0.3 or more is a hit. `ms` and `conf` come from the vision response.
- Identify requests send the closed allowed-parts list unless the case sets `candidates`.
- Wrong plugs caught counts verify cases with truth `pass: false` and answer `pass: false`, and it skips abstentions.
- The sample manifest names three jpegs and does not contain them. Tests write those bytes in a temp directory. Real clips stay outside the repo.
- The full suite was also run: `.venv/bin/python -m pytest -q` — 48 passed in 0.16s.
- The commit did not land. `git add` cannot create `$HOME/Projects/a-eye/.git/worktrees/eval/index.lock` (operation not permitted). This worktree's git metadata lives outside the writable workspace. The files are untracked on `pkg/eval` and ready to stage:

```sh
git add RESULT.md eval/README.md eval/run.py eval/table.py eval/test_eval.py eval/sample/manifest.json
git commit -m "Add the held-out vision accuracy harness."
```

Test: .venv/bin/python -m pytest -q eval - PASS (7 passed in 0.17s)
