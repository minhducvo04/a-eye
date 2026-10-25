// Live changes transport settings only when explicitly selected; Google consent stays separate.
export function liveSettings(mode, google, privateMode) {
  return {
    selected: mode === 'gemini-live',
    allowed: mode === 'gemini-live' && Boolean(google) && !privateMode,
    notice: 'During a Gemini Live call, your microphone audio and downscaled camera video go to Google. Memory stays local; only requested tool result text goes to Google.',
  };
}
