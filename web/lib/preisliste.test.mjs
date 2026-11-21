// Run: node --test web/lib/preisliste.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { PREISLISTE_FORMATE, preislisteText } from "./preisliste.ts";
import { beilageFehler } from "./regelwerk.ts";

test("price list formats and summary", () => {
  for (const name of ["a.csv", "a.xlsx", "a.X84", "a.d84", "a.x86", "a.D86", "a.json"]) assert.equal(beilageFehler({ name, size: 1 }, PREISLISTE_FORMATE, "Price list"), null);
  assert.match(beilageFehler({ name: "a.pdf", size: 1 }, PREISLISTE_FORMATE, "Price list"), /Allowed: CSV, XLSX, X84, D84, X86, D86, JSON/);
  const e = { id: "e", oz: null, kurztext: "Synthetic", einheit: "m2", ep: 1, quelle: "f:1" };
  assert.equal(preislisteText({ id: "p", dateiname: "demo.csv", waehrung: "EUR", warnungen: [], eintraege: [e, e] }), "demo.csv: 2 entries");
  assert.equal(preislisteText({ id: "p", dateiname: "demo.csv", waehrung: "EUR", warnungen: ["w", "v"], eintraege: [e] }), "demo.csv: 1 entry, 2 warnings");
});
