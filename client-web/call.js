// Safari call page. Speaks the v1 WebSocket contract. Frames stay in memory only
// for the JPEG we are about to send; nothing is written to storage or disk.

import { drawOverlay } from "./overlay.js";

const BOARD_ID = "demo-b650";
const MAX_FRAME_WIDTH = 640;
const FRAME_INTERVAL_MS = 1000;

const video = document.getElementById("camera");
const canvas = document.getElementById("overlay");
const statusDot = document.getElementById("status");
const stepState = document.getElementById("step-state");
const stepItem = document.getElementById("step-item");
const stepHeader = document.getElementById("step-header");
const captionEl = document.getElementById("caption");
const verdictEl = document.getElementById("verdict");

const sessionId = randomId();
let socket = null;
let seq = 0;
let frameTimer = 0;
let lastDrawnSeq = -1;
let latestOverlay = null;
let cameraOn = false;

function randomId() {
  if (globalThis.crypto && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function wsUrl() {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws`;
}

export function speak(text) {
  const synth = globalThis.speechSynthesis;
  if (!text || !synth || typeof SpeechSynthesisUtterance !== "function") return;
  const utter = new SpeechSynthesisUtterance(text);
  synth.cancel();
  synth.speak(utter);
}

function setStatus(on) {
  statusDot.classList.toggle("on", on);
  statusDot.classList.toggle("off", !on);
  statusDot.setAttribute("aria-label", on ? "socket connected" : "socket disconnected");
}

function setCaption(text, isError) {
  captionEl.textContent = text || "";
  captionEl.classList.toggle("bad", Boolean(isError));
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

function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  socket = new WebSocket(wsUrl());
  socket.addEventListener("open", () => {
    setStatus(true);
    send({
      v: 1,
      type: "hello",
      session_id: sessionId,
      board_id: BOARD_ID,
      mode: "live",
      client: "web",
    });
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
    window.setTimeout(connect, 2000);
  });
  socket.addEventListener("error", () => {
    setStatus(false);
  });
}

function onServer(message) {
  if (!message || typeof message !== "object") return;
  if (message.type === "overlay") {
    if (typeof message.seq === "number" && message.seq < lastDrawnSeq) return;
    if (typeof message.seq === "number") lastDrawnSeq = message.seq;
    latestOverlay = message;
    paint();
    return;
  }
  if (message.type === "say") {
    setCaption(message.text, false);
    speak(message.text);
    return;
  }
  if (message.type === "step") {
    stepState.textContent = message.state || "—";
    stepItem.textContent = message.item ? String(message.item).replaceAll("_", " ") : "—";
    stepHeader.textContent = message.target_header || "—";
    return;
  }
  if (message.type === "verdict") {
    showVerdict(message);
    return;
  }
  if (message.type === "error") {
    setCaption(message.message || "Something went wrong.", true);
  }
}

function showVerdict(message) {
  verdictEl.classList.remove("hidden", "pass", "fail", "abstain");
  if (message.abstain) {
    verdictEl.textContent = "Can't tell";
    verdictEl.classList.add("abstain");
    return;
  }
  const pct = Math.round(Number(message.conf) * 100);
  const reason = message.reason ? `${message.reason} ` : "";
  if (message.pass) {
    verdictEl.textContent = `${reason}${pct}%`;
    verdictEl.classList.add("pass");
  } else {
    verdictEl.textContent = `${reason}${pct}%`;
    verdictEl.classList.add("fail");
  }
}

function contentRect() {
  const elementW = video.clientWidth || canvas.clientWidth;
  const elementH = video.clientHeight || canvas.clientHeight;
  const frameW = video.videoWidth;
  const frameH = video.videoHeight;
  if (!frameW || !frameH || !elementW || !elementH) {
    return { x: 0, y: 0, w: elementW, h: elementH };
  }
  const scale = Math.min(elementW / frameW, elementH / frameH);
  const w = frameW * scale;
  const h = frameH * scale;
  return {
    x: (elementW - w) / 2,
    y: (elementH - h) / 2,
    w,
    h,
  };
}

function paint() {
  const cssW = video.clientWidth || canvas.clientWidth;
  const cssH = video.clientHeight || canvas.clientHeight;
  if (!cssW || !cssH) return;
  const dpr = window.devicePixelRatio || 1;
  const bitmapW = Math.round(cssW * dpr);
  const bitmapH = Math.round(cssH * dpr);
  if (canvas.width !== bitmapW || canvas.height !== bitmapH) {
    canvas.width = bitmapW;
    canvas.height = bitmapH;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  if (!latestOverlay) return;
  const rect = contentRect();
  if (!rect.w || !rect.h) return;
  ctx.save();
  ctx.translate(rect.x, rect.y);
  drawOverlay(ctx, latestOverlay, rect.w, rect.h);
  ctx.restore();
}

function rasterize(source, srcW, srcH) {
  const scale = srcW > MAX_FRAME_WIDTH ? MAX_FRAME_WIDTH / srcW : 1;
  const w = Math.max(1, Math.round(srcW * scale));
  const h = Math.max(1, Math.round(srcH * scale));
  const offscreen = document.createElement("canvas");
  offscreen.width = w;
  offscreen.height = h;
  const ctx = offscreen.getContext("2d");
  ctx.drawImage(source, 0, 0, w, h);
  const dataUrl = offscreen.toDataURL("image/jpeg", 0.7);
  const comma = dataUrl.indexOf(",");
  return { w, h, jpeg_b64: dataUrl.slice(comma + 1) };
}

function sendFrame() {
  if (!cameraOn || !video.videoWidth || !video.videoHeight) return;
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  const shot = rasterize(video, video.videoWidth, video.videoHeight);
  send({
    v: 1,
    type: "frame",
    session_id: sessionId,
    seq: nextSeq(),
    ts_ms: Date.now(),
    w: shot.w,
    h: shot.h,
    jpeg_b64: shot.jpeg_b64,
  });
}

function sendPhoto(shot) {
  const ok = send({
    v: 1,
    type: "photo",
    session_id: sessionId,
    seq: nextSeq(),
    w: shot.w,
    h: shot.h,
    jpeg_b64: shot.jpeg_b64,
  });
  if (!ok) setCaption("Not connected.", true);
}

function confirm(what) {
  const ok = send({
    v: 1,
    type: "confirm",
    session_id: sessionId,
    what,
    value: true,
  });
  if (!ok) setCaption("Not connected.", true);
}

async function startCamera() {
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
    setCaption("No camera. Use Upload photo.", false);
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    video.srcObject = stream;
    await video.play();
    cameraOn = true;
    sendFrame();
    frameTimer = window.setInterval(sendFrame, FRAME_INTERVAL_MS);
  } catch {
    cameraOn = false;
    setCaption("Camera unavailable. Use Upload photo.", false);
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
    sendPhoto(rasterize(image, image.naturalWidth, image.naturalHeight));
  } catch {
    setCaption("Could not read that photo.", true);
  } finally {
    URL.revokeObjectURL(url);
  }
}

document.getElementById("power-off").addEventListener("click", () => confirm("power_off"));
document.getElementById("check-again").addEventListener("click", () => confirm("check_again"));
document.getElementById("send-photo").addEventListener("click", () => {
  if (!video.videoWidth) {
    setCaption("No camera frame. Use Upload photo.", true);
    return;
  }
  sendPhoto(rasterize(video, video.videoWidth, video.videoHeight));
});
document.getElementById("upload").addEventListener("change", (event) => {
  onUpload(event);
});

window.addEventListener("resize", paint);
video.addEventListener("loadedmetadata", paint);
connect();
startCamera();
paint();
