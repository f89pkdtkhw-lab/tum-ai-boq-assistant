// Run: node --test web/lib/abschluss.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { abschliessen, lvAusJson } from "./abschluss.ts";

const p = (oz, gp, menge = null, ep = null) => ({ oz, kurztext: oz, langtext: "", menge, einheit: "m²", ep, gp, typ: "normal", titel_pfad: ["T"] });
const lv = (positionen) => ({ name: "LV", quelle: "s", positionen, summen: {} });

test("estimate and final bill are matched by OZ and marked by the 10 % tolerance", () => {
  const a = abschliessen(lv([p("1", 1000), p("2", 500), p("3", null, 10, 20), p("4", 80)]), lv([p("1", 1050), p("2", 700), p("3", 200), p("5", 10)]));
  assert.deepEqual(a.estimated_values.map((m) => [m.oz, m.value]), [["1", 1000], ["2", 500], ["3", 200], ["4", 80]]);
  assert.deepEqual(a.real_values.map((m) => [m.oz, m.value]), [["1", 1050], ["2", 700], ["3", 200]]);
  assert.deepEqual(a.marks.map((m) => [m.oz, m.status]), [["1", "confirmed"], ["2", "deviation"], ["3", "confirmed"]]);
  assert.equal(a.marks[1].what_happened, "Real price +40 % vs. estimate");
  assert.deepEqual(a.nurGeschaetzt, ["4"]);
  assert.deepEqual(a.nurReal, ["5"]);
});

test("a report JSON or a plain BoQ JSON is accepted, anything else is not", () => {
  assert.equal(lvAusJson({ lv: lv([p("1", 1)]), findings: [] }).name, "LV");
  assert.equal(lvAusJson(lv([])).name, "LV");
  assert.equal(lvAusJson({ foo: 1 }), null);
});
