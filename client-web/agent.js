import { bootPairCamera, setupPairCall } from './pair.js';
// Agent call page. Speaks the v2 WebSocket contract on /ws2.
// Frames exist only as the JPEG about to be sent. Nothing is written to storage.

import { paintDraw, applyDraw, pruneDraw, viewTransform, visibleOps } from "./draw.js";
import { writeFrame } from "./live.js";
import { sharpCanvasSize } from "./overlay.js";
import {
  AUDIO_FALLBACK_MS,
  ERROR_HTTPS,
  TEST_LINE,
  createCallUi,
  fallbackDecision,
  replyLines,
} from "./ui.js";
import {
  bargeSpeech,
  dbfs,
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

import { nextTurnState, statusLine } from "./turn.js";

// Same names and order as ios/AEyeCore Modes.all; pack null means "coming soon". PC Build is centred at launch.
const MODES = [
  { id: "general", title: "General", pack: "general" },
  { id: "pc_build", title: "PC Build", pack: "pc_build" },
  { id: "cooking", title: "Cooking", pack: "cooking" },
  { id: "assemble", title: "Assembly", pack: "assemble" },
  { id: "mechanic", title: "Mechanic", pack: null },
  { id: "plumbing", title: "Plumbing", pack: null },
  { id: "engineering", title: "Engineering", pack: null },
];
const DEFAULT_MODE = 1;
const RING_SLOT = 84;
const PACK_LABEL = Object.fromEntries(MODES.filter((m) => m.pack).map((m) => [m.pack, m.title]));
const PRESENCE_STATES = ["idle", "listening", "thinking", "speaking"];

const FRAME_MS = 1000;
const BOARD_ID = "demo-b650";
const TRACK_W = 320;

function boot() {
  if (bootPairCamera()) return;
  const picker = document.getElementById("picker");
  const stage = document.getElementById("stage");
  const video = document.getElementById("camera");
  const still = document.getElementById("still");
  const drawCanvas = document.getElementById("draw");
  const callEl = document.getElementById("call");
  const ringEl = document.getElementById("ring");
  const ringTitle = document.getElementById("ring-title");
  const ringHint = document.getElementById("ring-hint");
  const dotEl = document.getElementById("presence-dot");
  const elapsedEl = document.getElementById("elapsed");
  const linkEl = document.getElementById("link");
  const captionEl = document.getElementById("caption");
  const captionEyebrow = document.getElementById("caption-eyebrow");
  const captionSpeaker = document.getElementById("caption-speaker");
  const powerGate = document.getElementById("power-gate");
  const cameraIcon = document.getElementById("camera-icon");
  const micIcon = document.getElementById("mic-icon");
  const backdropEl = document.getElementById("backdrop");
  const settingsEl = document.getElementById("settings");
  const marketTitle = document.getElementById("market-title");
  const permissionEl = document.getElementById("permission");
  const permissionTitle = document.getElementById("permission-title");
  const permissionText = document.getElementById("permission-text");
  const connStatusEl = document.getElementById("conn-status");
  const serverHostEl = document.getElementById("server-host");
  const packLabel = document.getElementById("pack-label");
  const errorEl = document.getElementById("error");
  const noticeEl = document.getElementById("notice");
  const marketEl = document.getElementById("market");
  const marketBody = document.getElementById("market-body");
  const repliesEl = document.getElementById("replies");
  const interimEl = document.getElementById("interim");
  const typedEl = document.getElementById("typed");
  const micBtn = document.getElementById("mic");
  const holdBtn = document.getElementById("hold");
  const sensEl = document.getElementById("sensitivity");
  const ambientEl = document.getElementById("ambient");
  // Hold to talk is the reliable mode in a loud hall; ?hold=1 forces it, a noisy calibration turns it on.
  let holdMode = new URLSearchParams(location.search).get("hold") === "1";
  let holdPressed = false;
  const startBtn = document.getElementById("start-camera");
  const powerBtn = document.getElementById("power-off");
  const overlayEl = document.getElementById("start-overlay");
  const transcriptBtn = document.getElementById("transcript-toggle");
  const transcriptList = document.getElementById("transcript-list");
  const muteBtn = document.getElementById("mute");
  const volumeEl = document.getElementById("volume");
  const waveEl = document.getElementById("wave");
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

  let sessionId = randomId();
  const params = new URLSearchParams(location.search);
  // Server voice (Cartesia when keyed, else Kokoro on the box) by default; the browser voice is the last resort.
  // ?tts=cartesia means server TTS with a Cartesia voice from /api/voices.
  const storedVoice = (() => { try { return safeStorage()?.getItem("aeye.voice") || ""; } catch { return ""; } })();
  const wantCartesia = params.get("tts") === "cartesia";
  let tts = !wantCartesia && (params.get("tts") === "browser" || storedVoice === "browser") ? "browser" : "server";
  let ttsVoice = storedVoice && storedVoice !== "browser" ? storedVoice : "";
  const voicePick = document.getElementById("voice-pick");
  let stt = params.get("stt") === "server" ? "server" : "browser";
  const sttLabel = document.getElementById("stt-mode");
  const reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let ui = createCallUi({ storage: safeStorage() });

  let pack = "";
  let socket = null;
  let retryTimer = 0;
  let reconnectDelay = 500;
  let turn = nextTurnState(null, {}, Date.now());
  let pendingText = null;
  let seq = 0;
  let cameraOn = false;
  let starting = false;
  let frameTimer = 0;
  let photoUrl = "";
  let drawState = applyDraw(null, null, 0);
  // Presence as CallState.reduce does it: thinking or speaking by one agent makes the other idle.
  let agents = { helper: "idle", shopper: "idle" };
  let link = "connecting";
  let ended = false;
  let callStartedAt = 0;
  let powerConfirmed = false;
  let ringIndex = DEFAULT_MODE;
  let voice = null;
  let listening = false;
  let raf = 0;
  let speech = emptySpeech();
  const talkQueue = [];
  let talkBusy = false;
  const fallbackTimers = new Map();
  const waveLevels = [];
  let lastUiTick = 0;
  const tracker = createTracker();
  let tracks = new Map();
  let book = initialTrackerBook();
  let pendingPlan = null;
  let trackBusy = false;
  let lastTrackAt = null;
  let hud = initialHud();

  function voiceOptions() {
    return {
      holdToTalk: holdMode,
      sensitivity: Number(sensEl && sensEl.value) || 5,
      onAmbient: (reading) => {
        if (ambientEl) ambientEl.textContent = `Noise ${dbfs(reading.rms)} dB${reading.noisy ? " (loud)" : ""}`;
        if (reading.noisy && reading.calibrated && !holdMode) void enableHold();
      },
      onFinal: (text) => {
        const clean = String(text || "").trim();
        if (!clean) return;
        ui.dispatch({ type: "final", text: clean, now: Date.now() });
        renderCall();
        sendUser(clean, stt === "server" ? "server_stt" : "browser_stt");
      },
      onInterim: (text) => {
        turnEvent({ type: "interim", text });
        ui.dispatch({ type: "interim", text: String(text || "").trim(), now: Date.now() });
        renderCall();
      },
      onState: (state) => {
        if (state === "listening") {
          listening = true;
          ui.dispatch({ type: "mic_start" });
          turnEvent({ type: "mic_start" });
        } else if (state === "idle" || state === "stopped") {
          listening = false;
          ui.dispatch({ type: "mic_stop" });
          turnEvent({ type: "mic_stop" });
        }
        renderMic();
        renderCall();
      },
      onBargeIn: (id, ms) => {
        speech = bargeSpeech(speech);
        talkQueue.length = 0;
        talkBusy = false;
        clearAllFallbacks();
        ui.dispatch({ type: "audio_ended", utteranceId: "", now: Date.now() });
        send({
          v: 2,
          type: "barge_in",
          session_id: sessionId,
          utterance_id: id,
          at_ms: Math.max(0, Math.round(Number(ms) || 0)),
        });
        renderCall();
      },
      onLevel: (level) => {
        const n = Number(level);
        const value = Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
        waveLevels.push(value);
        while (waveLevels.length > 28) waveLevels.shift();
        drawWave();
      },
      onMicError: (kind) => {
        if (kind === "unsupported") {
          turnEvent({ type: "cause", detail: "Browser can't do speech recognition: using server" });
          void switchToServerStt();
          return;
        }
        if (kind === "no_speech") {
          turnEvent({ type: "cause", detail: "No speech detected" });
          return;
        }
        if (kind === "denied") {
          turnEvent({ type: "cause", detail: "Mic blocked" });
          ui.dispatch({ type: "permission_denied" });
          renderCall();
        }
      },
      onSpeakStart: (id) => {
        if (id !== "test-voice") markSound();
      },
      onSpeakEnd: () => {
        talkBusy = false;
        ui.dispatch({ type: "audio_ended", utteranceId: "", now: Date.now() });
        renderCall();
        pumpTalk();
      },
      onAudioError: (id) => {
        failAudio(typeof id === "string" ? id : "");
      },
      sttMode: stt,
      onAudioChunk: (pcm16Base64, audioSeq, final) => {
        if (turn.stage === "hearing") turnEvent({ type: "interim", text: "Speech detected" });
        if (final) turnEvent({ type: "sent" });
        send({
          v: 2,
          type: "audio_in",
          session_id: sessionId,
          seq: audioSeq,
          sample_rate: 16000,
          pcm16_b64: pcm16Base64,
          final: Boolean(final),
        });
      },
    };
  }

  function randomId() {
    if (globalThis.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
    return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function wsUrl() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${location.host}/ws2?token=${encodeURIComponent(new URLSearchParams(location.search).get("token") || "")}`;
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

  function setLink(next) {
    link = next;
    renderLink();
  }

  function renderLink() {
    linkEl.textContent = link === "reconnecting" ? "Reconnecting…" : "Connecting…";
    linkEl.classList.toggle("hidden", link === "live" || !pack);
    const labels = { connecting: "Connecting…", live: "Connected", reconnecting: "Reconnecting…" };
    if (connStatusEl) connStatusEl.textContent = pack ? labels[link] : "Not in a call";
  }

  function applyAgentState(agent, state) {
    if (agent !== "helper" && agent !== "shopper") return;
    if (!PRESENCE_STATES.includes(state)) return;
    agents = { ...agents, [agent]: state };
    if (state === "thinking" || state === "speaking") agents[agent === "helper" ? "shopper" : "helper"] = "idle";
    renderPresence();
  }

  function renderPresence() {
    const active = agents.shopper !== "idle" ? "shopper" : agents.helper !== "idle" ? "helper" : "";
    const state = active ? agents[active] : "idle";
    dotEl.setAttribute("data-agent", active);
    dotEl.setAttribute("data-state", state);
    const who = active === "shopper" ? "Shopper" : "Helper";
    dotEl.setAttribute("aria-label", active ? `${who} is ${state}` : "");
  }

  function showProblem(text) {
    ui.dispatch({ type: "error", message: text || "" });
    renderCall();
  }

  function turnEvent(event) {
    const before = turn.timestamps;
    turn = nextTurnState(turn, event, Date.now());
    if (turn.timestamps !== before) {
      ui.dispatch({ type: "turn_times", timestamps: turn.timestamps });
      renderTranscript(ui.getState());
    }
    document.getElementById("pipeline").textContent = statusLine(turn, Date.now());
  }

  const pipelineTimer = window.setInterval(() => {
    const retries = turn.retries;
    turnEvent({ type: "tick" });
    if (turn.retries > retries && pendingText) send(pendingText);
  }, 100);
  window.addEventListener("pagehide", () => window.clearInterval(pipelineTimer));

  function sendUser(text, source) {
    const clean = String(text || "").trim();
    if (!clean) return false;
    pendingText = {
      v: 2,
      type: "user_text",
      session_id: sessionId,
      text: clean,
      final: true,
      source,
    };
    turnEvent({ type: "sent", text: clean });
    const ok = send(pendingText);
    if (ok) hud = noteFinalWords(hud, Date.now());
    if (!ok) showProblem("Not connected.");
    return ok;
  }

  function sendHello() {
    if (!pack) return false;
    const hello = {
      v: 2,
      type: "hello",
      session_id: sessionId,
      pack,
      client: "web",
      tts,
      stt,
      camera: cameraOn,
    };
    if (tts === "server" && ttsVoice) hello.voice = ttsVoice;
    if (pack === "pc_build") hello.board_id = BOARD_ID;
    const ok = send(hello);
    if (ok) ui.dispatch({ type: "hello_sent" });
    return ok;
  }

  function connect() {
    if (!pack) return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    const ws = new WebSocket(wsUrl());
    socket = ws;
    ws.addEventListener("open", () => {
      if (socket !== ws) return;
      reconnectDelay = 500;
      // A fresh socket is a fresh server session: the power-off gate, drawing and presence start over.
      powerConfirmed = false;
      drawState = applyDraw(null, null, 0);
      agents = { helper: "idle", shopper: "idle" };
      ui.dispatch({ type: "error", message: "" });
      setLink("live");
      renderPresence();
      sendHello();
      turnEvent({ type: "connected" });
      renderCall();
    });
    ws.addEventListener("message", (event) => {
      if (socket !== ws || typeof event.data !== "string") return;
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      onServer(message);
    });
    ws.addEventListener("close", () => {
      if (socket !== ws) return;
      socket = null;
      window.clearTimeout(retryTimer);
      setLink("reconnecting");
      turnEvent({ type: "closed" });
      if (ended) return;
      retryTimer = window.setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(10000, reconnectDelay * 2);
    });
  }

  // A getter: sessionId changes when a new call starts, and a captured value sent stale ids (seen in the two-page run).
  const onPair = setupPairCall(send, () => sessionId);

  function onServer(message) {
    if (!message || typeof message !== "object") return;
    onPair(message);
    const now = Date.now();
    if (message.type === "turn") {
      if (message.stage === "received") pendingText = null;
      if (message.text && stt === "server" && !turn.text) {
        ui.dispatch({ type: "final", text: message.text, now });
      }
      turnEvent(message);
      renderCall();
      return;
    }
    if (message.type === "reply_delta") {
      turnEvent({ type: "first_text" });
      ui.dispatch({ type: "reply_delta", turnId: `turn:${message.turn_id}`, agent: message.agent, text: message.text });
      renderCall();
      return;
    }
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
      applyAgentState(message.agent, message.state);
      ui.dispatch({ type: "agent_state", agent: message.agent, state: message.state });
      renderCall();
      return;
    }
    if (message.type === "say") {
      turnEvent({ type: "first_text" });
      const result = pushSay(speech, message);
      speech = result.state;
      if (result.reset) {
        talkQueue.length = 0;
        talkBusy = false;
        clearAllFallbacks();
        if (voice) voice.cancel();
      }
      for (const line of result.speak) {
        ui.dispatch({
          type: "say",
          agent: line.agent,
          utteranceId: line.utteranceId,
          text: line.text,
          part: line.part,
          turnId: speech.turnId,
          now,
        });
        utteranceTurn.set(line.utteranceId, speech.turnId);
        // Server audio is synthesized sentence by sentence, so later sentences can wait longer than 1.5 s.
        // Arm the browser fallback only until the first audio of this turn arrives.
        if (tts === "server" && !audioTurns.has(speech.turnId)) armFallback(line.utteranceId);
      }
      if (tts === "browser" && result.speak.length) enqueueTalk(result.speak);
      renderCall();
      return;
    }
    if (message.type === "audio" && voice) {
      const id = typeof message.utterance_id === "string" ? message.utterance_id : "";
      const turnOfAudio = utteranceTurn.get(id);
      if (turnOfAudio != null) {
        audioTurns.add(turnOfAudio);
        for (const [uid, tid] of utteranceTurn) if (tid === turnOfAudio) clearFallback(uid);
      }
      clearFallback(id);
      ui.dispatch({ type: "audio_started", utteranceId: id, now });
      renderCall();
      try {
        voice.playPcm(message.utterance_id, message.pcm16_b64, Boolean(message.final));
      } catch {
        failAudio(id);
      }
      return;
    }
    if (message.type === "market_results") {
      showMarket(message.result);
      return;
    }
    if (message.type === "error") {
      showProblem(message.message || "Something went wrong.");
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

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  // Only web links open; anything else the server sends is dropped (as MarketSheet.safeURL).
  function safeLink(url) {
    try {
      const parsed = new URL(String(url || ""));
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
    } catch {
      return "";
    }
  }

  const CHIP = { fits: "Fits", no: "Does not fit", unverified: "Unverified" };

  function showMarket(result) {
    marketBody.replaceChildren();
    const category = String((result && result.category) || "");
    marketTitle.textContent = category ? category.charAt(0).toUpperCase() + category.slice(1) : "Options";
    const items = result && Array.isArray(result.items) ? result.items.slice(0, 3) : [];
    if (!items.length) marketBody.append(el("p", "market-empty", "No matching offers."));
    for (const item of items) {
      const status = item.compat && CHIP[item.compat.status] ? item.compat.status : "unverified";
      const card = el("article", "offer glass");
      const head = el("div", "offer-head");
      head.append(el("p", "offer-title", item.title || "Offer"), el("span", `status-chip ${status}`, CHIP[status]));
      card.append(head);
      if (item.retailer) card.append(el("p", "offer-retailer", item.retailer));
      let price = money(item.price_usd);
      if (price && item.shipping_usd != null && money(item.shipping_usd)) price += ` + ${money(item.shipping_usd)} shipping`;
      if (price) card.append(el("p", "offer-price", price));
      const line = fitsLine(item);
      if (line.text && !Object.values(CHIP).includes(line.text)) card.append(el("p", "offer-why", line.text));
      const href = safeLink(item.url);
      if (href) {
        const a = el("a", "", `View at ${item.retailer || "store"} ↗`);
        a.href = href;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        card.append(a);
      }
      marketBody.append(card);
    }
    if (result && result.note) marketBody.append(el("p", "market-note", String(result.note)));
    openSheet(marketEl);
  }

  function openSheet(sheet) {
    for (const other of [marketEl, settingsEl]) if (other && other !== sheet) other.classList.add("hidden");
    sheet.classList.remove("hidden");
    if (backdropEl) backdropEl.classList.remove("hidden");
  }

  function closeSheets() {
    marketEl.classList.add("hidden");
    marketBody.replaceChildren();
    if (settingsEl) settingsEl.classList.add("hidden");
    if (backdropEl) backdropEl.classList.add("hidden");
  }

  function showPermission(title, text) {
    permissionTitle.textContent = title;
    permissionText.textContent = text;
    permissionEl.classList.remove("hidden");
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
    turnEvent({ type: "first_sound" });
    hud = noteFirstSound(hud, Date.now());
  }

  function enqueueTalk(lines) {
    for (const line of lines) talkQueue.push(line);
    pumpTalk();
  }

  function pumpTalk() {
    if (talkBusy || tts === "server" || !voice || !talkQueue.length) return;
    const line = talkQueue.shift();
    talkBusy = true;
    ui.dispatch({ type: "audio_started", utteranceId: line.utteranceId, now: Date.now() });
    voice.speak(line.utteranceId, line.text);
    renderCall();
  }

  function clearFallback(id) {
    const timer = fallbackTimers.get(id);
    if (timer) window.clearTimeout(timer);
    fallbackTimers.delete(id);
  }

  function clearAllFallbacks() {
    for (const timer of fallbackTimers.values()) window.clearTimeout(timer);
    fallbackTimers.clear();
  }

  const utteranceTurn = new Map();
  const audioTurns = new Set();

  function armFallback(id) {
    if (tts !== "server") return;
    clearFallback(id);
    const wait = ui.getState().waits[id];
    if (!wait || wait.audioSeenMs != null || wait.fellBack) return;
    const delay = Math.max(0, AUDIO_FALLBACK_MS - (Date.now() - wait.sayTimeMs));
    const timer = window.setTimeout(() => runFallback(id), delay);
    fallbackTimers.set(id, timer);
  }

  function runFallback(id) {
    fallbackTimers.delete(id);
    const wait = ui.getState().waits[id];
    if (!wait || wait.fellBack) return;
    const now = Date.now();
    if (!fallbackDecision(wait.sayTimeMs, wait.audioSeenMs, now).fallback) {
      armFallback(id);
      return;
    }
    ui.dispatch({ type: "audio_timeout", utteranceId: id, now });
    const next = ui.getState().waits[id];
    if (voice && next && next.text) voice.speak(id, next.text);
    renderCall();
  }

  function failAudio(id) {
    const wait = ui.getState().waits[id];
    if (!wait || wait.fellBack) return;
    clearFallback(id);
    ui.dispatch({ type: "audio_error", utteranceId: id, now: Date.now() });
    const next = ui.getState().waits[id];
    if (voice && next && next.text) voice.speak(id, next.text);
    renderCall();
  }

  function placeDevHud(view, poses) {
    if (!devEl) return;
    const box = devHudPosition(view, poses || {});
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
    hud = notePaint(hud, now);
    const drawCtx = fitCanvas(drawCanvas, view.w, view.h);
    const frameState = cameraOn ? anchoredState(drawState, tracks, now) : drawState;
    paintDraw(drawCtx, frameState, view, now, reduced);
    placeDevHud(view, null);
  }

  function renderElapsed(now) {
    if (!callStartedAt) return;
    const seconds = Math.max(0, Math.floor((now - callStartedAt) / 1000));
    const text = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    if (elapsedEl.textContent !== text) elapsedEl.textContent = text;
  }

  function loop() {
    const now = Date.now();
    stepTracker(now);
    if (now - lastUiTick > 200) {
      lastUiTick = now;
      const before = ui.getState().caption;
      ui.dispatch({ type: "tick", now });
      if (ui.getState().caption !== before) renderUserCaption(ui.getState());
      renderElapsed(now);
    }
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
    window.clearInterval(frameTimer);
    frameTimer = 0;
    renderCamera();
    send({ v: 2, type: "camera", session_id: sessionId, on: false });
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
      ui.dispatch({ type: "https" });
      renderCall();
      showPermission("Camera needs HTTPS", ERROR_HTTPS);
      return;
    }
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
      showProblem("No camera in this browser. Use Upload photo.");
      return;
    }
    starting = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      if (!pack) {
        // The call ended while the camera prompt was open: do not leave a live camera on the ring screen.
        for (const track of stream.getTracks()) track.stop();
        return;
      }
      hideStill();
      video.srcObject = stream;
      video.playsInline = true;
      video.muted = true;
      // On before play(): a play() that never settles must not leave a live camera the button can't stop.
      cameraOn = true;
      await video.play().catch(() => {});
      if (video.srcObject !== stream) return;
      renderCamera();
      send({ v: 2, type: "camera", session_id: sessionId, on: true });
      commitTracker("draw");
      sendLiveFrame();
      startFrames();
    } catch (err) {
      stopCamera();
      const name = err && err.name;
      if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
        showPermission("Camera access is off",
          "A-eye looks through the camera to point at parts while you work. Allow the camera for this site in your browser settings, or upload a photo from Settings.");
      } else {
        showProblem("Camera unavailable. Use Upload photo.");
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
        showProblem("Could not read that photo.");
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
      if (!ok) showProblem("Not connected.");
    } catch {
      if (photoUrl !== url) URL.revokeObjectURL(url);
      showProblem("Could not read that photo.");
    }
  }

  function renderCamera() {
    startBtn.setAttribute("aria-pressed", cameraOn ? "true" : "false");
    startBtn.setAttribute("aria-label", cameraOn ? "Camera off" : "Camera on");
    cameraIcon.setAttribute("href", cameraOn ? "#i-camera" : "#i-camera-off");
  }

  // CallScreen.micButton: mic when listening, struck-through mic in the warn colour when muted.
  function renderMic() {
    const ready = Boolean(voice && voice.supported && voice.supported.stt);
    micBtn.disabled = !ready;
    const on = ui.getState().micOn;
    micBtn.setAttribute("aria-pressed", on ? "true" : "false");
    micBtn.setAttribute("data-muted", ready && !on ? "true" : "false");
    micIcon.setAttribute("href", on ? "#i-mic" : "#i-mic-off");
    micBtn.setAttribute("aria-label", on ? "Stop microphone" : "Start microphone");
  }

  function applyAudioPrefs() {
    const st = ui.getState();
    if (!voice) return;
    if (typeof voice.setMuted === "function") voice.setMuted(st.muted);
    if (typeof voice.setVolume === "function") voice.setVolume(st.volume);
  }

  function securePage() {
    return Boolean(window.isSecureContext);
  }

  async function startMic() {
    await voice.startListening();
    if (voice.isListening()) {
      ui.dispatch({ type: "mic_start" });
      turnEvent({ type: "mic_start" });
      renderCall();
    }
  }

  async function onMic() {
    voice = voice || (await rebuildVoice());
    if (!voice || !voice.supported || !voice.supported.stt) return;
    if (!securePage()) {
      ui.dispatch({ type: "https" });
      renderCall();
      return;
    }
    void voice.unlockAudio();
    if (ui.getState().micOn) {
      voice.stopListening();
      ui.dispatch({ type: "mic_stop" });
      turnEvent({ type: "mic_stop" });
      renderCall();
    }
    else void startMic();
    pumpTalk();
  }

  function onStartTap() {
    ui.dispatch({ type: "tap_start" });
    renderCall();
    if (!voice) return;
    voice.primeSpeech();
    void voice.unlockAudio();
    applyAudioPrefs();
    if (!securePage()) {
      ui.dispatch({ type: "https" });
      renderCall();
      return;
    }
    if (voice.supported && voice.supported.stt) void startMic();
  }

  async function onTestVoice() {
    if (!voice) return;
    void voice.unlockAudio();
    applyAudioPrefs();
    if (tts === "server") {
      try {
        const reply = await fetch(`/api/voice_sample?voice=${encodeURIComponent(ttsVoice)}`);
        if (reply.ok) {
          const sample = await reply.json();
          voice.playPcm("test-voice", sample.pcm16_b64, true);
          return;
        }
      } catch {
        // fall through to the browser voice
      }
    }
    voice.speak("test-voice", TEST_LINE);
  }

  async function loadVoices() {
    if (!voicePick) return;
    let listed = [];
    try {
      const reply = await fetch("/api/voices");
      if (reply.ok) listed = (await reply.json()).voices || [];
    } catch {
      listed = [];
    }
    voicePick.textContent = "";
    for (const item of listed) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.label + (item.default ? " (default)" : "");
      voicePick.append(option);
    }
    const browserOption = document.createElement("option");
    browserOption.value = "browser";
    browserOption.textContent = "Browser voice (robotic)";
    voicePick.append(browserOption);
    const fallback = (listed.find((item) => item.default) || listed[0] || { id: "browser" }).id;
    if (wantCartesia && !String(ttsVoice).startsWith("cartesia:")) {
      const cartesia = listed.find((item) => item.engine === "cartesia" && item.default)
        || listed.find((item) => item.engine === "cartesia");
      if (cartesia) {
        ttsVoice = cartesia.id;
        sendHello();
      }
    }
    voicePick.value = tts === "browser" ? "browser" : (ttsVoice || fallback);
  }

  function onVoicePick() {
    const picked = voicePick.value;
    tts = picked === "browser" ? "browser" : "server";
    ttsVoice = picked === "browser" ? "" : picked;
    try {
      safeStorage()?.setItem("aeye.voice", picked);
    } catch {
      // per-viewer convenience only
    }
    sendHello();
    void onTestVoice();
  }

  async function choosePack(next) {
    if (!PACK_LABEL[next] || pack) return;
    pack = next;
    ended = false;
    sessionId = randomId();
    ui = createCallUi({ storage: safeStorage() });
    turn = nextTurnState(null, {}, Date.now());
    speech = emptySpeech();
    powerConfirmed = false;
    agents = { helper: "idle", shopper: "idle" };
    callStartedAt = Date.now();
    elapsedEl.textContent = "0:00";
    packLabel.textContent = PACK_LABEL[next];
    link = "connecting";
    renderPresence();
    renderCamera();
    ui.dispatch({ type: "pack", pack: next });
    picker.classList.add("hidden");
    callEl.classList.remove("hidden");
    voice = await rebuildVoice();
    if (voice && !voice.supported.stt && stt !== "server") {
      stt = "server";
      ui.dispatch({ type: "stt_unsupported" });
      voice = await rebuildVoice();
    }
    applyAudioPrefs();
    renderCall();
    connect();
    paint(Date.now());
  }

  async function enableHold() {
    holdMode = true;
    renderHold();
    if (stt !== "server") await switchToServerStt();
    if (voice && typeof voice.setHoldMode === "function") voice.setHoldMode(true);
    if (voice && !voice.isListening() && voice.supported && voice.supported.stt) await startMic();
    renderHold();
  }

  function renderHold() {
    if (!holdBtn) return;
    holdBtn.classList.toggle("hold-default", holdMode);
    holdBtn.setAttribute("aria-pressed", holdPressed ? "true" : "false");
    holdBtn.setAttribute("aria-label", holdPressed ? "Listening, release to send" : "Hold to talk");
  }

  // CallController.end: back to the mode ring with the same mode selected.
  function endCall() {
    if (!pack) return;
    ended = true;
    if (cameraOn || video.srcObject) stopCamera();
    holdPressed = false;
    if (voice) {
      voice.stopListening();
      if (typeof voice.cancel === "function") voice.cancel();
    }
    talkQueue.length = 0;
    talkBusy = false;
    clearAllFallbacks();
    window.clearTimeout(retryTimer);
    const ws = socket;
    socket = null;
    if (ws) ws.close();
    pack = "";
    callStartedAt = 0;
    drawState = applyDraw(null, null, 0);
    agents = { helper: "idle", shopper: "idle" };
    hideStill();
    closeSheets();
    permissionEl.classList.add("hidden");
    overlayEl.classList.add("hidden");
    callEl.classList.add("hidden");
    picker.classList.remove("hidden");
    renderLink();
    paint(Date.now());
  }

  function ringButtons() {
    return ringEl && typeof ringEl.querySelectorAll === "function" ? [...ringEl.querySelectorAll("button[data-mode]")] : [];
  }

  // ModeRing.swift: centred item 78 px with a white ring, neighbours 52 / 42 / 34 and fading.
  function renderRing() {
    ringButtons().forEach((button, i) => {
      const dist = Math.min(Math.abs(i - ringIndex), 3);
      button.setAttribute("data-dist", String(dist));
      button.setAttribute("aria-current", dist === 0 ? "true" : "false");
    });
    const mode = MODES[ringIndex];
    ringTitle.textContent = mode.title;
    ringHint.textContent = mode.pack ? "tap to start" : "coming soon";
  }

  function scrollRingTo(i, smooth) {
    if (!ringEl || typeof ringEl.scrollTo !== "function") return;
    ringEl.scrollTo({ left: i * RING_SLOT, behavior: smooth && !reducedMotion() ? "smooth" : "auto" });
  }

  function onRingScroll() {
    const i = Math.max(0, Math.min(MODES.length - 1, Math.round(ringEl.scrollLeft / RING_SLOT)));
    if (i === ringIndex) return;
    ringIndex = i;
    renderRing();
  }

  function shake(button) {
    if (reducedMotion()) return;
    button.classList.remove("shake");
    void button.offsetWidth;
    button.classList.add("shake");
  }

  async function onHoldDown() {
    if (holdPressed) return;
    holdPressed = true;
    renderHold();
    if (voice) void voice.unlockAudio();
    if (!holdMode || stt !== "server" || !voice || !voice.isListening()) await enableHold();
    if (holdPressed && voice && typeof voice.holdStart === "function") {
      voice.holdStart();
      turnEvent({ type: "interim", text: "Holding to talk" });
    }
  }

  function onHoldUp() {
    if (!holdPressed) return;
    holdPressed = false;
    if (voice && typeof voice.holdEnd === "function") voice.holdEnd();
    renderHold();
  }

  async function switchToServerStt() {
    if (stt === "server") return;
    const micWasOn = ui.getState().micOn;
    stt = "server";
    ui.dispatch({ type: "stt_unsupported" });
    voice = await rebuildVoice();
    applyAudioPrefs();
    sendHello();
    renderCall();
    // The mic was on when browser recognition failed: keep listening through server STT.
    if (voice && micWasOn && voice.supported && voice.supported.stt) void startMic();
  }

  function renderCall() {
    const st = ui.getState();
    errorEl.textContent = st.error || "";
    errorEl.classList.toggle("hidden", !st.error);
    powerGate.classList.toggle("hidden", pack !== "pc_build" || powerConfirmed);
    renderLink();
    const notes = [st.sttNotice, st.voiceNotice].filter(Boolean);
    noticeEl.textContent = notes.join(" ");
    noticeEl.classList.toggle("hidden", notes.length === 0);
    renderReplies(st);
    renderUserCaption(st);
    renderTranscript(st);
    muteBtn.setAttribute("aria-pressed", st.muted ? "true" : "false");
    muteBtn.textContent = st.muted ? "Unmute" : "Mute";
    if (document.activeElement !== volumeEl) volumeEl.value = String(st.volume);
    overlayEl.classList.toggle("hidden", !st.showStart);
    if (sttLabel) sttLabel.textContent = stt === "server" ? "Whisper" : "Browser";
    renderMic();
  }

  // CaptionCard.swift: eyebrow A-EYE or SHOPPER, then the reply. The web streams a turn sentence by sentence,
  // so the card holds the whole current turn (clamped to 8 lines) instead of only the last sentence.
  function renderReplies(st) {
    repliesEl.replaceChildren();
    const lines = replyLines(st);
    lines.forEach((line, i) => {
      if (i) repliesEl.append(document.createTextNode(" "));
      repliesEl.append(el("span", line.active ? "line active" : "line", line.text));
    });
    const last = lines[lines.length - 1];
    const shopper = Boolean(last && last.speaker === "Shopper");
    captionEl.setAttribute("data-agent", shopper ? "shopper" : "helper");
    captionEyebrow.textContent = shopper ? "SHOPPER" : "A-EYE";
    captionSpeaker.textContent = shopper ? "Shopper" : "Helper";
    captionEl.classList.toggle("hidden", !lines.length && !st.error);
  }

  function renderUserCaption(st) {
    const cap = st.caption || {};
    interimEl.replaceChildren();
    interimEl.classList.toggle("is-interim", cap.kind === "interim" && cap.visible);
    interimEl.classList.toggle("is-gone", !cap.visible);
    if (!cap.visible || !cap.text) return;
    interimEl.append(document.createTextNode(cap.text));
    if (cap.kind === "interim") {
      const caret = document.createElement("span");
      caret.className = "caret";
      caret.setAttribute("aria-hidden", "true");
      interimEl.append(caret);
    }
  }

  function renderTranscript(st) {
    transcriptList.replaceChildren();
    for (const line of st.transcript) {
      const item = document.createElement("li");
      const who = document.createElement("span");
      who.className = "who";
      who.style.color = line.color || "#f4f7fb";
      who.textContent = line.speaker;
      item.append(who, document.createTextNode(line.text));
      if (line.timestamps) {
        const times = document.createElement("small");
        times.textContent = " · " + ["sent", "received", "first_text", "first_sound"].map(key => {
          const at = line.timestamps[key];
          return `${key.replaceAll("_", " ")}: ${at == null ? "—" : new Date(at).toISOString()}`;
        }).join(" · ");
        item.append(times);
      }
      transcriptList.append(item);
    }
    if (transcriptBtn.getAttribute("aria-expanded") === "true") {
      transcriptList.scrollTop = transcriptList.scrollHeight;
    }
  }

  function drawWave() {
    if (!waveEl) return;
    const ctx = waveEl.getContext("2d");
    if (!ctx) return;
    const w = waveEl.width;
    const h = waveEl.height;
    ctx.clearRect(0, 0, w, h);
    const levels = waveLevels.length ? waveLevels : [0];
    const gap = 2;
    const bw = Math.max(2, (w - gap * (levels.length - 1)) / levels.length);
    ctx.fillStyle = "#8eb6ff";
    for (let i = 0; i < levels.length; i += 1) {
      const amp = Math.max(0, Math.min(1, levels[i] || 0));
      const bh = Math.max(2, amp * (h - 2));
      ctx.fillRect(i * (bw + gap), (h - bh) / 2, bw, bh);
    }
  }

  // Tap the centred mode to start; a coming-soon mode shakes. With a mouse there is no swipe, so tapping a side
  // mode that works starts it directly (iOS only scrolls it to the centre).
  picker.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-mode]");
    if (!button) return;
    const i = MODES.findIndex((m) => m.id === button.getAttribute("data-mode"));
    const next = button.getAttribute("data-pack");
    if (i >= 0 && i !== ringIndex) {
      ringIndex = i;
      renderRing();
      scrollRingTo(i, true);
    }
    if (!next) {
      shake(button);
      return;
    }
    choosePack(next);
  });
  if (ringEl) {
    ringEl.addEventListener("scroll", onRingScroll, { passive: true });
    ringEl.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const i = Math.max(0, Math.min(MODES.length - 1, ringIndex + (event.key === "ArrowRight" ? 1 : -1)));
      ringIndex = i;
      renderRing();
      scrollRingTo(i, true);
      const target = ringButtons()[i];
      if (target) target.focus();
    });
    ringEl.addEventListener("animationend", (event) => {
      const button = event.target.closest && event.target.closest("button");
      if (button) button.classList.remove("shake");
    });
  }
  document.getElementById("end-call").addEventListener("click", endCall);
  const openers = typeof document.querySelectorAll === "function" ? document.querySelectorAll(".open-settings") : [];
  for (const opener of openers) opener.addEventListener("click", () => openSheet(settingsEl));
  document.getElementById("settings-done").addEventListener("click", closeSheets);
  if (backdropEl) backdropEl.addEventListener("click", closeSheets);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSheets();
  });
  document.getElementById("permission-retry").addEventListener("click", () => {
    permissionEl.classList.add("hidden");
    void startCamera();
  });
  document.getElementById("permission-close").addEventListener("click", () => {
    permissionEl.classList.add("hidden");
  });
  startBtn.addEventListener("click", () => {
    if (cameraOn || video.srcObject) stopCamera();
    else void startCamera();
  });
  powerBtn.addEventListener("click", () => {
    const ok = send({
      v: 2,
      type: "confirm",
      session_id: sessionId,
      what: "power_off",
      value: true,
    });
    if (!ok) {
      showProblem("Not connected.");
      return;
    }
    powerConfirmed = true;
    renderCall();
  });
  document.getElementById("upload").addEventListener("change", (event) => {
    onUpload(event);
  });
  document.getElementById("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = typedEl.value;
    typedEl.value = "";
    const clean = String(text || "").trim();
    if (!clean) return;
    ui.dispatch({ type: "final", text: clean, now: Date.now() });
    renderCall();
    sendUser(clean, "typed");
  });
  micBtn.addEventListener("click", () => {
    onMic();
  });
  if (holdBtn) {
    holdBtn.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      if (typeof holdBtn.setPointerCapture === "function") holdBtn.setPointerCapture(event.pointerId);
      void onHoldDown();
    });
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) holdBtn.addEventListener(name, onHoldUp);
    holdBtn.addEventListener("contextmenu", (event) => event.preventDefault());
  }
  const typingTarget = (el) => el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
  window.addEventListener("keydown", (event) => {
    if (event.code !== "Space" || event.repeat || typingTarget(document.activeElement)) return;
    event.preventDefault();
    void onHoldDown();
  });
  window.addEventListener("keyup", (event) => {
    if (event.code !== "Space" || typingTarget(document.activeElement)) return;
    event.preventDefault();
    onHoldUp();
  });
  if (sensEl) {
    sensEl.addEventListener("input", () => {
      if (voice && typeof voice.setSensitivity === "function") voice.setSensitivity(Number(sensEl.value));
    });
  }
  overlayEl.addEventListener("click", () => {
    onStartTap();
  });
  muteBtn.addEventListener("click", () => {
    ui.dispatch({ type: "mute", muted: !ui.getState().muted });
    applyAudioPrefs();
    renderCall();
  });
  volumeEl.addEventListener("input", () => {
    ui.dispatch({ type: "volume", volume: Number(volumeEl.value) });
    applyAudioPrefs();
  });
  if (voicePick) {
    voicePick.addEventListener("change", onVoicePick);
    void loadVoices();
  }
  document.getElementById("test-voice").addEventListener("click", () => {
    onTestVoice();
  });
  transcriptBtn.addEventListener("click", () => {
    const open = transcriptBtn.getAttribute("aria-expanded") === "true";
    const next = !open;
    transcriptBtn.setAttribute("aria-expanded", next ? "true" : "false");
    transcriptList.classList.toggle("hidden", !next);
    transcriptBtn.textContent = next ? "Hide transcript" : "Transcript";
    if (next) transcriptList.scrollTop = transcriptList.scrollHeight;
  });
  document.getElementById("market-dismiss").addEventListener("click", closeSheets);
  window.addEventListener("resize", () => paint(Date.now()));
  video.addEventListener("loadedmetadata", () => paint(Date.now()));
  if (reducedQuery && typeof reducedQuery.addEventListener === "function") {
    reducedQuery.addEventListener("change", () => paint(Date.now()));
  }

  volumeEl.value = String(ui.getState().volume);
  if (serverHostEl) serverHostEl.textContent = location.host;
  renderRing();
  scrollRingTo(ringIndex, false);
  renderPresence();
  renderCamera();
  drawWave();
  renderCall();
  raf = window.requestAnimationFrame(loop);
  void raf;

  async function rebuildVoice() {
    try {
      const mod = await import("./voice.js");
      if (voice && typeof voice.stopListening === "function") voice.stopListening();
      if (!mod || typeof mod.createVoice !== "function") return null;
      const next = mod.createVoice(voiceOptions());
      return next;
    } catch {
      return null;
    }
  }
}

function safeStorage() {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

if (typeof document !== "undefined") boot();
