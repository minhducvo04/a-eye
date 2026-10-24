import test from "node:test";
import assert from "node:assert/strict";
import { boxStyle, fmtCallTime, hitCaption } from "./rewind.js";

test("call time and caption", () => {
  assert.equal(fmtCallTime(130.4), "2:10");
  assert.equal(fmtCallTime(-3), "0:00");
  assert.equal(hitCaption({ t_s: 130, sure: true }), "2:10 into the call");
  assert.equal(hitCaption({ t_s: 130, sure: false, alternatives: [402] }), "Best guess: 2:10 into the call, or 6:42");
});

test("box style is clamped percent of the frame", () => {
  assert.deepEqual(boxStyle([0.4, 0.3, 0.2, 1.4]), { left: "40%", top: "30%", width: "20%", height: "100%" });
});
