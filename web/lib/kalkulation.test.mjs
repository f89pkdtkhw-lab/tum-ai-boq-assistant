// Run: node --test web/lib/kalkulation.test.mjs  (Node >= 23 strips the TypeScript types of kalkulation.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aenderung, demoKalkulation, filtereStatus, hatKalkulation, kalkulationsZeilen, kosten, mitVorzeichen, statusInfo, zaehleStatus,
} from "./kalkulation.ts";

const p = (oz, menge = 10, ep = null) =>
  ({ oz, kurztext: `Synthetic item ${oz}`, langtext: "", menge, einheit: "m2", ep, gp: null, typ: "normal", titel_pfad: [] });
const lv = { name: "Synthetic", quelle: "test", positionen: [p("01.01"), p("01.02"), p("01.03"), p("01.04"), p("01.05")], summen: {} };
const eur = (n) => `€${n.toFixed(2)}`;

test("missing fields: section hidden, no rows", () => {
  assert.equal(hatKalkulation({}), false);
  assert.equal(hatKalkulation({ kalkulation: null, geschaetztes_lv: null }), false);
  assert.deepEqual(kalkulationsZeilen({ lv }), []);
  const k = kosten(undefined, undefined, []);
  assert.equal(k.originalNetto, null);
  assert.equal(k.differenz, null);
});

test("priced original only (B6): every row unchanged, no-price rows marked, short text from the BoQ", () => {
  const kalkulation = {
    waehrung: "EUR", mwst_satz: 0.19, summe_netto: 125, summe_brutto: 148.75, ohne_preis: 1, vollstaendig: false,
    positionen: [
      { oz: "01.01", menge: 10, einheit: "m2", ep: 12.5, gp: 125, ep_lv: null, gp_lv: null, treffer: "oz", preis_eintrag: "x", aehnlichkeit: 1, in_summe: true },
      { oz: "01.02", menge: 3, einheit: "m2", ep: null, gp: null, ep_lv: null, gp_lv: null, treffer: "kein_treffer", preis_eintrag: null, aehnlichkeit: null, in_summe: false },
    ],
  };
  const zeilen = kalkulationsZeilen({ lv, kalkulation });
  assert.equal(hatKalkulation({ kalkulation }), true);
  assert.deepEqual(zeilen.map((z) => [z.oz, z.status, z.ohnePreis, z.kurztext]),
    [["01.01", "unchanged", false, "Synthetic item 01.01"], ["01.02", "unchanged", true, "Synthetic item 01.02"]]);
  const k = kosten(kalkulation, null, zeilen);
  assert.deepEqual([k.originalNetto, k.bruttoOriginal, k.geschaetztNetto, k.ohnePreis, k.vollstaendig], [125, 148.75, null, 1, false]);
});

test("estimated bill (B8): one row per position incl. added and removed, counts, filter, finding link", () => {
  const bericht = { lv, ...demoKalkulation(lv.positionen) };
  bericht.anpassungen[0].finding_id = "f-7";
  const zeilen = kalkulationsZeilen(bericht);
  assert.equal(zeilen.length, lv.positionen.length + 1);
  assert.deepEqual(zaehleStatus(zeilen), { unchanged: 3, updated: 1, added: 1, removed: 1 });
  assert.deepEqual(zaehleStatus(zeilen), bericht.geschaetztes_lv.anzahl);
  assert.deepEqual(filtereStatus(zeilen, "removed").map((z) => z.oz), ["01.03"]);
  assert.equal(filtereStatus(zeilen, null).length, zeilen.length);
  assert.equal(zeilen[1].findingId, "f-7");
  assert.equal(zeilen[3].ohnePreis, true);
  assert.equal(zeilen.find((z) => z.status === "removed").freigabe, true);
});

test("demo sums are consistent: estimated = original + difference; removed keeps the original row", () => {
  const { kalkulation, geschaetztes_lv: g } = demoKalkulation(lv.positionen);
  const k = kosten(kalkulation, g, []);
  assert.ok(Math.abs(k.originalNetto + k.differenz - k.geschaetztNetto) < 0.01);
  assert.equal(g.positionen.find((x) => x.status === "removed").gp_neu, 0);
  assert.ok(g.positionen.find((x) => x.status === "removed").gp_alt > 0);
  // Original net falls back to estimated − difference when only B8 is present.
  assert.ok(Math.abs(kosten(null, g, []).originalNetto - kalkulation.summe_netto) < 0.01);
});

test("status labels are never colour-only", () => {
  assert.equal(statusInfo("added").marke, "+ new");
  assert.equal(statusInfo("removed").marke, "− removed");
  assert.equal(statusInfo("updated").marke, "old → new");
  assert.equal(statusInfo("bogus").wert, "unchanged");
});

test("diff formatting", () => {
  assert.equal(aenderung(10, 12, "updated", String), "10 → 12");
  assert.equal(aenderung(10, 10, "unchanged", String), "10");
  assert.equal(aenderung(null, 12, "added", String), "12");
  assert.equal(aenderung(10, 0, "removed", String), "10");
  assert.equal(aenderung(null, 5, "updated", String), "unknown → 5");
  assert.equal(mitVorzeichen(250, eur), "+€250.00");
  assert.equal(mitVorzeichen(-80, eur), "−€80.00");
  assert.equal(mitVorzeichen(0, eur), "€0.00");
});

test("t237: estimated prices carry their kind, range and sources; tiles count them", () => {
  const kalkulation = {
    waehrung: "EUR", mwst_satz: 0.19, summe_netto: 3124.06, summe_brutto: 3717.63, ohne_preis: 0, vollstaendig: true,
    enthaelt_schaetzungen: true, geschaetzt_anzahl: 1,
    positionen: [
      { oz: "1", menge: 181, einheit: "m²", ep: 17.26, gp: 3124.06, ep_lv: null, gp_lv: null, treffer: "index", preis_eintrag: null,
        aehnlichkeit: null, in_summe: true, geschaetzt: true, ep_von: 10.62, ep_bis: 23.9,
        preis_quellen: [{ titel: "Destatis Baupreisindex", url: "https://www-genesis.destatis.de/x" }], schaetzung_hinweis: "Index estimate" },
      { oz: "2", menge: 1, einheit: "St", ep: 5, gp: 5, ep_lv: null, gp_lv: null, treffer: "oz", preis_eintrag: "a", aehnlichkeit: 1, in_summe: true },
    ],
  };
  const zeilen = kalkulationsZeilen({ lv, kalkulation });
  assert.deepEqual(zeilen[0].schaetzung, { art: "index", von: 10.62, bis: 23.9, quellen: kalkulation.positionen[0].preis_quellen, hinweis: "Index estimate" });
  assert.equal(zeilen[0].ohnePreis, false);
  assert.equal(zeilen[1].schaetzung, null);
  assert.equal(kosten(kalkulation, undefined, zeilen).geschaetzt, 1);
});
