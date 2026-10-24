// Browser mic, speech-to-text, and talk-back for the call page.
// No recording, no storage, and no logging. Status leaves only through onState.
// Server STT streams 16 kHz PCM16 through onAudioChunk and keeps only the unsent
// tail of the current utterance. Nothing is written to disk or kept after send.
// iOS creates or resumes AudioContext only inside a user gesture: the page calls
// unlockAudio() from the mic button tap.

const PCM_RATE = 16000;
const CHUNK_SAMPLES = PCM_RATE / 5; // 200 ms
const MAX_UTTER_SAMPLES = PCM_RATE * 15;
const VAD_RATIO = 2;
const VAD_UP = 0.2;
const VAD_DOWN = 0.05;
const SPEECH_RMS = 0.02;
const HANG_MS = 400;

export function wordCount(text) {
  return wordsOf(text).length;
}

// True when every heard word already appears in the line being spoken.
// An empty hear is treated as an echo so it cannot trip barge-in.
export function isEcho(heard, speaking) {
  const heardWords = wordsOf(heard);
  if (heardWords.length === 0) return true;
  const spoken = new Set(wordsOf(speaking));
  return heardWords.every((word) => spoken.has(word));
}

// Little-endian PCM16 bytes, base64, to floats in [-1, 1]. A trailing odd byte is dropped.
export function pcm16ToFloat32(base64) {
  const bytes = decodeBase64(base64);
  const n = bytes.length - (bytes.length % 2);
  const view = new DataView(bytes.buffer, bytes.byteOffset, n);
  const out = new Float32Array(n / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = view.getInt16(i * 2, true) / 32768;
  }
  return out;
}

// Box-average when fromRate is an integer multiple of toRate. Trailing samples
// that do not fill a whole output frame are dropped.
export function downsample(float32, fromRate, toRate) {
  const input = asFloat32(float32);
  const from = Number(fromRate);
  const to = Number(toRate);
  if (!input.length || !Number.isFinite(from) || !Number.isFinite(to) || from <= 0 || to <= 0) {
    return new Float32Array(0);
  }
  if (from === to) return new Float32Array(input);
  if (from % to === 0) {
    const step = from / to;
    const outLen = Math.floor(input.length / step);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      let sum = 0;
      const base = i * step;
      for (let j = 0; j < step; j++) sum += input[base + j];
      out[i] = sum / step;
    }
    return out;
  }
  const outLen = Math.floor((input.length * to) / from);
  const out = new Float32Array(outLen);
  const scale = from / to;
  for (let i = 0; i < outLen; i++) {
    const pos = i * scale;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}

// Floats outside [-1, 1] clamp to int16. Scale matches pcm16ToFloat32 (divide by 32768).
export function floatToPcm16(float32) {
  const input = asFloat32(float32);
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    let s = input[i];
    if (!Number.isFinite(s)) s = 0;
    else if (s > 1) s = 1;
    else if (s < -1) s = -1;
    let v = Math.round(s * 32768);
    if (v > 32767) v = 32767;
    else if (v < -32768) v = -32768;
    out[i] = v;
  }
  return out;
}

// The first frame sets the noise floor and does not open speech.
// Later frames start only above max(threshold, floor * 2). Silence for hangMs ends it.
export function createVad(options = {}) {
  const threshold = Number.isFinite(options.threshold) ? options.threshold : SPEECH_RMS;
  const hangMs = Number.isFinite(options.hangMs) ? options.hangMs : HANG_MS;
  let noise = 0;
  let seeded = false;
  let active = false;
  let lastVoice = 0;

  function gate() {
    return Math.max(threshold, noise * VAD_RATIO);
  }

  function adapt(energy) {
    const alpha = energy > noise ? VAD_UP : VAD_DOWN;
    noise = noise * (1 - alpha) + energy * alpha;
  }

  return {
    push(frameEnergy, nowMs) {
      const energy = Number.isFinite(frameEnergy) ? Math.max(0, frameEnergy) : 0;
      const now = Number.isFinite(nowMs) ? nowMs : 0;
      if (!seeded) {
        noise = energy;
        seeded = true;
        return "silence";
      }
      const above = energy > gate();
      if (!active) {
        if (above) {
          active = true;
          lastVoice = now;
          return "start";
        }
        adapt(energy);
        return "silence";
      }
      if (above) {
        lastVoice = now;
        return "speech";
      }
      if (now - lastVoice >= hangMs) {
        active = false;
        adapt(energy);
        return "end";
      }
      return "speech";
    },
  };
}

export function createVoice(options = {}) {
  const onFinal = options.onFinal || noop;
  const onInterim = options.onInterim || noop;
  const onState = options.onState || noop;
  const onBargeIn = options.onBargeIn || noop;
  const onAudioChunk = options.onAudioChunk || noop;
  const serverMode = options.sttMode === "server";
  const lang = options.lang || "en-US";
  const now = options.now || defaultNow;
  const synth = options.synth !== undefined ? options.synth : globalThis.speechSynthesis || null;
  const recognitionFactory = options.recognitionFactory || defaultRecognitionFactory;
  const audioContextFactory = options.audioContextFactory || defaultAudioContextFactory;
  const customAudio = Object.prototype.hasOwnProperty.call(options, "audioContextFactory");

  let rec = null;
  try {
    rec = recognitionFactory();
  } catch {
    rec = null;
  }

  const supported = {
    stt: serverMode ? micAvailable() : Boolean(rec),
    tts: Boolean(synth) || customAudio || hasAudioConstructor(),
  };

  let state = "idle";
  let listening = false;
  let recRunning = false;
  let speaking = false;
  let utteranceId = null;
  let spokenText = "";
  let playbackStartedAt = 0;
  let bargedUtterance = null;
  let synthActive = false;
  let synthGen = 0;
  let audioActive = false;
  let audioLeft = 0;
  let audioGen = 0;
  let pcmFinal = false;
  let nextTime = null;
  let audioCtx = null;
  const sources = [];
  let captureGen = 0;
  let mediaStream = null;
  const captureNodes = [];
  let workletUrl = "";
  let vad = createVad({ threshold: SPEECH_RMS, hangMs: HANG_MS });
  let pieces = [];
  let queued = 0;
  let sentInUtt = 0;
  let utteranceOpen = false;
  let serverHold = false;
  let audioSeq = 0;

  if (rec) {
    rec.onresult = handleResult;
    rec.onerror = handleRecError;
    rec.onend = handleRecEnd;
  }

  function setState(next) {
    if (next === state) return;
    state = next;
    onState(state);
  }

  function isSpeaking() {
    return speaking;
  }

  function maybeIdle() {
    if (synthActive || audioActive) return;
    speaking = false;
    setState(listening ? "listening" : "idle");
  }

  function haltPlayback() {
    audioGen += 1;
    synthGen += 1;
    synthActive = false;
    audioActive = false;
    audioLeft = 0;
    pcmFinal = false;
    nextTime = null;
    speaking = false;
    if (synth && typeof synth.cancel === "function") {
      try {
        synth.cancel();
      } catch {
        // ignore
      }
    }
    const doomed = sources.splice(0, sources.length);
    for (const src of doomed) {
      try {
        src.stop();
      } catch {
        // already stopped
      }
    }
  }

  function startListening() {
    if (serverMode) return startServerListening();
    if (!rec) return;
    listening = true;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang;
    if (!recRunning) {
      try {
        rec.start();
        recRunning = true;
      } catch {
        recRunning = false;
      }
    }
    if (!speaking) setState("listening");
  }

  function stopListening() {
    listening = false;
    if (serverMode) {
      captureGen += 1;
      if (utteranceOpen) drain(true);
      utteranceOpen = false;
      serverHold = false;
      releaseCapture();
      if (!speaking) setState("idle");
      return;
    }
    if (rec) {
      try {
        rec.stop();
      } catch {
        // not started
      }
    }
    if (!speaking) setState("idle");
  }

  function handleRecEnd() {
    recRunning = false;
    if (!listening || !rec) return;
    try {
      rec.start();
      recRunning = true;
    } catch {
      recRunning = false;
    }
  }

  function handleRecError(event) {
    const code = event && event.error;
    if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
      listening = false;
      if (!speaking) setState("idle");
    }
  }

  function handleResult(event) {
    const results = event && event.results;
    if (!results) return;
    const from = Number.isInteger(event.resultIndex) ? event.resultIndex : 0;
    for (let i = from; i < results.length; i++) {
      const row = results[i];
      const text = transcriptOf(row).trim();
      if (!text) continue;
      // While playback is up, a result whose words all sit inside the spoken line
      // is the speaker heard by the mic. Drop it instead of treating it as the user.
      if (speaking && isEcho(text, spokenText)) continue;
      considerBarge(text);
      if (row && row.isFinal) onFinal(text);
      else onInterim(text);
    }
  }

  function considerBarge(text) {
    if (!speaking || utteranceId == null) return;
    if (wordCount(text) < 2) return;
    if (isEcho(text, spokenText)) return;
    if (bargedUtterance === utteranceId) return;
    fireBarge();
  }

  // Server mode has no transcript yet. Speech onset is the barge, once per utterance.
  function considerServerBarge() {
    if (!speaking || utteranceId == null) return;
    if (bargedUtterance === utteranceId) return;
    fireBarge();
  }

  function fireBarge() {
    const id = utteranceId;
    const atMs = Math.max(0, Math.round(now() - playbackStartedAt));
    bargedUtterance = id;
    haltPlayback();
    setState(listening ? "listening" : "idle");
    onBargeIn(id, atMs);
  }

  function speak(id, text) {
    haltPlayback();
    utteranceId = id;
    spokenText = String(text || "");
    bargedUtterance = null;
    playbackStartedAt = now();
    speaking = true;
    setState("speaking");
    if (!synth || typeof synth.speak !== "function") {
      maybeIdle();
      return;
    }
    const utter = makeUtterance(spokenText);
    utter.lang = lang;
    const token = ++synthGen;
    synthActive = true;
    const done = () => {
      if (token !== synthGen) return;
      synthActive = false;
      maybeIdle();
    };
    utter.onend = done;
    utter.onerror = done;
    try {
      synth.speak(utter);
    } catch {
      synthActive = false;
      maybeIdle();
    }
  }

  function playPcm(id, pcm16Base64, finalChunk) {
    const same = speaking && utteranceId === id;
    if (!same) {
      const keepText = utteranceId === id ? spokenText : "";
      haltPlayback();
      utteranceId = id;
      spokenText = keepText;
      bargedUtterance = null;
      playbackStartedAt = now();
      speaking = true;
      setState("speaking");
    }
    // Server audio replaces browser TTS for this utterance. Bump the token
    // before cancel so the utterance's onend does not mark playback finished.
    if (synthActive) {
      synthGen += 1;
      synthActive = false;
      if (synth && typeof synth.cancel === "function") {
        try {
          synth.cancel();
        } catch {
          // ignore
        }
      }
    }
    if (finalChunk) pcmFinal = true;
    let samples;
    try {
      samples = pcm16ToFloat32(pcm16Base64);
    } catch {
      samples = new Float32Array(0);
    }
    if (samples.length === 0) {
      if (pcmFinal && audioLeft === 0) {
        audioActive = false;
        maybeIdle();
      }
      return;
    }
    const ctx = ensureAudio();
    if (!ctx || typeof ctx.createBuffer !== "function" || typeof ctx.createBufferSource !== "function") {
      if (pcmFinal && audioLeft === 0) {
        audioActive = false;
        maybeIdle();
      }
      return;
    }
    if (ctx.state === "suspended" && typeof ctx.resume === "function") {
      try {
        ctx.resume();
      } catch {
        // unlocked later from the mic tap
      }
    }
    let src;
    try {
      const buffer = ctx.createBuffer(1, samples.length, PCM_RATE);
      const channel = buffer.getChannelData(0);
      channel.set(samples);
      src = ctx.createBufferSource();
      src.buffer = buffer;
      if (typeof src.connect === "function") src.connect(ctx.destination);
      const current = typeof ctx.currentTime === "number" ? ctx.currentTime : 0;
      const startAt = nextTime == null || nextTime < current ? current : nextTime;
      nextTime = startAt + samples.length / PCM_RATE;
      const token = audioGen;
      audioLeft += 1;
      audioActive = true;
      sources.push(src);
      src.onended = () => {
        if (token !== audioGen) return;
        audioLeft = Math.max(0, audioLeft - 1);
        if (audioLeft === 0 && pcmFinal) {
          audioActive = false;
          maybeIdle();
        }
      };
      src.start(startAt);
    } catch {
      if (src) {
        const idx = sources.indexOf(src);
        if (idx >= 0) sources.splice(idx, 1);
      }
      if (pcmFinal && audioLeft === 0) {
        audioActive = false;
        maybeIdle();
      }
    }
  }

  function cancel() {
    haltPlayback();
    utteranceId = null;
    spokenText = "";
    setState(listening ? "listening" : "idle");
  }

  function micAvailable() {
    if (typeof options.getUserMedia === "function") return true;
    const md = globalThis.navigator && globalThis.navigator.mediaDevices;
    return Boolean(md && typeof md.getUserMedia === "function");
  }

  function requestMic() {
    const constraints = { audio: { echoCancellation: true, noiseSuppression: true } };
    if (typeof options.getUserMedia === "function") return Promise.resolve(options.getUserMedia(constraints));
    const md = globalThis.navigator && globalThis.navigator.mediaDevices;
    if (!md || typeof md.getUserMedia !== "function") return Promise.reject(new Error("no mic"));
    return md.getUserMedia(constraints);
  }

  async function startServerListening() {
    const token = ++captureGen;
    listening = true;
    utteranceOpen = false;
    serverHold = false;
    dropQueue();
    releaseCapture();
    vad = createVad({ threshold: SPEECH_RMS, hangMs: HANG_MS });
    try {
      const stream = await requestMic();
      if (token !== captureGen || !listening) {
        stopTracks(stream);
        return;
      }
      mediaStream = stream;
      const ctx = ensureAudio();
      if (!ctx) throw new Error("no audio");
      await attachCapture(ctx, stream, token);
      if (token !== captureGen || !listening) {
        releaseCapture();
        return;
      }
      if (!speaking) setState("listening");
    } catch {
      if (token !== captureGen) return;
      listening = false;
      releaseCapture();
      if (!speaking) setState("idle");
    }
  }

  async function attachCapture(ctx, stream, token) {
    if (typeof ctx.createMediaStreamSource !== "function") throw new Error("no source");
    const source = ctx.createMediaStreamSource(stream);
    captureNodes.push(source);
    const worked = await attachWorklet(ctx, source, token);
    if (worked) return;
    if (typeof ctx.createScriptProcessor !== "function") throw new Error("no capture node");
    const proc = ctx.createScriptProcessor(2048, 1, 1);
    proc.onaudioprocess = (event) => {
      const buffer = event && event.inputBuffer;
      const rate = buffer && buffer.sampleRate ? buffer.sampleRate : ctx.sampleRate || 48000;
      onCapture(monoBuffer(buffer), rate, token);
    };
    if (typeof source.connect === "function") source.connect(proc);
    connectSilent(ctx, proc);
    captureNodes.push(proc);
  }

  async function attachWorklet(ctx, source, token) {
    const worklet = ctx.audioWorklet;
    if (!worklet || typeof worklet.addModule !== "function") return false;
    if (typeof globalThis.AudioWorkletNode !== "function") return false;
    try {
      const url = createWorkletUrl();
      workletUrl = url;
      await worklet.addModule(url);
      if (token !== captureGen || !listening) return false;
      const node = new globalThis.AudioWorkletNode(ctx, "pcm-capture");
      node.port.onmessage = (event) => {
        const samples = event && event.data;
        if (!samples || typeof samples.length !== "number") return;
        onCapture(samples, ctx.sampleRate || 48000, token);
      };
      if (typeof source.connect === "function") source.connect(node);
      connectSilent(ctx, node);
      captureNodes.push(node);
      return true;
    } catch {
      return false;
    }
  }

  function onCapture(samples, sampleRate, token) {
    if (token !== captureGen || !listening) return;
    const down = downsample(samples, sampleRate, PCM_RATE);
    if (down.length === 0) return;
    const verdict = vad.push(rms(down), now());
    if (serverHold) {
      if (verdict === "end" || verdict === "silence") serverHold = false;
      return;
    }
    if (verdict === "silence") return;
    if (verdict === "start") {
      dropQueue();
      sentInUtt = 0;
      utteranceOpen = true;
      considerServerBarge();
    } else if (verdict === "end") {
      if (utteranceOpen) drain(true);
      utteranceOpen = false;
      return;
    } else if (!utteranceOpen) {
      return;
    }
    appendSamples(down);
    drain(false);
  }

  function appendSamples(samples) {
    const pcm = floatToPcm16(samples);
    if (pcm.length === 0) return;
    pieces.push(pcm);
    queued += pcm.length;
  }

  function takeSamples(n) {
    const out = new Int16Array(n);
    let filled = 0;
    while (filled < n && pieces.length) {
      const head = pieces[0];
      const need = n - filled;
      if (head.length <= need) {
        out.set(head, filled);
        filled += head.length;
        pieces.shift();
      } else {
        out.set(head.subarray(0, need), filled);
        pieces[0] = head.subarray(need);
        filled += need;
      }
    }
    queued -= filled;
    return filled === n ? out : out.subarray(0, filled);
  }

  function dropQueue() {
    pieces = [];
    queued = 0;
  }

  function drain(finalChunk) {
    while (queued >= CHUNK_SAMPLES && sentInUtt + CHUNK_SAMPLES < MAX_UTTER_SAMPLES) {
      const took = takeSamples(CHUNK_SAMPLES);
      sentInUtt += took.length;
      emitChunk(took, false);
    }
    const hitCap = utteranceOpen && sentInUtt + queued >= MAX_UTTER_SAMPLES;
    if (hitCap) {
      const room = MAX_UTTER_SAMPLES - sentInUtt;
      const n = Math.min(queued, room > 0 ? room : 0);
      const tail = n > 0 ? takeSamples(n) : new Int16Array(0);
      dropQueue();
      sentInUtt += tail.length;
      emitChunk(tail, true);
      utteranceOpen = false;
      serverHold = true;
      return;
    }
    if (!finalChunk) return;
    const tail = queued > 0 ? takeSamples(queued) : new Int16Array(0);
    if (tail.length > 0 || sentInUtt > 0) emitChunk(tail, true);
    dropQueue();
    sentInUtt = 0;
    utteranceOpen = false;
  }

  function emitChunk(samples, finalChunk) {
    const seq = audioSeq;
    audioSeq += 1;
    onAudioChunk(encodePcm16(samples), seq, Boolean(finalChunk));
  }

  function releaseCapture() {
    const stream = mediaStream;
    mediaStream = null;
    stopTracks(stream);
    const nodes = captureNodes.splice(0, captureNodes.length);
    for (const node of nodes) {
      try {
        if (node && typeof node.disconnect === "function") node.disconnect();
      } catch {
        // already disconnected
      }
    }
    if (workletUrl) {
      try {
        URL.revokeObjectURL(workletUrl);
      } catch {
        // ignore
      }
      workletUrl = "";
    }
  }

  function connectSilent(ctx, node) {
    if (!node || typeof node.connect !== "function") return;
    if (typeof ctx.createGain === "function") {
      const gain = ctx.createGain();
      if (gain.gain) gain.gain.value = 0;
      node.connect(gain);
      if (ctx.destination && typeof gain.connect === "function") gain.connect(ctx.destination);
      captureNodes.push(gain);
      return;
    }
    if (ctx.destination) node.connect(ctx.destination);
  }

  function ensureAudio() {
    if (audioCtx) return audioCtx;
    try {
      audioCtx = audioContextFactory() || null;
    } catch {
      audioCtx = null;
    }
    return audioCtx;
  }

  function unlockAudio() {
    const ctx = ensureAudio();
    if (!ctx) return Promise.resolve(false);
    if (typeof ctx.resume === "function" && ctx.state !== "running") {
      try {
        return Promise.resolve(ctx.resume()).then(
          () => true,
          () => false,
        );
      } catch {
        return Promise.resolve(false);
      }
    }
    return Promise.resolve(true);
  }

  return {
    supported,
    startListening,
    stopListening,
    speak,
    playPcm,
    cancel,
    isSpeaking,
    unlockAudio,
  };
}

function wordsOf(text) {
  const found = String(text || "").toLowerCase().match(/[a-z0-9']+/g);
  return found || [];
}

function transcriptOf(row) {
  if (!row) return "";
  if (row[0] && typeof row[0].transcript === "string") return row[0].transcript;
  if (typeof row.transcript === "string") return row.transcript;
  return "";
}

function makeUtterance(text) {
  const Ctor = globalThis.SpeechSynthesisUtterance;
  if (typeof Ctor === "function") return new Ctor(text);
  return { text };
}

function decodeBase64(base64) {
  const clean = String(base64 || "").replace(/\s+/g, "");
  if (!clean) return new Uint8Array(0);
  const bin = atob(clean);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i) & 0xff;
  return out;
}

function defaultRecognitionFactory() {
  const Ctor = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
  if (typeof Ctor !== "function") return null;
  return new Ctor();
}

function defaultAudioContextFactory() {
  const Ctor = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (typeof Ctor !== "function") return null;
  return new Ctor();
}

function hasAudioConstructor() {
  return typeof (globalThis.AudioContext || globalThis.webkitAudioContext) === "function";
}

function defaultNow() {
  if (globalThis.performance && typeof performance.now === "function") return performance.now();
  return Date.now();
}

function asFloat32(value) {
  if (value instanceof Float32Array) return value;
  if (!value || typeof value.length !== "number") return new Float32Array(0);
  return Float32Array.from(value);
}

function rms(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    sum += s * s;
  }
  return Math.sqrt(sum / samples.length);
}

function monoBuffer(buffer) {
  if (!buffer || typeof buffer.getChannelData !== "function") return new Float32Array(0);
  const channels = buffer.numberOfChannels || 1;
  const first = buffer.getChannelData(0);
  if (!first || !first.length) return new Float32Array(0);
  if (channels < 2) return first;
  const out = new Float32Array(first.length);
  for (let c = 0; c < channels; c++) {
    const ch = buffer.getChannelData(c);
    if (!ch) continue;
    for (let i = 0; i < out.length; i++) out[i] += ch[i] || 0;
  }
  const inv = 1 / channels;
  for (let i = 0; i < out.length; i++) out[i] *= inv;
  return out;
}

function encodePcm16(samples) {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i], true);
  let bin = "";
  const step = 8192;
  for (let i = 0; i < bytes.length; i += step) {
    const end = Math.min(bytes.length, i + step);
    let part = "";
    for (let j = i; j < end; j++) part += String.fromCharCode(bytes[j]);
    bin += part;
  }
  return btoa(bin);
}

function createWorkletUrl() {
  const source = `
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;
    const ch0 = input[0];
    const channels = input.length;
    if (channels === 1) {
      this.port.postMessage(ch0);
      return true;
    }
    const mixed = new Float32Array(ch0.length);
    for (let c = 0; c < channels; c++) {
      const ch = input[c];
      if (!ch) continue;
      for (let i = 0; i < mixed.length; i++) mixed[i] += ch[i] || 0;
    }
    const inv = 1 / channels;
    for (let i = 0; i < mixed.length; i++) mixed[i] *= inv;
    this.port.postMessage(mixed);
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
`;
  const blob = new Blob([source], { type: "application/javascript" });
  return URL.createObjectURL(blob);
}

function stopTracks(stream) {
  if (!stream || typeof stream.getTracks !== "function") return;
  for (const track of stream.getTracks()) {
    try {
      track.stop();
    } catch {
      // already stopped
    }
  }
}

function noop() {}
