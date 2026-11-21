// Run: node --test web/lib/wettbewerb.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { auswerten, bewerte, demo, empfehle, leseDokument, leseZeilen } = await import("./wettbewerb.ts");

test("lines with company and amount, German and English numbers", () => {
  assert.deepEqual(leseZeilen("Muster Bau GmbH; 1.234.567,89 €\nNord AG: 980,000\n1200000"),
    [{ firma: "Muster Bau GmbH", summe: 1234567.89 }, { firma: "Nord AG", summe: 980000 }, { firma: "Bidder 3", summe: 1200000 }]);
});

test("usual margin over our own costs, wins, and flags for dumping", () => {
  const subs = [
    { id: "1", projekt: "P1", datum: "2026-01-01", selbstkosten: 900, gebote: [{ firma: "A", summe: 1000 }, { firma: "Dump", summe: 800 }, { firma: "B", summe: 950 }] },
    { id: "2", projekt: "P2", datum: "2026-02-01", selbstkosten: 900, gebote: [{ firma: "A", summe: 1000 }, { firma: "Dump", summe: 820 }, { firma: "B", summe: 1100 }] },
  ];
  const f = Object.fromEntries(auswerten(subs).map((x) => [x.firma, x]));
  assert.equal(f.A.marge, 10);
  assert.equal(f.Dump.einstufung, "unrealistisch");     // below our costs and ≥10 % under the next bid twice
  assert.equal(f.Dump.siege, 2);
  assert.equal(f.Dump.sprunghaft, 2);
  assert.equal(f.A.einstufung, "normal");
  assert.equal(auswerten(subs)[0].firma, "Dump");      // lowest margin first
});

test("demo history: fictional bidders, one of them unrealistic", () => {
  const firmen = auswerten(demo());
  assert.equal(firmen.length, 6);
  assert.equal(firmen.find((x) => x.firma === "Bidder E").einstufung, "unrealistisch");
  assert.ok(firmen.filter((x) => x.einstufung === "normal").length >= 2);
});

test("tender opening document: table with header, or free lines with rank and place", () => {
  assert.deepEqual(leseDokument("Rang;Bieter;Angebotssumme brutto\n1;Muster Bau GmbH;1.234.567,89\n2;\"Nord AG\";1.300.000,00"),
    [{ firma: "Muster Bau GmbH", summe: 1234567.89 }, { firma: "Nord AG", summe: 1300000 }]);
  assert.deepEqual(leseDokument("Niederschrift Submission Kita Nord\n1. Muster Bau GmbH, Musterstadt   1.234.567,89 €\n2) Süd Hochbau KG – 1 310 000,00 EUR\nSumme aller Angebote 2.544.567,89"),
    [{ firma: "Muster Bau GmbH, Musterstadt", summe: 1234567.89 }, { firma: "Süd Hochbau KG", summe: 1310000 }]);
});

test("one tender: margin per bid and the very low outlier", () => {
  const z = bewerte([{ firma: "A", summe: 1000 }, { firma: "Low", summe: 850 }, { firma: "B", summe: 1050 }], 900);
  assert.deepEqual(z.map((x) => [x.firma, x.rang, x.ausreisser]), [["Low", 1, true], ["A", 2, false], ["B", 3, false]]);
  assert.equal(z[1].marge, 10);
});

test("prediction: skip unrealistic bidders, undercut the cheapest serious one, keep a minimum margin", () => {
  const subs = demo();
  const firmen = auswerten(subs);
  const e = empfehle(1000000, firmen, subs, { unterbieten: 1, minMarge: 2 });
  assert.ok(e.ignoriert.includes("Bidder E"));
  assert.ok(!e.vorhersagen.some((v) => v.firma === "Bidder E"));
  assert.ok(e.empfohlen < e.vorhersagen[0].summe);
  assert.ok(e.marge >= 2);
  assert.ok(e.siegquote > 0);
  const hart = empfehle(1000000, firmen, subs, { unterbieten: 30, minMarge: 4 });
  assert.equal(hart.grund, "mindestmarge");
  assert.equal(hart.marge, 4);
});
