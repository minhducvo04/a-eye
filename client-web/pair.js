import { drawQr } from './qr.js';
import { writeFrame } from './live.js';
import { createVoice } from './voice.js';

export function pairMode(search) {
  const query = new URLSearchParams(search);
  return { camera: query.has('pair'), code: query.get('pair') || '', token: query.get('token') || '' };
}
export function pairUrl(origin, path, search) {
  const url = new URL(path, origin);
  const token = pairMode(search).token;
  if (token) url.searchParams.set('token', token);
  return url.href;
}
export function pairStatus(message, camera = false) {
  if (message.state === 'joined') return camera ? 'Camera + mic connected' : 'Phone camera + mic connected';
  if (message.state === 'camera') return message.camera_on ? 'Phone camera on' : 'Phone camera off';
  if (message.state === 'left') return camera ? 'Call ended. Request a new code to reconnect.' : 'Phone disconnected; using this device’s camera.';
  return message.detail || 'Unable to pair. Request a new code.';
}

// The laptop's mic while a phone is paired: the phone's mic replaces it, and leaving restores it.
// route is { phone, resume }; returns the next route and what to do with the local mic.
export function phoneMicRoute(route, message, localMicOn) {
  const r = route || { phone: false, resume: false };
  if (!message || message.type !== 'pair_status' || message.role !== 'call') return { route: r, action: null };
  if (message.state === 'joined' && !r.phone) {
    return { route: { phone: true, resume: Boolean(localMicOn) }, action: localMicOn ? 'stop_local' : null };
  }
  if (message.state === 'left' && r.phone) {
    return { route: { phone: false, resume: false }, action: r.resume ? 'start_local' : null };
  }
  return { route: r, action: null };
}

// Phone side: utterance chunks go out as audio_in. barge_in goes first, at voice.js's barge point (400 ms of
// speech, 700 ms in a loud room); chunks wait for it so the server's barge_in reset never drops this
// utterance's start. An utterance that ends before its barge point is sent without one.
export function createPhoneAudio(send) {
  let held = [];
  let barged = false;
  const out = (seq, pcm16_b64, final) => send({ type: 'audio_in', seq, sample_rate: 16000, pcm16_b64, final });
  return {
    chunk(pcm16_b64, seq, final) {
      if (barged) out(seq, pcm16_b64, final);
      else held.push([seq, pcm16_b64, final]);
      if (final) {
        for (const item of held) out(...item);
        held = [];
        barged = false;
      }
    },
    bargePoint() {
      if (barged) return;
      barged = true;
      send({ type: 'barge_in', utterance_id: 'phone', at_ms: 0 });
      for (const item of held) out(...item);
      held = [];
    },
  };
}

export function setupPairCall(send, sessionId) {
  const button = document.getElementById('pair-request');
  const status = document.getElementById('pair-status');
  button?.addEventListener('click', () => {
    const id = typeof sessionId === 'function' ? sessionId() : sessionId;
    if (!send({ v: 2, type: 'pair_request', session_id: id })) status.textContent = 'Start a call first.';
  });
  return message => {
    if (message.type === 'pair_status') status.textContent = pairStatus(message);
    if (message.type !== 'pair') return;
    const url = pairUrl(location.origin, message.path, location.search);
    status.textContent = `Code ${message.code} · expires in ${message.expires_in_s} seconds`;
    const link = document.getElementById('pair-link');
    link.href = url; link.textContent = url;
    const canvas = document.getElementById('pair-qr');
    canvas.hidden = false;
    try { drawQr(canvas, url); } catch (error) { canvas.hidden = true; status.textContent += ` · ${error.message}`; }
  };
}

// An isolated entry point: never initializes call UI or pack selection. One tap starts the camera and the mic;
// the mic runs voice.js's VAD and sends utterances for server speech recognition. The phone never plays audio.
export function bootPairCamera({ makeVoice = createVoice } = {}) {
  const mode = pairMode(location.search);
  if (!mode.camera) return false;
  document.body.replaceChildren();
  document.body.style.cssText = 'margin:0;background:#000;color:#fff;font:17px -apple-system,system-ui,sans-serif;text-align:center';
  const video = document.createElement('video');
  video.autoplay = video.muted = video.playsInline = true;
  video.style.cssText = 'width:100%;max-height:60vh;object-fit:contain;background:#111';
  const button = document.createElement('button');
  button.textContent = 'Start'; button.style.cssText = 'margin:16px;padding:20px 48px;font-size:24px;border-radius:16px;border:0;background:#8EB6FF;color:#000';
  const meter = document.createElement('div');
  meter.setAttribute('role', 'meter'); meter.setAttribute('aria-label', 'Microphone level');
  meter.setAttribute('aria-valuemin', '0'); meter.setAttribute('aria-valuemax', '100');
  meter.style.cssText = 'margin:8px 16px;height:28px;border-radius:14px;background:rgba(255,255,255,0.15);overflow:hidden';
  const fill = document.createElement('div');
  fill.id = 'phone-level';
  fill.style.cssText = 'height:100%;width:0;background:#8EB6FF;transition:width 60ms linear';
  meter.append(fill);
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.id = 'phone-status';
  status.style.cssText = 'margin:12px 16px;font-size:20px';
  status.textContent = 'Tap Start to use this phone as the camera and mic.';
  document.body.append(video, button, meter, status);
  const sessionId = globalThis.crypto.randomUUID(), grab = document.createElement('canvas');
  let socket, stream, timer, voice, seq = 0, paired = false, terminal = false, signIn = false;
  const send = msg => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ v: 2, session_id: sessionId, ...msg })); };
  const audio = createPhoneAudio(msg => { if (paired) send(msg); });
  function showLevel(level) {
    const pct = Math.round(Math.max(0, Math.min(1, Number(level) || 0)) * 100);
    fill.style.width = `${pct}%`;
    meter.setAttribute('aria-valuenow', String(pct));
  }
  function stop() {
    clearInterval(timer);
    stream?.getTracks().forEach(track => track.stop()); stream = null; video.srcObject = null;
    voice?.stopListening(); showLevel(0);
    button.textContent = 'Start';
  }
  function ensureVoice() {
    voice = voice || makeVoice({
      sttMode: 'server',
      synth: null,
      onAudioChunk: (pcm16, _seq, final) => audio.chunk(pcm16, _seq, final),
      onBargePoint: () => audio.bargePoint(),
      onLevel: showLevel,
      onMicError: () => { status.textContent = 'Mic unavailable. Camera only.'; },
    });
    return voice;
  }
  async function startMic() {
    if (ensureVoice().supported.stt) await voice.startListening();
  }
  button.addEventListener('click', async () => {
    if (signIn) { location.reload(); return; }
    if (stream) { send({ type: 'camera', on: false }); stop(); return; }
    // Inside the tap, before any await: iOS Safari only starts audio capture from a user gesture.
    void ensureVoice().unlockAudio?.();
    button.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      video.srcObject = stream; await video.play(); button.textContent = 'Stop';
      if (!socket) {
        const url = new URL('/ws2', location.href); url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        if (mode.token) url.searchParams.set('token', mode.token);
        socket = new WebSocket(url);
        socket.addEventListener('open', () => send({ type: 'hello', pack: 'general', role: 'camera', pair_code: mode.code, camera: true }));
        socket.addEventListener('message', event => {
          const msg = JSON.parse(event.data);
          if (msg.type === 'pair_status') {
            status.textContent = pairStatus(msg, true);
            paired = msg.state === 'joined' || (paired && msg.state === 'camera');
            if (['left', 'rejected', 'expired'].includes(msg.state)) { terminal = true; stop(); button.disabled = true; }
          } else if (msg.type === 'error') status.textContent = msg.message;
        });
        socket.addEventListener('close', event => {
          if (!terminal) status.textContent = 'Disconnected. Request a new code to reconnect.';
          terminal = true; paired = false; stop(); button.disabled = true;
          if (event?.code === 4401) {
            signIn = true; status.textContent = 'Please sign in again';
            button.textContent = 'Reload to sign in'; button.disabled = false;
          }
        });
      } else send({ type: 'camera', on: true });
      await startMic();
      timer = setInterval(() => {
        if (!paired || !stream || document.hidden || socket.bufferedAmount || !video.videoWidth) return;
        const shot = writeFrame(grab, video, video.videoWidth, video.videoHeight);
        if (shot) send({ type: 'frame', seq: ++seq, ts_ms: Date.now(), ...shot });
      }, 1000);
    } catch { stop(); status.textContent = 'Camera unavailable. Allow camera access and use HTTPS, then try again.'; }
    finally { button.disabled = terminal; }
  });
  window.addEventListener('pagehide', () => { stop(); socket?.close(); });
  return true;
}
