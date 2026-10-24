// Rewind: the call-memory switch and the answer card. Video clips go to TwelveLabs only while the switch is on.
export const NOTICE = "When on, short video clips of this call are uploaded to TwelveLabs so you can ask about them later.";

export function fmtCallTime(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function hitCaption(hit) {
  const when = `${fmtCallTime(hit.t_s)} into the call`;
  if (hit.sure) return when;
  const others = (hit.alternatives || []).map(fmtCallTime);
  return `Best guess: ${when}${others.length ? `, or ${others.join(", ")}` : ""}`;
}

export function boxStyle(bbox) {
  const [x, y, w, h] = bbox.map((v) => Math.min(1, Math.max(0, Number(v) || 0)) * 100);
  return { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` };
}

// Build the card: the kept frame with boxes on it (not on the live picture), and the call time.
export function renderHit(doc, body, hit) {
  body.replaceChildren();
  if (hit.frame_b64) {
    const figure = doc.createElement("div");
    figure.className = "rewind-frame";
    const img = doc.createElement("img");
    img.alt = `Frame at ${fmtCallTime(hit.t_s)}`;
    img.src = `data:image/jpeg;base64,${hit.frame_b64}`;
    figure.append(img);
    for (const obj of hit.objects || []) {
      const box = doc.createElement("span");
      box.className = "rewind-box";
      Object.assign(box.style, boxStyle(obj.bbox));
      box.textContent = String(obj.label || "");
      figure.append(box);
    }
    body.append(figure);
  }
  const line = doc.createElement("p");
  line.className = "rewind-when";
  line.textContent = hitCaption(hit);
  body.append(line);
}
