import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { drawOverlay, roleColor, toPixels } from "./overlay.js";

const examplesPath = join(dirname(fileURLToPath(import.meta.url)), "..", "contracts", "examples.json");
const examples = JSON.parse(readFileSync(examplesPath, "utf8"));
const [headerOverlay, pinOverlay] = examples.overlay;

function fakeCtx() {
  const calls = [];
  const ctx = new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === "calls") return calls;
        if (typeof prop !== "string") return undefined;
        return (...args) => {
          calls.push([prop, ...args]);
        };
      },
      set(_target, prop, value) {
        calls.push(["set", prop, value]);
        return true;
      },
    },
  );
  return ctx;
}

function methods(ctx, name) {
  return ctx.calls.filter((call) => call[0] === name);
}

test("toPixels scales normalized bbox onto the frame", () => {
  const bbox = headerOverlay.boxes[0].bbox;
  const rect = toPixels(bbox, 640, 480);
  assert.deepEqual(rect, {
    x: bbox[0] * 640,
    y: bbox[1] * 480,
    w: bbox[2] * 640,
    h: bbox[3] * 480,
  });
  assert.equal(rect.x, 256);
  assert.equal(rect.y, 264);
  assert.deepEqual(toPixels([0.25, 0.5, 0.5, 0.25], 200, 100), {
    x: 50,
    y: 50,
    w: 100,
    h: 25,
  });
});

test("toPixels clamps boxes that start outside or run past the frame", () => {
  assert.deepEqual(toPixels([0.8, -0.2, 0.5, 0.5], 100, 100), {
    x: 80,
    y: 0,
    w: 20,
    h: 30,
  });
  assert.deepEqual(toPixels([-0.5, 0.5, 0.25, 2], 100, 50), {
    x: 0,
    y: 25,
    w: 0,
    h: 25,
  });
});

test("roleColor covers target, other, wrong and ok", () => {
  assert.equal(roleColor("target"), "#3DDC97");
  assert.equal(roleColor("other"), "#8B909A");
  assert.equal(roleColor("wrong"), "#FF4B4B");
  assert.equal(roleColor("ok"), "#4C9AFF");
});

test("drawOverlay strokes each example box, draws the arrow, and dots only pin level", () => {
  const width = 200;
  const height = 100;
  const headerCtx = fakeCtx();
  drawOverlay(headerCtx, headerOverlay, width, height);
  const headerRects = methods(headerCtx, "strokeRect");
  assert.equal(headerRects.length, headerOverlay.boxes.length);
  assert.deepEqual(headerRects[0].slice(1), Object.values(toPixels(headerOverlay.boxes[0].bbox, width, height)));
  assert.equal(methods(headerCtx, "arc").length, 0);
  assert.ok(methods(headerCtx, "stroke").length >= 1);
  const [tx, ty] = headerOverlay.arrow.to;
  const arrowTip = methods(headerCtx, "lineTo").some(
    (call) => Math.abs(call[1] - tx * width) < 1e-9 && Math.abs(call[2] - ty * height) < 1e-9,
  );
  assert.equal(arrowTip, true);
  const labels = methods(headerCtx, "fillText").map((call) => call[1]);
  assert.ok(labels.some((text) => text.includes("CPU_FAN") && text.includes("86%")));
  assert.ok(labels.some((text) => text.includes("SYS_FAN1") && text.includes("74%")));

  const pinCtx = fakeCtx();
  drawOverlay(pinCtx, pinOverlay, width, height);
  assert.equal(methods(pinCtx, "strokeRect").length, pinOverlay.boxes.length);
  const pinCount = pinOverlay.boxes.reduce((sum, box) => sum + (box.pins ? box.pins.length : 0), 0);
  assert.equal(methods(pinCtx, "arc").length, pinCount);
  assert.equal(methods(pinCtx, "stroke").length, 0);

  const headerWithPins = {
    ...pinOverlay,
    level: "header",
    arrow: undefined,
  };
  const gated = fakeCtx();
  drawOverlay(gated, headerWithPins, width, height);
  assert.equal(methods(gated, "arc").length, 0);
  assert.equal(methods(gated, "strokeRect").length, 1);
});
