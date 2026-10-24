// Pure overlay drawing. No DOM access at import time (Node tests import this file).
// Coordinates in messages are normalized 0..1 of the frame that was sent.
// drawOverlay maps them onto the displayed video size (width x height, pixels).

const ROLE_COLOR = {
  target: "#3DDC97",
  other: "#8B909A",
  wrong: "#FF4B4B",
  ok: "#4C9AFF",
};

export function roleColor(role) {
  return ROLE_COLOR[role] || ROLE_COLOR.other;
}

// bbox is [x, y, w, h]. Values outside the frame are clamped so the rect stays inside.
export function toPixels(bbox, width, height) {
  let x = Number(bbox[0]) * width;
  let y = Number(bbox[1]) * height;
  let w = Number(bbox[2]) * width;
  let h = Number(bbox[3]) * height;
  if (w < 0) {
    x += w;
    w = -w;
  }
  if (h < 0) {
    y += h;
    h = -h;
  }
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }
  if (x > width) x = width;
  if (y > height) y = height;
  if (w < 0) w = 0;
  if (h < 0) h = 0;
  if (x + w > width) w = Math.max(0, width - x);
  if (y + h > height) h = Math.max(0, height - y);
  return { x, y, w, h };
}

function boxCaption(box) {
  const name = box.label || box.header || box.id || "";
  const pct = Math.round(Number(box.conf) * 100);
  return name ? `${name} ${pct}%` : `${pct}%`;
}

function drawArrow(ctx, arrow, width, height) {
  const x1 = arrow.from[0] * width;
  const y1 = arrow.from[1] * height;
  const x2 = arrow.to[0] * width;
  const y2 = arrow.to[1] * height;
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const head = Math.max(10, Math.min(width, height) * 0.04);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(
    x2 - head * Math.cos(angle - Math.PI / 6),
    y2 - head * Math.sin(angle - Math.PI / 6),
  );
  ctx.lineTo(
    x2 - head * Math.cos(angle + Math.PI / 6),
    y2 - head * Math.sin(angle + Math.PI / 6),
  );
  ctx.closePath();
  ctx.fill();
}

export function drawOverlay(ctx, overlay, width, height) {
  ctx.clearRect(0, 0, width, height);
  if (!overlay) return;
  const boxes = overlay.boxes || [];
  ctx.lineWidth = Math.max(2, Math.round(Math.min(width, height) / 160));
  ctx.font = `${Math.max(14, Math.round(height * 0.045))}px sans-serif`;
  ctx.textBaseline = "bottom";
  for (const box of boxes) {
    const rect = toPixels(box.bbox, width, height);
    const color = roleColor(box.role);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    ctx.fillText(boxCaption(box), rect.x, Math.max(14, rect.y - 2));
    if (overlay.level === "pin" && box.pins) {
      for (const pin of box.pins) {
        ctx.beginPath();
        ctx.fillStyle = roleColor(pin.role);
        ctx.arc(pin.x * width, pin.y * height, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  if (overlay.arrow && overlay.arrow.from && overlay.arrow.to) {
    ctx.strokeStyle = roleColor("target");
    ctx.fillStyle = roleColor("target");
    drawArrow(ctx, overlay.arrow, width, height);
  }
}
