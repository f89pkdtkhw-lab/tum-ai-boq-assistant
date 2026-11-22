// Run: node --test web/lib/preisbericht.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { preisbericht, preisSpanne, relFuer, summeSpannen, mitManuellemEp, QUELLE_NAME } = await import("./preisbericht.ts");

const pos = (oz, kurztext, menge, ep, gp = menge * ep) => ({ oz, kurztext, langtext: "", menge, einheit: "m³", ep, gp, typ: "normal", titel_pfad: [] });

test("price list first, then past projects, else unchanged; totals and changed count", () => {
  const b = preisbericht(
    [pos("1", "Betonarbeiten Wand", 10, 100), pos("2", "Erdarbeiten Aushub", 10, 20), pos("3", "Malerarbeiten Anstrich", 10, 5), { ...pos("4", "Fenster", null, null), gp: null }],
    [{ trade: "Erdarbeiten", projects: 5, withActual: 5, avgDeviation: 10, deviationSpread: 8 }, { trade: "Malerarbeiten", projects: 5, withActual: 5, avgDeviation: 1, deviationSpread: 2 }],
    [{ item: "Betonarbeiten", unit: "m³", preis: 120 }]);
  assert.deepEqual(b.zeilen.map((z) => [z.oz, z.quelle, z.geschaetzt]), [["1", "preisliste", 1200], ["2", "historie", 220], ["3", "unveraendert", 50], ["4", "ohne_preis", null]]);
  assert.equal(b.war, 1250);
  assert.equal(b.geschaetzt, 1470);
  assert.equal(b.diff, 220);
  assert.equal(b.geaendert, 2);
  // #225: every priced item has a range; the unpriced item has none; total = sum of item ranges
  assert.deepEqual(b.zeilen.map((z) => [z.oz, z.von, z.bis]), [
    ["1", 1140, 1260],   // list ±5 % of 1200
    ["2", 202.4, 237.6], // history spread 8 % of 220
    ["3", 42.5, 57.5],   // unchanged ±15 % of 50
    ["4", null, null],
  ]);
  assert.equal(b.von, 1384.9);
  assert.equal(b.bis, 1555.1);
  assert.deepEqual(summeSpannen(b.zeilen), { von: 1384.9, bis: 1555.1 });
});

test("range width follows the source: list narrow, history from spread, unchanged wide, no price none", () => {
  assert.deepEqual(preisSpanne({ ep: 100, menge: 10, quelle: "preisliste" }), { epVon: 95, epBis: 105, von: 950, bis: 1050 });
  assert.deepEqual(preisSpanne({ ep: 22, menge: 10, quelle: "historie", streuungProzent: 8 }), { epVon: 20.24, epBis: 23.76, von: 202.4, bis: 237.6 });
  assert.equal(relFuer("historie", null), 0.10);
  assert.equal(relFuer("historie", 1), 0.05);
  assert.deepEqual(preisSpanne({ ep: 5, menge: 10, quelle: "unveraendert" }), { epVon: 4.25, epBis: 5.75, von: 42.5, bis: 57.5 });
  assert.deepEqual(preisSpanne({ ep: null, menge: 3, quelle: "ohne_preis" }), { epVon: null, epBis: null, von: null, bis: null });
});

test("index or research fallback uses the explicit range and stays wide without one", () => {
  const p = pos("5", "Bitumenanstrich Wand", 10, 8);
  const b = preisbericht([p], [], [], [{
    oz: "5", menge: 10, einheit: "m²", ep: 16, gp: 160, ep_lv: 8, gp_lv: 80,
    treffer: "index", preis_eintrag: null, aehnlichkeit: null, in_summe: true,
    geschaetzt: true, ep_von: 12, ep_bis: 20,
  }]);
  assert.equal(b.zeilen[0].quelle, "index");
  assert.equal(b.zeilen[0].geschaetzt, 160);
  assert.deepEqual([b.zeilen[0].von, b.zeilen[0].bis], [120, 200]);
  const weit = preisSpanne({ ep: 20, menge: 2, quelle: "recherche" });
  assert.deepEqual(weit, { epVon: 16, epBis: 24, von: 32, bis: 48 });
  assert.ok(b.zeilen[0].verweise.some((v) => v.url && /genesis/i.test(v.url)));
});

test("manual EP override recalculates GP, range, source and the total", () => {
  const b0 = preisbericht([pos("1", "Betonarbeiten Wand", 10, 100)], [], [{ item: "Betonarbeiten", unit: "m³", preis: 120 }]);
  assert.equal(b0.zeilen[0].quelle, "preisliste");
  assert.equal(b0.geschaetzt, 1200);
  const b = preisbericht([pos("1", "Betonarbeiten Wand", 10, 100)], [], [{ item: "Betonarbeiten", unit: "m³", preis: 120 }], null, { "0": 130 });
  assert.equal(b.zeilen[0].quelle, "manuell");
  assert.equal(b.zeilen[0].epGeschaetzt, 130);
  assert.equal(b.zeilen[0].geschaetzt, 1300);
  assert.deepEqual([b.zeilen[0].von, b.zeilen[0].bis], [1235, 1365]); // ±5 %
  assert.equal(b.geschaetzt, 1300);
  assert.equal(b.von, 1235);
  assert.equal(b.bis, 1365);
  const reset = mitManuellemEp(b0.zeilen[0], 120);
  assert.equal(reset.quelle, "manuell");
  assert.equal(QUELLE_NAME.manuell, "Manual");
});

test("price-list match and index fallback carry source references", () => {
  const liste = preisbericht([pos("1", "Betonarbeiten Wand", 10, 100)], [], [{ item: "Betonarbeiten Wand", unit: "m³", preis: 120 }]);
  assert.deepEqual(liste.zeilen[0].verweise.map((v) => v.titel), ["Betonarbeiten Wand"]);
  const idx = preisbericht([pos("2", "Bitumenanstrich", 10, 8)], [], [], [{
    oz: "2", menge: 10, einheit: "m²", ep: 16, gp: 160, ep_lv: 8, gp_lv: 80,
    treffer: "index", preis_eintrag: null, aehnlichkeit: null, in_summe: true,
    geschaetzt: true, ep_von: 12, ep_bis: 20,
    preis_quellen: [{ titel: "Destatis Baupreisindex Wohngebäude", url: "https://www-genesis.destatis.de/datenbank/online/table/61261-0001" }],
  }]);
  assert.equal(idx.zeilen[0].quelle, "index");
  assert.equal(idx.zeilen[0].verweise[0].url, "https://www-genesis.destatis.de/datenbank/online/table/61261-0001");
});
