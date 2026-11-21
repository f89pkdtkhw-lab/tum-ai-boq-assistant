// Run: node --test web/lib/preis-db.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { abfrage, filtere, preisFehler, speicherBody, vorschau } = await import("./preis-db.ts");

const e = (kurztext, einheit, ep, oz = null) => ({ id: kurztext, oz, kurztext, einheit, ep, quelle: "demo.csv:2" });
const liste = { id: "p", dateiname: "demo.csv", waehrung: "EUR", warnungen: [], eintraege: [
  e("Synthetic screed", "m2", 12.5), e("", "m", 3, "01.02"), e("No unit", "", 4), e("Synthetic screed", "m2", 13), e("Negative", "m", -1),
] };

test("preview mapping keeps every row, marks invalid ones", () => {
  const v = vorschau(liste);
  assert.equal(v.length, 5);
  assert.deepEqual(v[1], { item: "01.02", unit: "m", price_per_unit: 3, quelle: "demo.csv:2", gueltig: true });
  assert.deepEqual(v.map((z) => z.gueltig), [true, true, false, true, false]);
});

test("request body: valid rows only, same item+unit keeps the last price", () => {
  assert.deepEqual(speicherBody(vorschau(liste)), [
    { item: "Synthetic screed", unit: "m2", price_per_unit: 13 },
    { item: "01.02", unit: "m", price_per_unit: 3 },
  ]);
  assert.deepEqual(speicherBody([]), []);
});

test("search filter and query string", () => {
  const db = [{ id: 1, item: "Synthetic screed", unit: "m²", price_per_unit: 12.5 }, { id: 2, item: "Synthetic edge strip", unit: "m", price_per_unit: 4 }];
  assert.deepEqual(filtere(db, "SCREED", "").map((x) => x.id), [1]);
  assert.deepEqual(filtere(db, "synthetic", "m").map((x) => x.id), [2]);
  assert.deepEqual(filtere(db, "", "").map((x) => x.id), [1, 2]);
  assert.equal(abfrage(" screed ", "", 50), "?item=screed&limit=50");
  assert.equal(abfrage("", "m²"), "?unit=m%C2%B2&limit=200");
});

test("404 texts per step, other errors keep the reason", () => {
  const nf = Object.assign(new Error("Not Found"), { status: 404 });
  assert.match(preisFehler("import", nf), /cannot read price lists yet/);
  assert.match(preisFehler("speichern", nf), /Nothing was saved/);
  assert.match(preisFehler("laden", nf), /not available/);
  assert.equal(preisFehler("speichern", Object.assign(new Error("Row 2: unit missing"), { status: 422 })), "Could not save the prices: Row 2: unit missing");
  assert.match(preisFehler("laden", new TypeError("x")), /Cannot connect/);
});
