# A-Eye: "Dad, how do I?"

A call with an AI dad who watches the camera and talks with his son through Gemini Live voice.
Build an Arduino LED circuit, read resistor bands, check LED polarity, use a multimeter, or learn to tie a tie, with guidance and boxes on named objects.

## What is code vs what is a model

1. **Model:** [Gemini Live](server/gemini_live.py) sees the camera and voices Dad, with Google consent.
2. **Code:** [Electronics](server/packs/electronics.py) and [tie](server/packs/tie.py) guides own the steps and progression; the model phrases the current instruction.
3. **Code:** [Hazard stops](server/safety.py) and pack rules interrupt Gemini and speak fixed warnings for recognized hazards.
4. **Both:** A vision model locates a named object; [code](server/pointer.py) checks freshness, confidence and box geometry before drawing.
5. **Both:** A [time-scope decision model](router/scope.py) selects when to look; [memory code](server/live_memory.py) retrieves evidence and handles missing results.
6. **Both:** The background planning team combines a [model planner](server/planner.py), context gathering and a coded plan checker; [Dad's parts shelf](server/parts_shelf.py) supplies curated cards linked to the team's Apify-scraped products.

## How a call flows

Explore the [live 3D system map](https://aeye.minhducvo.com/map.html), also served locally at `/map.html`.

1. Open `/agent.html` and call Dad. With Google consent and a configured Gemini key, the browser sends microphone audio and downscaled camera frames through the server to Gemini Live. See the [wire protocol](docs/api.md).
2. Recognized hazards take priority. Coded electronics and tie guides handle their own tasks, while Dad explains the current step. Named objects can receive a box when grounding passes the code checks.
3. For a task without a coded guide, the background planner proposes steps while Dad remains the speaker. Code checks the plan before installing it; it cannot replace an active coded guide. This is a model planner plus code checks, not independent model reviewers. See the [planning implementation and evidence](docs/results/planner-live.md).
4. Ask about the past. The time-scope model, enabled with `ROUTER=on`, distinguishes now, recent seconds or minutes, this call, and past calls. Code routes to recent notes, optional TwelveLabs Rewind, or saved-call history. Without the model, explicit time wording still routes memory requests. The current camera is not evidence of the past. See the [memory flow](docs/results/memory-gate.md).
5. Choose Private mode for fully local processing on your own machines, including local speech and vision services. Guest accounts can use this path too, but guest sign-in alone does not enable Private mode. Private mode or `LOCAL_ONLY=1` blocks cloud providers, including Gemini and TwelveLabs. See the [privacy boundaries](docs/privacy.md).

## Measured numbers

These are recorded demo measurements, not guarantees for every device or connection. Sources: [system map measurement notes](docs/results/system-map.md) and the [repo held-out decision results](router/results/scope_heldout_eval.json).

| Measure | Result |
|---|---|
| First voice after you stop speaking | 0.5 to 1.4 s |
| Named-object box | About 2 s |
| Hazard stop line, with Gemini muted | 86 ms |
| Time-scope decision model | 91 percent on an independent 300 question set, reported by the team; 93 of 100 on the repo held-out set |
| Decision latency | About 45 ms |
| List-price cost estimate per 2.5 min call | About $0.05 to $0.07; $0.13 to $0.15 with Recall |

Cost is an estimate, not a measured invoice. The independent-set result is recorded in the map notes; the repo held-out result includes the confusion matrix.

To compare models, [eval/swap/run.py](eval/swap/run.py) re-scores recorded planner and decision outputs and runs the production plan checker. See the [evaluation workflow](docs/results/evals.md). Fixture replay checks the evaluation machinery; it is not evidence of live model quality.

## How to run locally

Needs Python 3.11+ and `uv`. From the repository root:

```sh
make setup                         # Create the virtual environment and install dependencies
make vision VISION_BACKEND=ollama   # Run the vision service in one terminal
make server                        # Run the call server in another terminal
```

Open `http://localhost:8000/agent.html`; open `http://localhost:8000/map.html` for the system map. The Ollama backend needs a configured local model service. `VISION_BACKEND=fake` supplies canned scenes for development, not real camera understanding.

Configure `GEMINI_API_KEY` locally and enable Google consent for Gemini Live. Enable `ROUTER=on` with the router model dependencies installed for model-based time routing. Cloud planning requires Claude configuration and consent; Rewind requires TwelveLabs configuration and opt-in. See [local setup](docs/home-setup.md) and [privacy](docs/privacy.md).

For a local-only call, run `make server LOCAL_ONLY=1` with the local model and speech services available. For a canned offline UI demo, use `make mock` instead of `make server`. `make smoke` exercises the original photo flow with fake vision, not the full Dad call. Phone camera and microphone access require HTTPS; `make phone` prints setup guidance after access credentials are configured.

## Honest limits

- Electronics guidance is USB-only practice. Confirmations such as power disconnected and resistor in series are user reports, not physical certification. Tie completion is also reported by the user.
- Hazard rules recognize specific language. They cannot detect every dangerous situation or certify that a circuit is safe.
- Boxes can be wrong or absent. Stale frames, uncertain grounding and unavailable vision can produce no box.
- The background planner can fail, time out or produce a rejected plan. Its code checker does not prove that every accepted instruction is correct.
- Rewind uploads silent clips to TwelveLabs only when enabled. Clips are deleted at call end unless kept; saved-call recall depends on retained evidence. Missing memory gets an honest unavailable answer.
- Private mode needs working local services and does not provide Gemini Live, cloud planning or TwelveLabs Rewind. The parts shelf is a stored catalog, not a live price or stock check.

## Team

Shivam Bhatt, Reynard Adhitthanajaya, Tasos, Duc Minh Vo.
