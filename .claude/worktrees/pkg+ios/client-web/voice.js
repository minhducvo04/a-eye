// Browser mic, speech-to-text, and talk-back for the call page.
// No recording, no storage, and no logging. Status leaves only through onState.
// iOS creates or resumes AudioContext only inside a user gesture: the page calls
// unlockAudio() from the mic button tap.

const PCM_RATE = 16000;

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

export function createVoice(options = {}) {
  const onFinal = options.onFinal || noop;
  const onInterim = options.onInterim || noop;
  const onState = options.onState || noop;
  const onBargeIn = options.onBargeIn || noop;
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
    stt: Boolean(rec),
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

function noop() {}
