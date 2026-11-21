// Run: node --test web/lib/spezifikationen-auto.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { anforderungText, autoFelder, emptySource, leseAnforderung } from "./spezifikationen.ts";

test("requirement text is read into parameter, comparator, value and unit", () => {
  assert.deepEqual(leseAnforderung("10 cm"), { parameter: "", comparator: "eq", value: 10, unit: "cm" });
  assert.deepEqual(leseAnforderung("min. 12,5 cm Dicke"), { parameter: "thickness", comparator: "min", value: 12.5, unit: "cm" });
  assert.deepEqual(leseAnforderung("Breite höchstens 40 mm"), { parameter: "width", comparator: "max", value: 40, unit: "mm" });
  assert.equal(leseAnforderung("nach Absprache"), null);
  assert.equal(anforderungText(leseAnforderung("≥ 3 %  Gefälle")), "slope ≥ 3 %");
});

test("edits fill derived fields but never overwrite manual ones or the confirmation", () => {
  const s = { ...emptySource("S1"), verified: true };
  assert.deepEqual(autoFelder(s, { text: "min 20 cm" }).requirement, { parameter: "", comparator: "min", value: 20, unit: "cm" });
  const manuell = { ...s, text: "20 cm", requirement: { parameter: "thickness", comparator: "eq", value: 25, unit: "cm" } };
  assert.equal(autoFelder(manuell, { text: "30 cm" }).requirement, undefined);
  assert.equal(autoFelder(s, { document_ref: "DIN 18195-4" }).category, "german_standard");
  assert.equal(autoFelder(s, { source_type: "internet" }).category, "external_other");
  assert.equal(autoFelder(s, { scope: { oz: ["01.001", "01.002"], description: "" } }).scope.description, "OZ 01.001, 01.002");
  assert.equal(autoFelder({ ...s, scope: { oz: [], description: "Mine" } }, { scope: { oz: ["1"], description: "Mine" } }).scope, undefined);
  assert.equal("verified" in autoFelder(s, { text: "1 m" }), false);
});
