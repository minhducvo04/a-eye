// Any device with two or more cameras gets the button: phones, tablets, and desktops with an extra webcam.
export function showFlipCamera(nav, coarse, devices) {
  return devices.filter(d => d.kind === "videoinput").length >= 2;
}

export async function switchVideoTrack(stream, facingMode, getUserMedia, active = () => true) {
  // Mobile Safari may require releasing the old camera before opening the other one.
  for (const track of stream.getVideoTracks()) {
    track.stop();
    stream.removeTrack(track);
  }
  const next = await getUserMedia({
    video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
  });
  if (!active()) {
    for (const track of next.getVideoTracks()) track.stop();
    return false;
  }
  for (const track of next.getVideoTracks()) stream.addTrack(track);
  return true;
}

export function wireFlipCamera({ video, button, active, busy, onError, onSwitch = () => {} }) {
  let facing = "environment";
  let switching = false;
  try { if (localStorage.getItem("aeye.facingMode") === "user") facing = "user"; } catch {}
  function preview() {
    // Mirror the preview only (frames sent to the server are never mirrored). Desktop webcams rarely report a
    // facingMode, so an unreported one is treated as the back camera and left unmirrored.
    const actual = video.srcObject?.getVideoTracks?.()[0]?.getSettings?.().facingMode;
    video.style.transform = (actual || "environment") === "user" ? "scaleX(-1)" : "";
    button.disabled = !active() || switching;
  }
  async function refresh() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      button.hidden = !showFlipCamera(navigator, window.matchMedia("(pointer: coarse)").matches, devices);
    } catch { button.hidden = true; }
    preview();
  }
  button.addEventListener("click", async () => {
    if (switching || busy() || !active()) return;
    switching = true;
    button.disabled = true;
    const stream = video.srcObject;
    const next = facing === "environment" ? "user" : "environment";
    const stillActive = () => active() && video.srcObject === stream;
    try {
      if (await switchVideoTrack(stream, next, c => navigator.mediaDevices.getUserMedia(c), stillActive)) {
        facing = next;
        try { localStorage.setItem("aeye.facingMode", facing); } catch {}
        onSwitch();
      }
    } catch {
      // Restore the previous camera after a denied/unavailable switch.
      if (stillActive()) {
        try { await switchVideoTrack(stream, facing, c => navigator.mediaDevices.getUserMedia(c), stillActive); } catch {}
        onError("Could not switch the camera.");
      }
    } finally {
      switching = false;
      preview();
    }
  });
  video.addEventListener("loadedmetadata", refresh);
  navigator.mediaDevices?.addEventListener?.("devicechange", refresh);
  void refresh();
  return {
    constraints: base => (base.deviceId ? base : { width: base.width, height: base.height, facingMode: facing }),
    refresh,
    preview,
    busy: () => switching,
  };
}
