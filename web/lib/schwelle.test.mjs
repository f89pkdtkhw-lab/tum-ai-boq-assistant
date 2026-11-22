// Run: node --test web/lib/schwelle.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { liegtUeberSchwelle, SCHWELLE_STUFEN, sliderFarbe } from "./schwelle.ts";

test("threshold keeps findings at or above the chosen severity", () => {
  assert.equal(liegtUeberSchwelle("niedrig", "niedrig"), true);
  assert.equal(liegtUeberSchwelle("mittel", "niedrig"), true);
  assert.equal(liegtUeberSchwelle("niedrig", "mittel"), false);
  assert.equal(liegtUeberSchwelle("hoch", "mittel"), true);
  assert.equal(liegtUeberSchwelle("mittel", "hoch"), false);
  assert.equal(liegtUeberSchwelle("kritisch", "hoch"), true);
  assert.equal(liegtUeberSchwelle("hoch", "kritisch"), false);
  assert.equal(liegtUeberSchwelle("kritisch", "kritisch"), true);
});

test("slider stops run from lenient to strict", () => {
  assert.deepEqual(SCHWELLE_STUFEN, ["niedrig", "mittel", "hoch", "kritisch"]);
});

test("slider colour runs from green to red", () => {
  assert.equal(sliderFarbe(0), "rgb(52, 199, 89)");
  assert.equal(sliderFarbe(1), "rgb(255, 59, 48)");
  assert.equal(sliderFarbe(-1), "rgb(52, 199, 89)");
  assert.equal(sliderFarbe(2), "rgb(255, 59, 48)");
  const mid = sliderFarbe(0.5);
  assert.match(mid, /^rgb\(\d+, \d+, \d+\)$/);
  assert.notEqual(mid, sliderFarbe(0));
  assert.notEqual(mid, sliderFarbe(1));
});
