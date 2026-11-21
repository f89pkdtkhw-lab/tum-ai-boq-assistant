// Run: node --test web/lib/marge.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { auswerten, bereinige, kennzahlen, leseGebote, leseXlsx } = await import("./marge.ts");
const { readFileSync } = await import("node:fs");

const tabelle = [
  ["Bidder", "Item", "Unit", "Quantity", "Unit price", "Direct cost", "Operating cost %", "Margin %"],
  ["Our company", "Masonry", "m2", "100", "", "50", "10", "2"],
  ["A", "Masonry", "m2", "", "", "48", "8", "7"],
  ["B", "Masonry", "m2", "", "58", "", "", ""],
  ["C", "Masonry", "m2", "", "58,50", "", "", ""],
  ["D", "Masonry", "m2", "", "59", "", "", ""],
  ["E", "Masonry", "m2", "", "60", "", "", ""],
  ["F", "Masonry", "m2", "", "90", "", "", ""],
];

test("markup from the split or back-calculated, IQR drops the outlier, median minus one point", () => {
  const r = auswerten(leseGebote(tabelle), [-Infinity, Infinity], -1);
  assert.deepEqual(r.liste.map((b) => Math.round(b.aufschlag)), [15, 16, 17, 18, 20, 80]);
  assert.equal(r.liste[1].angebot, 5800); // no quantity in the bid: our quantity × unit price
  const [p] = r.posten;
  assert.equal(p.n, 5); assert.equal(p.raus, 1); assert.equal(p.wenig, false);
  assert.equal(p.median, 17); assert.equal(p.aufschlag, 16);
  const c = (x) => Math.round(x * 100) / 100;
  assert.deepEqual([c(p.preis), c(p.preisKonk)], [58, 58.5]);
  assert.deepEqual([c(r.summe.uns), c(r.summe.konk), c(r.summe.gewinn), c(r.summe.gewinnKonk)], [5800, 5850, 300, 350]);
  assert.deepEqual([r.auswahl.bieter, r.auswahl.vonBietern], [6, 6]);
});

test("narrowing the range keeps fewer bidders; the floor (operating costs + minimum margin) holds", () => {
  const r = auswerten(leseGebote(tabelle), [10, 18], -10);
  assert.deepEqual([r.auswahl.bieter, r.auswahl.median, r.bieter.map((b) => b.name).join("")], [4, 16.5, "ABCD"]);
  assert.equal(r.posten[0].wenig, true);
  assert.equal(r.posten[0].aufschlag, 12); assert.equal(r.posten[0].amBoden, true);
});

test("under five points only implausible values go; mean vs median over 3 points is skewed", () => {
  assert.deepEqual(bereinige([10, -5, 120, 30]), { werte: [10, 30], raus: 2, wenig: true });
  assert.equal(kennzahlen([15, 16, 17, 27, 28]).schief, true);
  assert.equal(kennzahlen([15, 16, 17]).schief, false);
});

test("the synthetic Excel file is read in the browser way and fills every part of the page", async () => {
  const datei = readFileSync(new URL("../../data/testfaelle/marge/competitor_bids_synthetic.xlsx", import.meta.url));
  const zeilen = await leseXlsx(datei.buffer.slice(datei.byteOffset, datei.byteOffset + datei.byteLength));
  assert.deepEqual(zeilen[0].slice(0, 6), ["Provider", "Item", "Unit", "Quantity", "Unit price", "Current offer"]);
  const r = auswerten(leseGebote(zeilen), [-Infinity, Infinity], -1);
  assert.equal(r.auswahl.vonBietern, 10);
  assert.ok(r.liste.find((b) => b.name === "Fuchs Construction").aufschlag > 70);
  assert.equal(r.posten.length, 6);
  assert.ok(r.posten.every((p) => p.median != null && p.median < 30)); // the outlier never sets the benchmark
  assert.ok(r.posten.find((p) => p.item.startsWith("Screed")).wenig);
  assert.ok(r.posten.find((p) => p.item.startsWith("Masonry")).schief);
  assert.ok(r.summe.uns < r.summe.konk && r.summe.gewinn < r.summe.gewinnKonk);
});
