// Run: node --test web/lib/preis-anpassung.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const {
  PREIS_ANPASSUNG_AKTUELL, PREIS_ANPASSUNG_PRAEFIX,
  berichtMitAnpassungen, ladePreisAnpassungen, leseAnpassungen, setzePreisAnpassung, speicherePreisAnpassungen,
} = await import("./preis-anpassung.ts");

function mockStorage() {
  const data = new Map();
  const storage = {
    get length() { return data.size; },
    key(i) { return [...data.keys()][i] ?? null; },
    getItem(k) { return data.has(k) ? data.get(k) : null; },
    setItem(k, v) { data.set(k, String(v)); },
    removeItem(k) { data.delete(k); },
    clear() { data.clear(); },
  };
  globalThis.window = { sessionStorage: storage };
  return storage;
}

test("leseAnpassungen keeps only finite numeric row indexes", () => {
  assert.deepEqual(leseAnpassungen(null), {});
  assert.deepEqual(leseAnpassungen({ "0": 12.5, "2": 8, foo: 1, "1": "x", "3": NaN }), { "0": 12.5, "2": 8 });
});

test("session store writes to the evaluation key and supports reset", () => {
  const s = mockStorage();
  setzePreisAnpassung("e1", 0, 15.5);
  setzePreisAnpassung("e1", 2, 9);
  assert.deepEqual(ladePreisAnpassungen("e1"), { "0": 15.5, "2": 9 });
  assert.equal(s.getItem(PREIS_ANPASSUNG_PRAEFIX + "e1"), JSON.stringify({ "0": 15.5, "2": 9 }));
  assert.equal(s.getItem(PREIS_ANPASSUNG_AKTUELL), JSON.stringify({ "0": 15.5, "2": 9 }));
  setzePreisAnpassung("e1", 0, null);
  assert.deepEqual(ladePreisAnpassungen("e1"), { "2": 9 });
  speicherePreisAnpassungen("e1", {});
  assert.deepEqual(ladePreisAnpassungen("e1"), {});
  assert.equal(s.getItem(PREIS_ANPASSUNG_PRAEFIX + "e1"), null);
});

test("berichtMitAnpassungen updates EP, GP, range and the net sum", () => {
  const bericht = {
    lv: { name: "S", quelle: "s", positionen: [
      { oz: "01.01", kurztext: "A", langtext: "", menge: 10, einheit: "m²", ep: 8, gp: 80, typ: "normal", titel_pfad: [] },
      { oz: "01.02", kurztext: "B", langtext: "", menge: 5, einheit: "m", ep: 4, gp: 20, typ: "normal", titel_pfad: [] },
    ], summen: {} },
    findings: [], kennzahlen: { positionen: 2, findings: 0, kritisch: 0, modell_mock: true },
    zusammenfassung: { score: 9, score_abzuege: [], schaetzung_abweichung_eur: 0, grosse_probleme: 0, warnungen: 0, hinweise: 0, empfehlungen: 0 },
    kalkulation: {
      waehrung: "EUR", mwst_satz: 0.19, summe_netto: 100, summe_brutto: 119, ohne_preis: 0, vollstaendig: true,
      positionen: [
        { oz: "01.01", menge: 10, einheit: "m²", ep: 8, gp: 80, ep_lv: 8, gp_lv: 80, treffer: "text", preis_eintrag: "a", aehnlichkeit: 1, in_summe: true },
        { oz: "01.02", menge: 5, einheit: "m", ep: 4, gp: 20, ep_lv: 4, gp_lv: 20, treffer: "text", preis_eintrag: "b", aehnlichkeit: 1, in_summe: true },
      ],
    },
    geschaetztes_lv: {
      positionen: [
        { oz: "01.01", status: "unchanged", kurztext: "A", einheit: "m²", menge_alt: 10, menge_neu: 10, ep: 8, gp_alt: 80, gp_neu: 80, anpassung_ids: [], grund: "", freigabe_noetig: false, gp_von: 76, gp_bis: 84 },
        { oz: "01.02", status: "unchanged", kurztext: "B", einheit: "m", menge_alt: 5, menge_neu: 5, ep: 4, gp_alt: 20, gp_neu: 20, anpassung_ids: [], grund: "", freigabe_noetig: false, gp_von: 19, gp_bis: 21 },
      ],
      summe_netto: 100, summe_brutto: 119, differenz_netto: 0, differenz_prozent: 0, anzahl: { unchanged: 2, updated: 0, added: 0, removed: 0 },
      summe_netto_von: 95, summe_netto_bis: 105,
    },
  };
  const neu = berichtMitAnpassungen(bericht, { "0": 10 });
  assert.equal(neu.kalkulation.positionen[0].ep, 10);
  assert.equal(neu.kalkulation.positionen[0].gp, 100);
  assert.equal(neu.kalkulation.positionen[1].ep, 4);
  assert.equal(neu.kalkulation.summe_netto, 120);
  assert.equal(neu.geschaetztes_lv.positionen[0].gp_neu, 100);
  assert.equal(neu.geschaetztes_lv.summe_netto, 120);
  assert.equal(neu.geschaetztes_lv.differenz_netto, 20);
  assert.deepEqual([neu.geschaetztes_lv.positionen[0].gp_von, neu.geschaetztes_lv.positionen[0].gp_bis], [95, 105]);
  assert.equal(neu.zusammenfassung.schaetzung_von, neu.geschaetztes_lv.summe_netto_von);
  assert.equal(bericht.kalkulation.positionen[0].ep, 8, "original report is not mutated");
});
