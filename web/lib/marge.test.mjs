// Run: node --test web/lib/marge.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { auswerten, bereinige, bieterFarbe, bieterFarben, bieterFarbHue, BIETER_FARB_HUES, impliziteMarge, kennzahlen, leseGebote, leseXlsx, markerVersatz, monateFaktor, sliderHue, sliderMarker } = await import("./marge.ts");
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

test("markup from the split or back-calculated, IQR drops the outlier, default margin is median implied − 1", () => {
  const r = auswerten(leseGebote(tabelle));
  assert.deepEqual(r.liste.map((b) => Math.round(b.aufschlag)), [15, 16, 17, 18, 20, 80]);
  assert.equal(r.liste[1].angebot, 5800); // no quantity in the bid: our quantity × unit price
  assert.equal(r.liste.find((b) => b.name === "F").ausreisser, true);
  const [p] = r.posten;
  assert.equal(p.n, 5); assert.equal(p.raus, 0); assert.equal(p.wenig, false); // F already dropped at bidder level
  assert.equal(p.median, 17);
  assert.equal(r.medianMarge, 7); assert.equal(r.marge, 6); // implied median 17−10, then −1
  assert.equal(p.aufschlag, 16);
  const c = (x) => Math.round(x * 100) / 100;
  assert.deepEqual([c(p.preis), c(p.preisKonk)], [58, 58.5]);
  assert.deepEqual([c(r.summe.uns), c(r.summe.konk), c(r.summe.gewinn), c(r.summe.gewinnKonk)], [5800, 5850, 300, 350]);
  assert.deepEqual([r.auswahl.bieter, r.auswahl.vonBietern], [5, 6]);
});

test("checking a subset recomputes mean and median; the floor (operating costs + minimum margin) holds", () => {
  const r = auswerten(leseGebote(tabelle), { namen: ["A", "B", "C", "D"], ausreisser: false, marge: 0 });
  assert.deepEqual([r.auswahl.bieter, r.auswahl.median, r.bieter.map((b) => b.name).join("")], [4, 16.5, "ABCD"]);
  assert.equal(r.posten[0].wenig, true);
  assert.equal(r.boden, 2); assert.equal(r.marge, 2); // slider cannot go under the 2 % minimum
  assert.equal(r.posten[0].aufschlag, 12); assert.equal(r.posten[0].amBoden, true);
});

test("under five points only implausible values go; mean vs median over 3 points is skewed", () => {
  assert.deepEqual(bereinige([10, -5, 120, 30]), { werte: [10, 30], raus: 2, wenig: true });
  assert.equal(kennzahlen([15, 16, 17, 27, 28]).schief, true);
  assert.equal(kennzahlen([15, 16, 17]).schief, false);
});

test("IQR outlier toggle: on drops F from the selection, off keeps F and raises the mean", () => {
  const gebote = leseGebote(tabelle);
  const an = auswerten(gebote, { ausreisser: true });
  const aus = auswerten(gebote, { ausreisser: false });
  assert.equal(an.auswahl.bieter, 5);
  assert.equal(aus.auswahl.bieter, 6);
  assert.ok(aus.auswahl.mittel > an.auswahl.mittel);
  assert.equal(an.liste.find((b) => b.name === "F").ausreisser, true);
  assert.equal(aus.liste.find((b) => b.name === "F").ausreisser, false);
});

test("annual operating costs are pro-rated by months/12 for us and for a disclosed competitor split", () => {
  assert.equal(monateFaktor(10), 10 / 12);
  assert.equal(monateFaktor(0), 1);
  const r = auswerten(leseGebote(tabelle), { monate: 6, namen: ["A"], ausreisser: false, marge: 2 });
  assert.equal(r.faktor, 0.5);
  assert.equal(r.posten[0].bgk, 5); // our 10 % annual × 6/12
  assert.equal(r.posten[0].aufschlag, 7);
  const a = r.liste.find((b) => b.name === "A");
  assert.equal(a.bgk, 8); // table shows the annual figure from the file
  assert.equal(a.aufschlag, 8 * 0.5 + 7); // 11 % project markup
});

test("slider hue is red at the cost floor, green at or above the competitor median, and interpolates in between", () => {
  assert.equal(sliderHue(2, 2, 10), 0);
  assert.equal(sliderHue(10, 2, 10), 120);
  assert.equal(sliderHue(18, 2, 10), 120);
  assert.equal(sliderHue(6, 2, 10), 60);
});

test("the synthetic Excel file is read in the browser way and fills every part of the page", async () => {
  const datei = readFileSync(new URL("../../data/testfaelle/marge/competitor_bids_synthetic.xlsx", import.meta.url));
  const zeilen = await leseXlsx(datei.buffer.slice(datei.byteOffset, datei.byteOffset + datei.byteLength));
  assert.deepEqual(zeilen[0].slice(0, 6), ["Provider", "Item", "Unit", "Quantity", "Unit price", "Current offer"]);
  const r = auswerten(leseGebote(zeilen));
  assert.equal(r.auswahl.vonBietern, 10);
  assert.ok(r.liste.find((b) => b.name === "Fuchs Construction").aufschlag > 70);
  assert.equal(r.liste.find((b) => b.name === "Fuchs Construction").ausreisser, true);
  assert.equal(r.auswahl.bieter, 9);
  assert.equal(r.posten.length, 6);
  assert.ok(r.posten.every((p) => p.median != null && p.median < 30)); // the outlier never sets the benchmark
  assert.ok(r.posten.find((p) => p.item.startsWith("Screed")).wenig);
  assert.ok(r.posten.find((p) => p.item.startsWith("Masonry")).schief);
  assert.ok(r.summe.uns < r.summe.konk && r.summe.gewinn < r.summe.gewinnKonk);
});

test("the margin demo Excel is read and fills the page, with an outlier and a skewed thin item", async () => {
  const datei = readFileSync(new URL("../../docs/beispiele/margin-demo.xlsx", import.meta.url));
  const zeilen = await leseXlsx(datei.buffer.slice(datei.byteOffset, datei.byteOffset + datei.byteLength));
  assert.ok(zeilen.some((z) => z[0] === "Anbieter" || z.includes?.("Anbieter")));
  const r = auswerten(leseGebote(zeilen));
  assert.equal(r.posten.length, 22);
  assert.equal(r.auswahl.vonBietern, 6);
  assert.equal(r.liste.find((b) => b.name === "Blitzofferte Bau UG").ausreisser, true);
  assert.equal(r.auswahl.bieter, 5);
  const tueren = r.posten.find((p) => p.item.startsWith("Innentüren"));
  assert.ok(tueren.wenig && tueren.schief);
  assert.ok(r.posten.filter((p) => !p.item.startsWith("Innentüren")).every((p) => !p.wenig && p.median != null));
  assert.ok(r.summe.uns < r.summe.konk);
});

test("company colours come from a spaced palette and stay unique within a set", () => {
  assert.equal(bieterFarbHue("A"), bieterFarbHue("A"));
  assert.ok(BIETER_FARB_HUES.includes(bieterFarbHue("Blitzofferte Bau UG")));
  assert.match(bieterFarbe("Nordbau"), /^hsl\(\d+ 72% 44%\)$/);
  const namen = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"];
  const map = bieterFarben(namen);
  assert.equal(map.size, namen.length);
  assert.equal(new Set(map.values()).size, namen.length);
  assert.deepEqual([...map.keys()], [...namen].sort((a, b) => a.localeCompare(b)));
});

test("slider markers use implied margin, sort low to high, clamp and keep outliers visible", () => {
  const r = auswerten(leseGebote(tabelle));
  const marker = sliderMarker(r.liste, r.bgkUns, r.boden, r.hiMarge);
  assert.equal(marker.length, 6);
  const werte = marker.map((m) => m.marge);
  assert.deepEqual(werte, [...werte].sort((a, b) => a - b));
  const fuchs = marker.find((m) => m.name === "F");
  assert.equal(fuchs.ausreisser, true);
  assert.equal(fuchs.pct, 100); // 80 % markup is above hiMarge, clamped to the end
  assert.equal(impliziteMarge(17, 10), 7);
  for (const m of marker) {
    assert.ok(m.pct >= 0 && m.pct <= 100);
    assert.equal(m.marge, impliziteMarge(r.liste.find((b) => b.name === m.name).aufschlag, r.bgkUns));
  }
});

test("close markers get staggered vertical lanes so they do not fully cover each other", () => {
  const lanes = markerVersatz([{ pct: 10 }, { pct: 11 }, { pct: 50 }, { pct: 10.5 }], 3);
  assert.equal(lanes[0], 0);
  assert.equal(lanes[1], 1);
  assert.equal(lanes[2], 0); // far from the cluster
  assert.ok(lanes[3] !== 0 && lanes[3] !== 1);
  assert.deepEqual(markerVersatz([{ pct: 0 }, { pct: 50 }, { pct: 100 }], 3), [0, 0, 0]);
});
