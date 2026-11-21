// Run: node --test web/lib/titelbaum.test.mjs  (Node >= 23 strips the TypeScript types of titelbaum.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { baueTitelbaum, imTeilbaum, ozImTeilbaum, OHNE_TITEL_NAME } from "./titelbaum.ts";

const p = (oz, titel_pfad = []) =>
  ({ oz, kurztext: "", langtext: "", menge: 1, einheit: "m", ep: null, gp: null, typ: "normal", titel_pfad });
const f = (id, oz, schwere = "mittel") =>
  ({ id, oz, kategorie: "fehler", schwere, titel: "", begruendung: "", vorschlag: "", quelle: "regel", regel_id: "R", euro_wirkung: null });

const positionen = [
  p("01.01.0010", ["Earthworks", "Excavation"]),
  p("01.01.0020", ["Earthworks", "Excavation"]),
  p("01.02.0010", ["Earthworks", "Backfill"]),
  p("02.0010", ["Concrete"]),
  p("9", []),
  p("10", ["  ", ""]),
];
const findings = [
  f("a", "01.01.0010", "niedrig"),
  f("b", "01.01.0020", "kritisch"),
  f("c", "01.02.0010", "hoch"),
  f("d", "9", "mittel"),
  f("e", "99", "kritisch"),
];

test("nested paths keep BoQ order, Without title last, counts roll up", () => {
  const baum = baueTitelbaum(positionen, findings);
  assert.deepEqual(baum.map((k) => k.titel), ["Earthworks", "Concrete", OHNE_TITEL_NAME]);
  const [erd, beton, ohne] = baum;
  assert.deepEqual(erd.kinder.map((k) => [k.titel, k.positionen, k.findings, k.maxSchwere]),
    [["Excavation", 2, 2, "kritisch"], ["Backfill", 1, 1, "hoch"]]);
  assert.deepEqual([erd.positionen, erd.findings, erd.maxSchwere], [3, 3, "kritisch"]);
  assert.deepEqual([beton.positionen, beton.findings, beton.maxSchwere, beton.kinder.length], [1, 0, null, 0]);
  // Empty and blank-only paths both go under "Without title".
  assert.deepEqual([ohne.pfad, ohne.positionen, ohne.findings, ohne.maxSchwere], [[], 2, 1, "mittel"]);
  assert.deepEqual(erd.kinder[0].pfad, ["Earthworks", "Excavation"]);
});

test("a finding on a duplicate OZ counts once per node", () => {
  const baum = baueTitelbaum([p("1", ["A"]), p("1", ["A"])], [f("x", "1", "hoch")]);
  assert.deepEqual([baum[0].positionen, baum[0].findings], [2, 1]);
});

test("subtree filter by path prefix, empty path means Without title", () => {
  assert.equal(imTeilbaum(p("1", ["A", "B"]), ["A"]), true);
  assert.equal(imTeilbaum(p("1", ["A", "B"]), ["A", "B"]), true);
  assert.equal(imTeilbaum(p("1", ["A"]), ["A", "B"]), false);
  assert.equal(imTeilbaum(p("1", ["AB"]), ["A"]), false);
  assert.equal(imTeilbaum(p("1", []), []), true);
  assert.equal(imTeilbaum(p("1", ["A"]), []), false);
  assert.deepEqual([...ozImTeilbaum(positionen, ["Earthworks"])], ["01.01.0010", "01.01.0020", "01.02.0010"]);
  assert.deepEqual([...ozImTeilbaum(positionen, [])], ["9", "10"]);
});

test("empty BoQ gives an empty tree", () => {
  assert.deepEqual(baueTitelbaum([], [f("e", "1")]), []);
});
