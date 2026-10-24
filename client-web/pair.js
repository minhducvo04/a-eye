import { drawQr } from './qr.js';
import { writeFrame } from './live.js';

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
  if (message.state === 'joined') return camera ? 'Paired' : 'Phone camera connected';
  if (message.state === 'camera') return message.camera_on ? 'Phone camera on' : 'Phone camera off';
  if (message.state === 'left') return camera ? 'Call ended. Request a new code to reconnect.' : 'Phone disconnected; using this device’s camera.';
  return message.detail || 'Unable to pair. Request a new code.';
}

export function setupPairCall(send, sessionId) {
  const button = document.getElementById('pair-request');
  const status = document.getElementById('pair-status');
  button?.addEventListener('click', () => {
    if (!send({ v: 2, type: 'pair_request', session_id: sessionId })) status.textContent = 'Start a call first.';
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

// An isolated entry point: never initializes call UI, speech, mic or pack selection.
export function bootPairCamera() {
  const mode = pairMode(location.search);
  if (!mode.camera) return false;
  document.body.replaceChildren();
  const video = document.createElement('video');
  video.autoplay = video.muted = video.playsInline = true;
  video.style.cssText = 'width:100%;max-height:70vh;object-fit:contain';
  const button = document.createElement('button');
  button.textContent = 'Start camera'; button.style.cssText = 'padding:24px;font-size:24px';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  status.textContent = 'Start camera to pair with your call.';
  document.body.append(video, button, status);
  const sessionId = globalThis.crypto.randomUUID(), grab = document.createElement('canvas');
  let socket, stream, timer, seq = 0, paired = false, terminal = false;
  const send = msg => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ v: 2, session_id: sessionId, ...msg })); };
  function stop() {
    clearInterval(timer);
    stream?.getTracks().forEach(track => track.stop()); stream = null; video.srcObject = null;
    button.textContent = 'Start camera';
  }
  button.addEventListener('click', async () => {
    if (stream) { send({ type: 'camera', on: false }); stop(); return; }
    button.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      video.srcObject = stream; await video.play(); button.textContent = 'Stop camera';
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
        socket.addEventListener('close', () => {
          if (!terminal) status.textContent = 'Disconnected. Request a new code to reconnect.';
          terminal = true; paired = false; stop(); button.disabled = true;
        });
      } else send({ type: 'camera', on: true });
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
