import assert from "node:assert/strict";
import test from "node:test";
import { createVoice, isEcho, pcm16ToFloat32, wordCount } from "./voice.js";

function pcm16Base64(samples) {
  const bytes = Buffer.alloc(samples.length * 2);
  for (let i = 0; i < samples.length; i++) bytes.writeInt16LE(samples[i], i * 2);
  return bytes.toString("base64");
}

function fakeRecognition() {
  return {
    continuous: false,
    interimResults: false,
    lang: "",
    starts: 0,
    stops: 0,
    start() {
      this.starts += 1;
    },
    stop() {
      this.stops += 1;
    },
  };
}

function fakeSynth() {
  return {
    cancels: 0,
    spoken: [],
    cancel() {
      this.cancels += 1;
    },
    speak(utterance) {
      this.spoken.push(utterance);
      this.current = utterance;
    },
  };
}

function fakeContext() {
  const ctx = {
    state: "running",
    currentTime: 0,
    destination: {},
    starts: [],
    stops: 0,
    resumes: 0,
    createBuffer(_channels, length, sampleRate) {
      const data = new Float32Array(length);
      return {
        length,
        sampleRate,
        duration: length / sampleRate,
        getChannelData() {
          return data;
        },
      };
    },
    createBufferSource() {
      const src = {
        buffer: null,
        connect() {},
        start(when) {
          ctx.starts.push(when);
        },
        stop() {
          ctx.stops += 1;
          src.stopped = true;
        },
      };
      return src;
    },
    resume() {
      ctx.resumes += 1;
      ctx.state = "running";
      return Promise.resolve();
    },
  };
  return ctx;
}

function harness(extra = {}) {
  const rec = extra.rec || fakeRecognition();
  const synth = extra.synth || fakeSynth();
  const ctx = extra.ctx || fakeContext();
  const events = {
    finals: [],
    interims: [],
    states: [],
    barges: [],
  };
  let clock = extra.t0 ?? 0;
  const voice = createVoice({
    onFinal: (text) => events.finals.push(text),
    onInterim: (text) => events.interims.push(text),
    onState: (state) => events.states.push(state),
    onBargeIn: (id, atMs) => {
      events.barges.push([id, atMs, voice.isSpeaking()]);
    },
    recognitionFactory: () => rec,
    synth,
    audioContextFactory: () => ctx,
    now: () => clock,
    ...extra.options,
  });
  return {
    rec,
    synth,
    ctx,
    events,
    voice,
    setTime(value) {
      clock = value;
    },
  };
}

function result(transcript, isFinal) {
  return {
    results: [{ 0: { transcript }, isFinal }],
  };
}

test("word count, echo, and a known PCM16 buffer", () => {
  assert.equal(wordCount("  one   two  three "), 3);
  assert.equal(wordCount("hello, world!"), 2);
  assert.equal(wordCount(""), 0);
  assert.equal(isEcho("Switch the PSU off.", "switch the psu off and unplug it"), true);
  assert.equal(isEcho("stop that now", "switch the psu off"), false);
  assert.equal(isEcho("", "hello there"), true);

  const encoded = pcm16Base64([0, 16384, -32768]);
  const decoded = pcm16ToFloat32(encoded);
  assert.equal(decoded.length, 3);
  assert.equal(decoded[0], 0);
  assert.equal(decoded[1], 16384 / 32768);
  assert.equal(decoded[2], -1);
});

test("final and interim callbacks", () => {
  const { rec, voice, events } = harness();
  assert.equal(voice.supported.stt, true);
  assert.equal(voice.supported.tts, true);
  voice.startListening();
  rec.onresult(result("place the fan", false));
  rec.onresult(result("place the fan here", true));
  assert.deepEqual(events.interims, ["place the fan"]);
  assert.deepEqual(events.finals, ["place the fan here"]);
});

test("recognition restarts after end while listening", () => {
  const { rec, voice, events } = harness();
  voice.startListening();
  assert.equal(rec.continuous, true);
  assert.equal(rec.interimResults, true);
  assert.equal(rec.lang, "en-US");
  assert.equal(rec.starts, 1);
  assert.deepEqual(events.states, ["listening"]);
  rec.onend();
  assert.equal(rec.starts, 2);
  voice.stopListening();
  assert.equal(rec.stops, 1);
  rec.onend();
  assert.equal(rec.starts, 2);
  assert.deepEqual(events.states, ["listening", "idle"]);
});

test("speak is speaking until the utterance ends", () => {
  const { synth, voice, events } = harness();
  voice.speak("say-1", "Switch the PSU off.");
  assert.equal(voice.isSpeaking(), true);
  assert.deepEqual(events.states, ["speaking"]);
  assert.equal(synth.spoken.length, 1);
  assert.equal(synth.spoken[0].text, "Switch the PSU off.");
  synth.current.onend();
  assert.equal(voice.isSpeaking(), false);
  assert.deepEqual(events.states, ["speaking", "idle"]);
});

test("cancel stops synth and audio", () => {
  const { synth, ctx, voice, events } = harness();
  voice.speak("say-2", "Check the fan header.");
  voice.playPcm("say-2", pcm16Base64(new Array(1600).fill(0)), false);
  const cancels = synth.cancels;
  voice.cancel();
  assert.equal(synth.cancels, cancels + 1);
  assert.equal(ctx.stops, 1);
  assert.equal(voice.isSpeaking(), false);
  assert.equal(events.states.at(-1), "idle");
});

test("barge-in fires once with id and elapsed ms and stops playback", () => {
  const { rec, synth, ctx, voice, events, setTime } = harness({ t0: 1000 });
  voice.startListening();
  voice.speak("utt-9", "Turn the screw clockwise now.");
  setTime(1000);
  voice.playPcm("utt-9", pcm16Base64(new Array(800).fill(0)), false);
  const cancelsAfterPlay = synth.cancels;
  setTime(1250);
  rec.onresult(result("wait", false));
  assert.equal(events.barges.length, 0);
  assert.equal(voice.isSpeaking(), true);
  rec.onresult(result("wait stop that", false));
  assert.deepEqual(events.barges, [["utt-9", 250, false]]);
  assert.equal(synth.cancels, cancelsAfterPlay + 1);
  assert.equal(ctx.stops, 1);
  assert.equal(voice.isSpeaking(), false);
  assert.deepEqual(events.interims, ["wait", "wait stop that"]);
  rec.onresult(result("wait stop that please", true));
  assert.equal(events.barges.length, 1);
  assert.deepEqual(events.finals, ["wait stop that please"]);
  assert.equal(events.states.at(-1), "listening");
});

test("an echo of the spoken line does not barge in", () => {
  const { rec, synth, voice, events } = harness({ t0: 0 });
  voice.speak("utt-3", "Switch the PSU off and unplug it.");
  const cancels = synth.cancels;
  rec.onresult(result("switch the psu off", false));
  rec.onresult(result("Switch the PSU off and unplug it.", true));
  assert.equal(events.barges.length, 0);
  assert.equal(synth.cancels, cancels);
  assert.equal(voice.isSpeaking(), true);
  assert.deepEqual(events.interims, []);
  assert.deepEqual(events.finals, []);
});

test("PCM16 chunks queue back to back", () => {
  const { ctx, voice } = harness();
  const first = new Array(800).fill(0);
  const second = new Array(1600).fill(1000);
  voice.playPcm("aud-1", pcm16Base64(first), false);
  voice.playPcm("aud-1", pcm16Base64(second), true);
  assert.equal(ctx.starts.length, 2);
  assert.equal(ctx.starts[0], 0);
  assert.equal(ctx.starts[1] - ctx.starts[0], first.length / 16000);
  assert.equal(ctx.starts[1], first.length / 16000);
});

test("unlockAudio resumes a suspended context", async () => {
  const ctx = fakeContext();
  ctx.state = "suspended";
  const { voice } = harness({ ctx });
  const ok = await voice.unlockAudio();
  assert.equal(ok, true);
  assert.equal(ctx.resumes, 1);
  assert.equal(ctx.state, "running");
});

test("missing speech APIs report unsupported and do not throw", () => {
  const voice = createVoice({
    recognitionFactory: () => null,
    synth: null,
    onFinal() {},
    onInterim() {},
    onState() {},
    onBargeIn() {},
  });
  assert.deepEqual(voice.supported, { stt: false, tts: false });
  voice.startListening();
  voice.speak("x", "hi");
  voice.cancel();
  assert.equal(voice.isSpeaking(), false);
});
