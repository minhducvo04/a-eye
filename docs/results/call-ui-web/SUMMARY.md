# Call UI verification

Base: local main `2c7a8bf`, fast-forwarded with `git merge main`.
The pre-existing UI edits were restored and all four conflicts resolved. No UI commit was made.

Test: node --test client-web/ - PASS (167 passed, 0 failed, 0 skipped).
Test: node --test client-web/turn.test.mjs - PASS (17 passed).
Test: browser smoke - PASS (4 viewports; 0 page errors; 12 screenshots).
Test: git diff --check - PASS.

Browser command:
```
$HOME/.cache/uv/archive-v0/hcY8qU8TLWbqDTHje52_-/bin/python client-web/call-ui-smoke.py $HOME/Projects/a-eye/.venv/bin/python
```

The final browser run is recorded in [browser-smoke.log](browser-smoke.log).
Viewports: 390x844, 768x1024, 1280x844, 844x390.
Verified: exact slogan/security line; two start buttons (Call and Settings); two-line slogan;
no launcher overflow; keyboard Settings and Call; sequential verb entry and reduced-motion final state;
real local /ws2 hello with General and camera off; mock response; End call visible after 3.2 seconds;
no phone camera button or Cartesia setting; hold-to-talk press/release; Rewind/keep wire messages and reset;
synthetic camera frames; stream released at call end.

| Width | Start | Call | Settings |
| --- | --- | --- | --- |
| 390 | [Start](after-start-390.png) | [Call](after-call-390.png) | [Settings](after-settings-390.png) |
| 768 | [Start](after-start-768.png) | [Call](after-call-768.png) | [Settings](after-settings-768.png) |
| 1280 | [Start](after-start-1280.png) | [Call](after-call-1280.png) | [Settings](after-settings-1280.png) |
| 844 landscape | [Start](after-start-844.png) | [Call](after-call-844.png) | [Settings](after-settings-844.png) |

The 390 and 1280 start/call captures and the 768 start were visually inspected after the final polish.
Existing before-* captures are inherited evidence, not captures of the final source.

Limits: Chromium with an isolated real local mock server, synthetic media, Google opted out and
LOCAL_ONLY=1; external browser requests blocked. This proves UI and local transport, not real cloud
voice, TwelveLabs storage, Safari, or physical-device behavior. No real media was stored.
The task's smoke owns the one-Call UI; the older scripts/browser_start_smoke.py still targets the retired
mode picker and was not changed in this client-owned package.
