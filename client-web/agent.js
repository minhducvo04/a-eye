// Agent call page. Speaks the v2 WebSocket contract on /ws2.
// Frames exist only as the JPEG about to be sent. Nothing is written to storage.

import { paintDraw, applyDraw, pruneDraw, viewTransform, visibleOps } from "./draw.js";
import { writeFrame } from "./live.js";
import { sharpCanvasSize } from "./overlay.js";
import { AGENTS, layoutOrbs, nextPresence, paintPresence } from "./presence.js";
import {
  bargeSpeech,
  devHudPosition,
  emptySpeech,
  formatHud,
  initialHud,
  initialTrackerBook,
  nextTrackerPlan,
  noteFinalWords,
  noteFirstSound,
  noteFrameReply,
  noteFrameSent,
  noteMetrics,
  notePaint,
  noteTrackerMs,
  pushSay,
  shouldTrack,
} from "./realtime.js";
import { applyAnchors, createTracker, toGray } from "./track.js";

const PACK_LABEL = {
  general: "General",
  pc_build: "PC build",
  cooking: "Cooking",
  assemble: "Assemble",
};

const FRAME_MS = 1000;
const BOARD_ID = "demo-b650";
const TRACK_W = 320;

function boot() {
  const picker = document.getElementById("picker");
  const stage = document.getElementById("stage");
  const video = document.getElementById("camera");
  const still = document.getElementById("still");
  const drawCanvas = document.getElementById("draw");
  const presenceCanvas = document.getElementById("presence");
  const packLabel = document.getElementById("pack-label");
  const statusDot = document.getElementById("status");
  const errorEl = document.getElementById("error");
  const marketEl = document.getElementById("market");
  const marketBody = document.getElementById("market-body");
  const captionEl = document.getElementById("caption");
  const interimEl = document.getElementById("interim");
  const typedEl = document.getElementById("typed");
  const micBtn = document.getElementById("mic");
  const startBtn = document.getElementById("start-camera");
  const powerBtn = document.getElementById("power-off");
  const grab = document.createElement("canvas");
  const grayCanvas = document.createElement("canvas");
  const devOn = new URLSearchParams(location.search).get("dev") === "1";
  const devEl = devOn ? document.createElement("p") : null;
  if (devEl) {
    devEl.className = "dev-hud";
    devEl.setAttribute("aria-hidden", "true");
    const hudRoot = stage.querySelector(".hud");
    if (hudRoot) hudRoot.append(devEl);
  }

  const sessionId = randomId();
  const params = new URLSearchParams(location.search);
  const tts = params.get("tts") === "server" ? "server" : "browser";
  const stt = params.get("stt") === "server" ? "server" : "browser";
  const sttLabel = document.createElement("span");
  sttLabel.className = "stt-mode";
  sttLabel.textContent = stt === "server" ? "Whisper" : "Browser";
  micBtn.insertAdjacentElement("afterend", sttLabel);
  const reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

  let pack = "";
  let socket = null;
  let retryTimer = 0;
  let seq = 0;
  let cameraOn = false;
  let starting = false;
  let frameTimer = 0;
  let photoUrl = "";
  let drawState = applyDraw(null, null, 0);
  let presence = nextPresence(null, null, 0);
  let motion = { helper: null, shopper: null };
  let voice = null;
  let listening = false;
  let raf = 0;
  let speech = emptySpeech();
  let speakQueue = [];
  let voicedTurn = null;
  const tracker = createTracker();
  let tracks = new Map();
  let book = initialTrackerBook();
  let pendingPlan = null;
  let trackBusy = false;
  let lastTrackAt = null;
  let hud = initialHud();

  const voiceReady = loadVoice({
    onFinal: (text) => {
      const clean = String(text || "").trim();
      if (!clean) return;
      setInterim(clean);
      sendUser(clean, "browser_stt");
    },
    onInterim: (text) => {
      setInterim(String(text || "").trim());
    },
    onState: (state) => {
      if (state === "listening") listening = true;
      if (state === "idle" || state === "stopped") listening = false;
      renderMic();
    },
    onBargeIn: (id, ms) => {
      speech = bargeSpeech(speech);
      speakQueue = [];
      voicedTurn = null;
      send({
        v: 2,
        type: "barge_in",
        session_id: sessionId,
        utterance_id: id,
        at_ms: Math.max(0, Math.round(Number(ms) || 0)),
      });
    },
    sttMode: stt,
    onAudioChunk: (pcm16Base64, seq, final) => {
      send({
        v: 2,
        type: "audio_in",
        session_id: sessionId,
        seq,
        sample_rate: 16000,
        pcm16_b64: pcm16Base64,
        final: Boolean(final),
      });
    },
  });

  function randomId() {
    if (globalThis.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
    return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function wsUrl() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${location.host}/ws2`;
  }

  function reducedMotion() {
    return Boolean(reducedQuery && reducedQuery.matches);
  }

  function send(message) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(message));
    return true;
  }

  function nextSeq() {
    seq += 1;
    return seq;
  }

  function setStatus(on) {
    statusDot.classList.toggle("on", on);
    statusDot.classList.toggle("off", !on);
    statusDot.setAttribute("aria-label", on ? "socket connected" : "socket disconnected");
  }

  function setInterim(text) {
    interimEl.textContent = text || "";
  }

  function setSpeaker(agent, text) {
    const spec = AGENTS[agent] || AGENTS.helper;
    captionEl.replaceChildren();
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = spec.name;
    who.style.color = spec.caption;
    captionEl.append(who, document.createTextNode(text || ""));
  }

  function sendUser(text, source) {
    const clean = String(text || "").trim();
    if (!clean) return false;
    const ok = send({
      v: 2,
      type: "user_text",
      session_id: sessionId,
      text: clean,
      final: true,
      source,
    });
    if (ok) hud = noteFinalWords(hud, Date.now());
    if (!ok) setSpeaker("helper", "Not connected.");
    return ok;
  }

  function connect() {
    if (!pack) return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    socket = new WebSocket(wsUrl());
    socket.addEventListener("open", () => {
      setStatus(true);
      const hello = {
        v: 2,
        type: "hello",
        session_id: sessionId,
        pack,
        client: "web",
        tts,
        stt,
      };
      if (pack === "pc_build") hello.board_id = BOARD_ID;
      send(hello);
    });
    socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") return;
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      onServer(message);
    });
    socket.addEventListener("close", () => {
      setStatus(false);
      socket = null;
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(connect, 2000);
    });
    socket.addEventListener("error", () => {
      setStatus(false);
    });
  }

  function onServer(message) {
    if (!message || typeof message !== "object") return;
    const now = Date.now();
    if (message.type === "draw") {
      hud = noteFrameReply(hud, message, now);
      const before = drawState;
      drawState = applyDraw(drawState, message, now);
      if (drawState !== before) {
        const changed = Array.isArray(message.ops) ? message.ops : [];
        commitTracker("draw", message.seq, null, changed);
      }
      return;
    }
    if (message.type === "track") {
      hud = noteFrameReply(hud, message, now);
      commitTracker("track", message.seq, message.objects);
      return;
    }
    if (message.type === "metrics") {
      hud = noteMetrics(hud, message);
      return;
    }
    if (message.type === "agent_state") {
      presence = nextPresence(presence, message, now);
      return;
    }
    if (message.type === "say") {
      errorEl.classList.add("hidden");
      const result = pushSay(speech, message);
      speech = result.state;
      if (!result.ignored) setSpeaker(result.agent, result.caption);
      if (result.reset) {
        speakQueue = [];
        voicedTurn = null;
        if (voice) voice.cancel();
      }
      if (tts === "browser" && result.speak.length) {
        speakQueue.push(...result.speak);
        flushSpeech();
      }
      return;
    }
    if (message.type === "audio" && voice) {
      markSound();
      Promise.resolve()
        .then(() => voice.playPcm(message.utterance_id, message.pcm16_b64, Boolean(message.final)))
        .catch(() => {});
      return;
    }
    if (message.type === "market_results") {
      showMarket(message.result);
      return;
    }
    if (message.type === "error") {
      errorEl.textContent = message.message || "Something went wrong.";
      errorEl.classList.remove("hidden");
    }
  }

  function fitsLine(item) {
    const compat = item && item.compat;
    const status = compat && compat.status;
    if (status === "unverified") {
      const unknown = compat.unknown && compat.unknown.length ? `: ${compat.unknown.join(", ")}` : "";
      return { text: `Unverified${unknown}`, kind: "unverified" };
    }
    if (status === "no") {
      const why = compat.reasons && compat.reasons.length ? compat.reasons.join("; ") : "";
      return { text: why ? `Does not fit: ${why}` : "Does not fit", kind: "no" };
    }
    if (item && item.explain) return { text: item.explain, kind: status || "" };
    if (status === "fits") {
      const why = compat.reasons && compat.reasons.length ? compat.reasons.join("; ") : "";
      return { text: why ? `Fits because: ${why}` : "Fits", kind: "fits" };
    }
    return { text: "Unverified", kind: "unverified" };
  }

  function money(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "";
    return `$${n.toFixed(2)}`;
  }

  function showMarket(result) {
    marketBody.replaceChildren();
    const items = result && Array.isArray(result.items) ? result.items.slice(0, 3) : [];
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "why";
      empty.textContent = "No offers.";
      marketBody.append(empty);
    } else {
      for (const item of items) {
        const card = document.createElement("article");
        card.className = "offer";
        const title = document.createElement("h2");
        title.textContent = item.title || "Offer";
        const meta = document.createElement("p");
        meta.className = "meta";
        const price = money(item.price_usd);
        const retailer = item.retailer || "";
        meta.textContent = [price, retailer].filter(Boolean).join(" · ");
        const why = document.createElement("p");
        const line = fitsLine(item);
        why.className = line.kind ? `why ${line.kind}` : "why";
        why.textContent = line.text;
        card.append(title, meta, why);
        marketBody.append(card);
      }
    }
    marketEl.classList.remove("hidden");
  }

  function currentOps() {
    const ops = [];
    for (const agent of ["helper", "shopper"]) {
      for (const item of drawState.ops[agent] || []) ops.push(item.op);
    }
    return ops;
  }

  function commitTracker(kind, seq, objects, changedOps) {
    const plan = nextTrackerPlan(book, {
      camera: kind === "stop" ? false : cameraOn,
      kind,
      seq,
      ops: currentOps(),
      changed: changedOps || (kind === "draw" ? currentOps() : null),
      objects,
    });
    book = plan.state;
    if (!cameraOn || kind === "stop") {
      for (const id of plan.drop) tracker.drop(id);
      tracks = new Map();
      pendingPlan = null;
      return;
    }
    const shot = captureGray();
    if (!shot) {
      pendingPlan = plan;
      return;
    }
    applyPlan(plan, shot.gray);
  }

  function applyPlan(plan, gray) {
    for (const id of plan.drop) {
      tracker.drop(id);
      tracks.delete(id);
    }
    for (const item of plan.reseed) {
      try {
        tracker.reseed(item.id, item.bbox, gray);
        tracks.set(item.id, { bbox: item.bbox.slice(), score: 1, lost: false });
      } catch {
        tracker.drop(item.id);
        tracks.delete(item.id);
      }
    }
    pendingPlan = null;
  }

  function reseedKnown(gray) {
    for (const id of book.ids) {
      const bbox = book.boxes[id];
      if (!bbox) continue;
      try {
        tracker.reseed(id, bbox, gray);
        tracks.set(id, { bbox: bbox.slice(), score: 1, lost: false });
      } catch {
        tracker.drop(id);
        tracks.delete(id);
      }
    }
  }

  function captureGray() {
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!(vw > 0) || !(vh > 0)) return null;
    const w = TRACK_W;
    const h = Math.max(1, Math.round((vh / vw) * w));
    const resized = grayCanvas.width !== w || grayCanvas.height !== h;
    if (resized) {
      grayCanvas.width = w;
      grayCanvas.height = h;
    }
    const ctx = grayCanvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    try {
      ctx.drawImage(video, 0, 0, w, h);
      const image = ctx.getImageData(0, 0, w, h);
      return { gray: toGray(image.data, image.width, image.height, 1), resized };
    } catch {
      return null;
    }
  }

  function stepTracker(now) {
    if (!cameraOn || !shouldTrack(lastTrackAt, now, trackBusy)) return;
    if (!video.videoWidth || !video.videoHeight) return;
    trackBusy = true;
    try {
      const shot = captureGray();
      if (!shot) return;
      if (pendingPlan) applyPlan(pendingPlan, shot.gray);
      else if (shot.resized) reseedKnown(shot.gray);
      const started = Date.now();
      tracks = tracker.update(shot.gray) || new Map();
      hud = noteTrackerMs(hud, Date.now() - started);
    } catch {
      /* keep the last good tracks */
    } finally {
      lastTrackAt = now;
      trackBusy = false;
    }
  }

  function dropUnanchored() {
    if (!cameraOn || !book.ids.length) return;
    const live = new Set();
    for (const op of currentOps()) {
      const id = op && op.anchor && op.anchor.object_id;
      if (typeof id === "string" && id) live.add(id);
    }
    if (book.ids.every((id) => live.has(id))) return;
    const plan = nextTrackerPlan(book, {
      camera: true,
      kind: "draw",
      seq: 0,
      ops: currentOps(),
      changed: [],
    });
    book = plan.state;
    for (const id of plan.drop) {
      tracker.drop(id);
      tracks.delete(id);
    }
  }

  function anchoredState(state, live, now) {
    if (!live || live.size === 0) return state;
    const vis = visibleOps(state, now);
    if (!vis.length) return state;
    const moved = applyAnchors(vis.map((item) => item.op), live);
    const ops = { helper: [], shopper: [] };
    for (let i = 0; i < vis.length; i += 1) {
      const agent = vis[i].agent === "shopper" ? "shopper" : "helper";
      ops[agent].push({ op: moved[i], bornMs: vis[i].bornMs, agent });
    }
    return { seq: state.seq, ops };
  }

  function markSound() {
    hud = noteFirstSound(hud, Date.now());
  }

  function flushSpeech() {
    if (!voice || tts !== "browser" || !speakQueue.length) return;
    const lines = speakQueue.splice(0, speakQueue.length);
    for (const line of lines) {
      if (voicedTurn !== speech.turnId) {
        voice.speak(line.utteranceId, line.text);
        voicedTurn = speech.turnId;
        markSound();
      } else {
        queueUtterance(line.text);
      }
    }
  }

  function queueUtterance(text) {
    const synth = globalThis.speechSynthesis;
    if (!synth || typeof synth.speak !== "function") return;
    const Ctor = globalThis.SpeechSynthesisUtterance;
    const utter = typeof Ctor === "function" ? new Ctor(text) : { text };
    utter.lang = "en-US";
    try {
      synth.speak(utter);
    } catch {
      /* caption still shows the sentence */
    }
  }

  function placeDevHud(view, poses) {
    if (!devEl) return;
    const box = devHudPosition(view, poses);
    devEl.style.left = `${box.x}px`;
    devEl.style.top = `${box.y}px`;
    devEl.style.width = `${box.w}px`;
    const text = formatHud(hud);
    if (devEl.textContent !== text) devEl.textContent = text;
  }

  function sourceSize() {
    if (cameraOn && video.videoWidth && video.videoHeight) {
      return { w: video.videoWidth, h: video.videoHeight };
    }
    if (!still.classList.contains("hidden") && still.naturalWidth && still.naturalHeight) {
      return { w: still.naturalWidth, h: still.naturalHeight };
    }
    return { w: 0, h: 0 };
  }

  function currentView() {
    const cssW = stage.clientWidth || window.innerWidth;
    const cssH = stage.clientHeight || window.innerHeight;
    const source = sourceSize();
    const srcW = source.w > 0 ? source.w : cssW;
    const srcH = source.h > 0 ? source.h : cssH;
    const transform = viewTransform(srcW, srcH, cssW, cssH);
    return { ...transform, w: cssW, h: cssH };
  }

  function fitCanvas(canvas, cssW, cssH) {
    const bitmap = sharpCanvasSize(cssW, cssH, window.devicePixelRatio || 1);
    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(bitmap.ratio, 0, 0, bitmap.ratio, 0, 0);
    return ctx;
  }

  function paint(now) {
    const view = currentView();
    if (!(view.w > 0) || !(view.h > 0)) return;
    const reduced = reducedMotion();
    drawState = pruneDraw(drawState, now);
    dropUnanchored();
    const laid = layoutOrbs(presence, motion, view, now, reduced);
    motion = laid.motion;
    hud = notePaint(hud, now);
    const drawCtx = fitCanvas(drawCanvas, view.w, view.h);
    const presenceCtx = fitCanvas(presenceCanvas, view.w, view.h);
    const frameState = cameraOn ? anchoredState(drawState, tracks, now) : drawState;
    paintDraw(drawCtx, frameState, view, now, reduced);
    paintPresence(presenceCtx, presence, laid.poses, view, now, reduced);
    placeDevHud(view, laid.poses);
  }

  function loop() {
    const now = Date.now();
    stepTracker(now);
    paint(now);
    raf = window.requestAnimationFrame(loop);
  }

  function sendLiveFrame() {
    if (!cameraOn || document.hidden) return;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    if (socket.bufferedAmount > 0) return;
    if (!video.videoWidth || !video.videoHeight) return;
    const shot = writeFrame(grab, video, video.videoWidth, video.videoHeight);
    if (!shot || !shot.jpeg_b64) return;
    const sentAt = Date.now();
    const frameSeq = nextSeq();
    const ok = send({
      v: 2,
      type: "frame",
      session_id: sessionId,
      seq: frameSeq,
      ts_ms: sentAt,
      w: shot.w,
      h: shot.h,
      jpeg_b64: shot.jpeg_b64,
    });
    if (ok) hud = noteFrameSent(hud, frameSeq, sentAt);
  }

  function startFrames() {
    if (frameTimer) return;
    frameTimer = window.setInterval(sendLiveFrame, FRAME_MS);
  }

  function stopCamera() {
    const stream = video.srcObject;
    if (stream && typeof stream.getTracks === "function") {
      for (const track of stream.getTracks()) track.stop();
    }
    video.srcObject = null;
    cameraOn = false;
    commitTracker("stop");
  }

  function hideStill() {
    still.classList.add("hidden");
    still.removeAttribute("src");
    if (photoUrl) {
      URL.revokeObjectURL(photoUrl);
      photoUrl = "";
    }
  }

  async function startCamera() {
    if (starting || cameraOn) return;
    if (!window.isSecureContext) {
      setSpeaker("helper", "Camera needs HTTPS or localhost. Use Upload photo.");
      return;
    }
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      setSpeaker("helper", "No camera in this browser. Use Upload photo.");
      return;
    }
    starting = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      hideStill();
      video.srcObject = stream;
      video.playsInline = true;
      video.muted = true;
      await video.play();
      cameraOn = true;
      startBtn.disabled = true;
      commitTracker("draw");
      sendLiveFrame();
      startFrames();
    } catch (err) {
      stopCamera();
      const name = err && err.name;
      if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
        setSpeaker("helper", "Camera blocked. Allow camera access, or use Upload photo.");
      } else {
        setSpeaker("helper", "Camera unavailable. Use Upload photo.");
      }
    } finally {
      starting = false;
    }
  }

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("image"));
      image.src = url;
    });
  }

  async function onUpload(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    const url = URL.createObjectURL(file);
    try {
      const image = await loadImage(url);
      const shot = writeFrame(grab, image, image.naturalWidth, image.naturalHeight);
      if (!shot || !shot.jpeg_b64) {
        URL.revokeObjectURL(url);
        setSpeaker("helper", "Could not read that photo.");
        return;
      }
      if (cameraOn) {
        URL.revokeObjectURL(url);
      } else {
        if (photoUrl) URL.revokeObjectURL(photoUrl);
        photoUrl = url;
        still.src = url;
        still.classList.remove("hidden");
      }
      const sentAt = Date.now();
      const frameSeq = nextSeq();
      const ok = send({
        v: 2,
        type: "frame",
        session_id: sessionId,
        seq: frameSeq,
        ts_ms: sentAt,
        w: shot.w,
        h: shot.h,
        jpeg_b64: shot.jpeg_b64,
      });
      if (ok) hud = noteFrameSent(hud, frameSeq, sentAt);
      if (!ok) setSpeaker("helper", "Not connected.");
    } catch {
      if (photoUrl !== url) URL.revokeObjectURL(url);
      setSpeaker("helper", "Could not read that photo.");
    }
  }

  function renderMic() {
    const ready = Boolean(voice && voice.supported && voice.supported.stt);
    micBtn.disabled = !ready;
    micBtn.setAttribute("aria-pressed", listening ? "true" : "false");
    micBtn.textContent = listening ? "Stop mic" : "Mic";
  }

  async function onMic() {
    voice = voice || (await voiceReady);
    flushSpeech();
    if (!voice || !voice.supported || !voice.supported.stt) return;
    try {
      await voice.unlockAudio();
    } catch {
      /* typed input still works */
    }
    if (listening) {
      voice.stopListening();
      listening = false;
    } else {
      voice.startListening();
      listening = true;
    }
    renderMic();
  }

  async function choosePack(next) {
    if (!PACK_LABEL[next]) return;
    pack = next;
    packLabel.textContent = PACK_LABEL[next];
    if (next === "pc_build") powerBtn.classList.remove("hidden");
    picker.classList.add("hidden");
    stage.classList.remove("hidden");
    voice = voice || (await voiceReady);
    flushSpeech();
    if (voice) {
      try {
        await voice.unlockAudio();
      } catch {
        /* typed input still works */
      }
    }
    renderMic();
    connect();
    paint(Date.now());
  }

  picker.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-pack]");
    if (!button) return;
    choosePack(button.getAttribute("data-pack"));
  });
  startBtn.addEventListener("click", () => {
    startCamera();
  });
  powerBtn.addEventListener("click", () => {
    const ok = send({
      v: 2,
      type: "confirm",
      session_id: sessionId,
      what: "power_off",
      value: true,
    });
    if (!ok) setSpeaker("helper", "Not connected.");
  });
  document.getElementById("upload").addEventListener("change", (event) => {
    onUpload(event);
  });
  document.getElementById("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = typedEl.value;
    typedEl.value = "";
    if (!String(text || "").trim()) return;
    setInterim(String(text).trim());
    sendUser(text, "typed");
  });
  micBtn.addEventListener("click", () => {
    onMic();
  });
  document.getElementById("market-dismiss").addEventListener("click", () => {
    marketEl.classList.add("hidden");
    marketBody.replaceChildren();
  });
  window.addEventListener("resize", () => paint(Date.now()));
  video.addEventListener("loadedmetadata", () => paint(Date.now()));
  if (reducedQuery && typeof reducedQuery.addEventListener === "function") {
    reducedQuery.addEventListener("change", () => paint(Date.now()));
  }

  renderMic();
  raf = window.requestAnimationFrame(loop);
  void raf;
}

async function loadVoice(handlers) {
  try {
    const mod = await import("./voice.js");
    if (!mod || typeof mod.createVoice !== "function") return null;
    return mod.createVoice(handlers);
  } catch {
    return null;
  }
}

if (typeof document !== "undefined") boot();
