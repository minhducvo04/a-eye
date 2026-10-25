## Inspiration

A breadboard project asks you to keep track of parts, tools, instructions and what you just changed. The team wanted a live guide that could see the work, point to the relevant part and remember earlier context. The aim is practice that gradually needs less help.

## What it does

A-eye is a live guide for building electronics projects. Gemini Live supplies the voice and eyes, receiving microphone audio and camera frames with consent. Boxes and arrows point at parts when grounding checks pass. Uncertain or stale targets produce no pointer. Safety stops live in code and check transcripts and tool arguments. <!-- Sources: docs/results/gemini-live.md; docs/results/pointer.md -->

Memory has different time scopes. The classic call path recalls the last 2 minutes from local, temporary text notes without another model request. Earlier moments in the call can use TwelveLabs Rewind when enabled. Across days, consented local memory retains context, with encrypted storage configured. Missing evidence produces an uncertain answer rather than an invented action. <!-- Sources: docs/results/recent-memory.md, Behavior (120 seconds); docs/results/grow.md, encrypted persistence and key requirements -->

Growth means hints fade, with full steps available again on request. Safety checks remain active. This behavior is currently implemented for guided home tasks; extending it to electronics is still work ahead. <!-- Source: docs/results/grow.md -->

Accounts offer Guest and Google sign-in. “My data” lets people view, export or delete their data for free, even after usage or cloud budgets run out. Guest and data controls passed a local browser run; live Google sign-in still needs verification. Failed cloud deletion stays pending rather than being reported as complete. <!-- Source: docs/results/accounts.md -->

## How we built it

The team worked with AI agents: Codex builds, Grok reviews and Claude plans. Packages had separate owners, branches and worktrees, with written tests and limits. The team made product decisions and approved privacy-sensitive merges. <!-- Source: docs/journey.md -->

Independent security reviews caught real holes: unauthenticated local-network access, pairing codes without a guess limit, and tunnel traffic being mistaken for local traffic. Review findings sent work back for fixes. <!-- Source: docs/journey.md -->

## Architecture

```text
Camera + microphone → server safety checks ↔ Gemini Live
                              ↓
                  checked speech + grounded boxes/arrows
                              ↕
             recent local notes | optional TwelveLabs Rewind
                              | encrypted cross-day memory
                              ↕
                       accounts + My data
```

Recent-note routing currently belongs to the classic call path. It has not been wired into Gemini Live's separate dialogue path. <!-- Sources: docs/results/recent-memory.md; docs/results/gemini-live.md -->

## Challenges

Venue Wi-Fi made the home GPU pointing path unreliable. The recorded benchmark missed most targets before the freshness deadline. An Ethernet rerun improved the observed result, but its raw output was not saved. <!-- Sources: docs/results/pointer.md; docs/results/system-bench.md, Lead addendum -->

Live camera delivery also failed: the probe reported that it could not see the image. Sending the frame before the question and changing the realtime message path passed the subsequent synthetic-image checks. <!-- Source: docs/results/gemini-live.md, Current verification -->

## Accomplishments

Gemini Live's median first received audio was 0.63 seconds for small talk and 1.13 seconds for a synthetic part image, across 10 trials each. These measure provider arrival, not audible playback after safety buffering. <!-- Source: docs/results/system-bench.md, Gemini Live audio -->

The local mock load test held 1,000 WebSockets for 30 seconds. It did not run active video calls or model inference. <!-- Source: docs/results/system-bench.md, Local HTTP and WebSocket load -->

Recent memory passed 20/20 source-selection and 20/20 answer-content checks on synthetic questions with Rewind stubbed. <!-- Source: docs/results/recent-memory.md, Measurement -->

Cached-caption pointing hit 3/10 synthetic targets on venue Wi-Fi, with no wrong pointers. The Ethernet addendum reports an observed 10/10, without saved raw results. Both used a scripted talker. <!-- Sources: docs/results/pointer.md, Measurement; docs/results/system-bench.md, Lead addendum -->

## Honest limits

There has been no user study. Scripted hint reduction does not prove learning, and a scene description does not prove successful assembly. Small parts, motion and physical-device pointing remain unverified. Live audio waits for transcript safety checks, so provider latency understates playback delay. <!-- Sources: docs/results/grow.md; docs/results/recent-memory.md; docs/results/pointer.md; docs/results/gemini-live.md -->

SpacetimeDB integration is pending. The 1M-user figure is an estimate, not demonstrated capacity. <!-- Source for capacity: docs/results/system-bench.md, Capacity model; integration status supplied in the requested story -->

## What's next

Connect recent recall to Live dialogue, extend fading hints to electronics tasks, and test real breadboard guidance with consenting users. Verify Google sign-in and physical-device playback, finish SpacetimeDB integration, and repeat pointing and active-call load tests with saved results.
