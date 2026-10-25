// Safari can disguise its platform as macOS. The explicit URL flag is the reliable entry point.
export function isHeadset(search = '', userAgent = '') {
  return new URLSearchParams(search).get('device') === 'headset' || /visionOS|Vision Pro/i.test(userAgent);
}

// Enforce the camera boundary at every local video acquisition, including Settings permissions.
export async function requestLocalMedia(mediaDevices, headset, constraints) {
  if (headset && constraints.video) throw new Error('Use your phone camera on Vision Pro.');
  return mediaDevices.getUserMedia(constraints);
}

// Persistent instruction card for the Vision Pro window. Valve status wins; otherwise the last helper line.
export function headsetStep(pack, { valve, caption } = {}) {
  const home = pack === 'home';
  const eyebrow = home ? 'SINK' : 'GENERAL';
  const line = String((home && valve) || caption || '').trim();
  if (line) return { eyebrow, line };
  return {
    eyebrow,
    line: home ? 'Show the sink. Say next when you are ready.' : 'Ask what you are looking at.',
  };
}
