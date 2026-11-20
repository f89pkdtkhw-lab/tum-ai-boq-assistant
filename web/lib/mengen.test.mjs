// Run: node --test web/lib/mengen.test.mjs  (Node >= 23 strips the TypeScript types of mengen.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { mengenSummen, mengenSchluessel, OHNE_TITEL } from "./mengen.ts";

const p = (menge, einheit, typ = "normal", titel = ["01 Earthworks"]) =>
  ({ oz: "x", kurztext: "", langtext: "", menge, einheit, ep: null, gp: null, typ, titel_pfad: titel });

test("sums per unit and title, skips optional, alternative and incomplete items", () => {
  const mengen = mengenSummen([
    p(10, "m³"),
    p(2.5, " M³ "),
    p(4, "m³", "pauschal", ["02 Concrete"]),
    p(3, "kg", "zulage", []),
    p(1, "h", "stundenlohn"),
    p(99, "m³", "bedarf"),
    p(99, "m³", "alternativ"),
    p(null, "m³"),
    p(5, null),
    p(5, "  "),
  ]);
  assert.deepEqual(mengen.einheiten, [
    { schluessel: "m³", einheit: "m³", summe: 16.5, positionen: 3 },
    { schluessel: "kg", einheit: "kg", summe: 3, positionen: 1 },
    { schluessel: "h", einheit: "h", summe: 1, positionen: 1 },
  ]);
  assert.deepEqual(mengen.titel, [
    { titel: "01 Earthworks", summen: { "m³": 12.5, h: 1 } },
    { titel: "02 Concrete", summen: { "m³": 4 } },
    { titel: OHNE_TITEL, summen: { kg: 3 } },
  ]);
  assert.equal(mengen.ausserVertrag, 2);
  assert.equal(mengen.ohneMenge, 3);
});

test("units are not converted and the key matches the tile", () => {
  assert.equal(mengenSchluessel(p(1, "m2")), "m2");
  assert.equal(mengenSchluessel(p(1, "m²")), "m²");
  assert.equal(mengenSchluessel(p(1, "St", "bedarf")), null);
});
