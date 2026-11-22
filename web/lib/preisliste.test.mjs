// Run: node --test web/lib/preisliste.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { PREIS_LV_FORMATE, PREISLISTE_FORMATE, preislisteText, eintragHinzu, findePreis, lesePreisliste, preislisteCsv } from "./preisliste.ts";
import { beilageFehler } from "./regelwerk.ts";

test("price list formats and summary", () => {
  for (const name of ["a.csv", "a.xlsx", "a.X84", "a.d84", "a.x86", "a.D86", "a.json"]) assert.equal(beilageFehler({ name, size: 1 }, PREISLISTE_FORMATE, "Price list"), null);
  assert.match(beilageFehler({ name: "a.pdf", size: 1 }, PREISLISTE_FORMATE, "Price list"), /Allowed: CSV, XLSX, X84, D84, X86, D86, JSON/);
  const e = { id: "e", oz: null, kurztext: "Synthetic", einheit: "m2", ep: 1, quelle: "f:1" };
  assert.equal(preislisteText({ id: "p", dateiname: "demo.csv", waehrung: "EUR", warnungen: [], eintraege: [e, e] }), "demo.csv: 2 entries");
  assert.equal(preislisteText({ id: "p", dateiname: "demo.csv", waehrung: "EUR", warnungen: ["w", "v"], eintraege: [e] }), "demo.csv: 1 entry, 2 warnings");
});


test("CSV with German header, semicolons and German number format", () => {
  const l = lesePreisliste("Bezeichnung;Einheit;Preis\nBetonarbeiten Bodenplatte;m³;1.250,50 €\nErdarbeiten;m³;24\n;m;3");
  assert.deepEqual(l, [{ item: "Betonarbeiten Bodenplatte", unit: "m³", preis: 1250.5 }, { item: "Erdarbeiten", unit: "m³", preis: 24 }]);
});

test("JSON list and missing columns", () => {
  assert.deepEqual(lesePreisliste('[{"item":"Fenster","unit":"St","price":900}]'), [{ item: "Fenster", unit: "St", preis: 900 }]);
  assert.throws(() => lesePreisliste("a,b\n1,2"), /item and a price/);
});

test("matching prefers the exact name, then the longest contained entry with the same unit", () => {
  const l = [{ item: "Betonarbeiten", unit: "m³", preis: 200 }, { item: "Betonarbeiten Bodenplatte", unit: "m³", preis: 250 }, { item: "Fenster", unit: "St", preis: 900 }];
  assert.equal(findePreis(l, "Betonarbeiten Bodenplatte C25/30", "m³").preis, 250);
  assert.equal(findePreis(l, "Betonarbeiten Wand", "m³").preis, 200);
  assert.equal(findePreis(l, "Betonarbeiten Wand", "m²"), null);
  assert.equal(findePreis(l, "Mauerwerk", "m²"), null);
});

test("own entry: material + hours × rate, replaces the same item and reads back from CSV", () => {
  let l = eintragHinzu([], { item: "Mauerwerk KS 24", unit: "m²", material: 38, stunden: 0.8, stundensatz: 62.5 });
  assert.deepEqual(l, [{ item: "Mauerwerk KS 24", unit: "m²", material: 38, stunden: 0.8, lohn: 50, preis: 88 }]);
  l = eintragHinzu(l, { item: "mauerwerk ks 24", unit: "m²", material: 40, stunden: 1, stundensatz: 60 });
  assert.equal(l.length, 1);
  assert.equal(l[0].preis, 100);
  assert.deepEqual(lesePreisliste(preislisteCsv(l)), l);
});

test("CSV with only material and labour columns sums them", () => {
  assert.deepEqual(lesePreisliste("item;unit;material;labour\nPutz;m²;8;12,5"), [{ item: "Putz", unit: "m²", preis: 20.5, material: 8, lohn: 12.5 }]);
});

test("a D84 offer can bring its tender bill (D83/X83/D86/X86) for the item texts", () => {
  for (const name of ["lv.d83", "LV.X83", "lv.D86", "lv.x86"]) assert.equal(beilageFehler({ name, size: 1 }, PREIS_LV_FORMATE, "Matching bill"), null);
  assert.match(beilageFehler({ name: "lv.pdf", size: 1 }, PREIS_LV_FORMATE, "Matching bill"), /Allowed: X83, D83, X86, D86/);
});
