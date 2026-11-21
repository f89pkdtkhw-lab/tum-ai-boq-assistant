// Run: node --test web/lib/top.test.mjs  (Node >= 23 strips the TypeScript types of top.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { topPositionen } from "./top.ts";

const p = (oz, kurztext = `Item ${oz}`) =>
  ({ oz, kurztext, langtext: "", menge: 1, einheit: "m", ep: null, gp: null, typ: "normal", titel_pfad: [] });
let n = 0;
const f = (oz, schwere = "mittel", euro_wirkung = null, quelle = "regel") =>
  ({ id: `f${n++}`, oz, kategorie: "fehler", schwere, titel: "", begruendung: "", vorschlag: "", quelle, regel_id: quelle === "regel" ? "R" : "MOCK_LLM", euro_wirkung });
const oz = (zeilen) => zeilen.map((z) => z.oz);

test("highest severity of a position ranks first", () => {
  const top = topPositionen([f("1", "niedrig"), f("2", "hoch"), f("3", "niedrig"), f("3", "kritisch")], [], 10);
  assert.deepEqual(oz(top), ["3", "2", "1"]);
  assert.equal(top[0].schwere, "kritisch");
  assert.equal(top[0].anzahl, 2);
});

test("known euro ranks by size, unknown after known, never as 0", () => {
  const top = topPositionen([f("a", "hoch", null), f("b", "hoch", 0), f("c", "hoch", 500), f("c", "hoch", 200), f("d", "hoch", 900)], [], 10);
  assert.deepEqual(oz(top), ["d", "c", "b", "a"]);
  assert.equal(top[1].euro, 700);
  assert.equal(top[2].euro, 0);
  assert.equal(top[3].euro, null);
});

test("model findings do not contribute euro; model-only flag", () => {
  const top = topPositionen([f("m", "hoch", 1000, "modell"), f("r", "hoch", null), f("r", "niedrig", null, "modell")], [p("m"), p("r")], 10);
  const m = top.find((z) => z.oz === "m");
  assert.equal(m.euro, null);
  assert.equal(m.nurModell, true);
  assert.equal(top.find((z) => z.oz === "r").nurModell, false);
});

test("then finding count, then OZ in natural order", () => {
  const top = topPositionen([f("01.10"), f("01.9"), f("01.2"), f("01.2")], [], 10);
  assert.deepEqual(oz(top), ["01.2", "01.9", "01.10"]);
});

test("cap, short text and click target", () => {
  const findings = Array.from({ length: 30 }, (_, i) => f(String(i + 1)));
  assert.equal(topPositionen(findings, [], 25).length, 25);
  assert.equal(topPositionen(findings, [], 100).length, 30);
  const krit = f("1", "kritisch");
  const [z] = topPositionen([f("1", "niedrig"), krit], [p("1", "Concrete")], 10);
  assert.equal(z.kurztext, "Concrete");
  assert.equal(z.findingId, krit.id);
  assert.equal(topPositionen([f("x")], [], 10)[0].kurztext, null);
  assert.deepEqual(topPositionen([], [], 10), []);
});
