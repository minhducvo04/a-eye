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

function fakeDoc() {
  const make = (tag) => ({
    tag, children: [], className: "", textContent: "",
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren() { this.children = []; },
  });
  return { createElement: make, createTextNode: (text) => ({ tag: "#text", textContent: text }) };
}

test("recap renders ordered steps and the skipped line", async () => {
  const { renderRecap } = await import("./rewind.js");
  const doc = fakeDoc();
  const body = doc.createElement("div");
  renderRecap(doc, body, { steps: [{ t_s: 42, text: "Installed the CPU" }], skipped: ["install the RAM"] });
  const [list, skipped] = body.children;
  assert.equal(list.tag, "ol");
  assert.equal(list.children[0].children[0].textContent, "0:42");
  assert.equal(list.children[0].children[1].textContent, " Installed the CPU");
  assert.equal(skipped.textContent, "Maybe skipped: install the RAM");
  renderRecap(doc, body, { pending: true });
  assert.match(body.children[0].textContent, /Making your recap/);
});

test("recap request carries the page token", async () => {
  const { fetchRecap } = await import("./rewind.js");
  const seen = [];
  globalThis.fetch = async (url, init) => { seen.push([url, init]); return { ok: true, json: async () => ({ steps: [] }) }; };
  await fetchRecap("s1", "?token=abc");
  assert.equal(seen[0][0], "/api/rewind/recap");
  assert.equal(seen[0][1].headers.Authorization, "Bearer abc");
  assert.equal(JSON.parse(seen[0][1].body).session_id, "s1");
});
