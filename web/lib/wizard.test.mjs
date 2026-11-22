// Run: node --test web/lib/wizard.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  effektiverSchritt, ladeStufe, leseSchritt, liveFortschritt, maxSchritt, rechercheZumBefund, wizardAnzeigeSchritt, wizardPfad, wizardSichtbar, wizardUmleitung,
} from "./wizard.ts";

test("leseSchritt reads the query or infers from the path", () => {
  assert.equal(leseSchritt("preis", "/"), "preis");
  assert.equal(leseSchritt(null, "/marge"), "marge");
  assert.equal(leseSchritt("nope", "/export"), "export");
  assert.equal(leseSchritt(null, "/"), "hochladen");
});

test("wizardPfad and visibility", () => {
  assert.equal(wizardPfad("fehler"), "/?schritt=fehler");
  assert.equal(wizardPfad("marge"), "/marge?schritt=marge");
  assert.equal(wizardSichtbar("/"), true);
  assert.equal(wizardSichtbar("/einstellungen"), false);
});

test("maxSchritt and clamp", () => {
  assert.equal(maxSchritt({ hatBericht: false, laeuft: false }), "hochladen");
  assert.equal(maxSchritt({ hatBericht: false, laeuft: true }), "pruefen");
  assert.equal(maxSchritt({ hatBericht: true, laeuft: false }), "export");
  assert.equal(effektiverSchritt("export", { hatBericht: false, laeuft: false }), "hochladen");
  assert.equal(effektiverSchritt("export", { hatBericht: false, laeuft: false }, "marge"), "marge");
  assert.equal(effektiverSchritt("fehler", { hatBericht: true, laeuft: false }), "fehler");
});

test("ladeStufe maps the job to four plain-language stages", () => {
  assert.deepEqual(ladeStufe({ phase: "leer" }), { stufe: 1, aktiv: false });
  assert.deepEqual(ladeStufe({ phase: "laeuft", importFertig: false }), { stufe: 1, aktiv: true });
  assert.deepEqual(ladeStufe({ phase: "laeuft", importFertig: true }), { stufe: 2, aktiv: true });
  assert.deepEqual(ladeStufe({ phase: "laeuft", importFertig: true, standStatus: "laeuft" }), { stufe: 3, aktiv: true });
  assert.deepEqual(ladeStufe({ phase: "fertig" }), { stufe: 4, aktiv: false });
  assert.deepEqual(ladeStufe({ phase: "fehler", standStatus: "fehler" }), { stufe: 3, aktiv: false });
});

test("rechercheZumBefund prefers finding_id and falls back to the same OZ", () => {
  const finding = { id: "F1", oz: "01.001", kategorie: "fehler", schwere: "hoch", titel: "x", begruendung: "y", vorschlag: "z", quelle: "regel", regel_id: "R", euro_wirkung: null };
  const rows = [
    { schritt: "positionen", gruppe: "a", oz: "01.001", finding_id: "F1", einschaetzung: "bestaetigt", text: "direct", quellen: [{ url: "https://example.com", titel: "E" }], marktpreis_von: null, marktpreis_bis: null },
    { schritt: "preise", gruppe: "a", oz: "01.001", finding_id: null, einschaetzung: "zu_hoch", text: "price", quellen: [{ url: "https://example.com/p", titel: "P" }], marktpreis_von: 1, marktpreis_bis: 2 },
    { schritt: "positionen", gruppe: "b", oz: "02.001", finding_id: "F2", einschaetzung: "unklar", text: "other", quellen: [{ url: "https://example.com/o", titel: "O" }], marktpreis_von: null, marktpreis_bis: null },
  ];
  assert.equal(rechercheZumBefund(rows, finding)[0].text, "direct");
  assert.equal(rechercheZumBefund(rows, { ...finding, id: "missing" }).length, 1);
  assert.equal(rechercheZumBefund(rows, { ...finding, id: "missing" })[0].text, "price");
  assert.deepEqual(rechercheZumBefund([], finding), []);
});

test("wizardUmleitung clamps the URL, but waits while an evaluation link is being restored", () => {
  const q = (s) => new URLSearchParams(s);
  assert.equal(wizardUmleitung("pruefen", "pruefen", q("schritt=pruefen")), null);
  assert.equal(wizardUmleitung("preis", "hochladen", q("schritt=preis")), "/?schritt=hochladen");
  // Running evaluation chip: /?schritt=pruefen&eval=<id>&job=<id> before the page has reported its status.
  assert.equal(wizardUmleitung("pruefen", "hochladen", q("schritt=pruefen&eval=j1&job=j1")), null);
  assert.equal(wizardUmleitung("preis", "hochladen", q("schritt=preis&eval=lokal-3")), null);
});

test("liveFortschritt clamps step and percent for the review box", () => {
  assert.equal(liveFortschritt(null), null);
  assert.equal(liveFortschritt({ schritt: 3, schritte_gesamt: 0, prozent: 10 }), null);
  assert.deepEqual(liveFortschritt({ schritt: 3, schritte_gesamt: 8, prozent: 25 }), { schritt: 3, gesamt: 8, prozent: 25 });
  assert.deepEqual(liveFortschritt({ schritt: 0, schritte_gesamt: 8, prozent: -5 }), { schritt: 1, gesamt: 8, prozent: 0 });
  assert.deepEqual(liveFortschritt({ schritt: 99, schritte_gesamt: 8, prozent: 140.6 }), { schritt: 8, gesamt: 8, prozent: 100 });
});

test("wizardAnzeigeSchritt keeps the requested step while an evaluation link is restored", () => {
  const q = (s) => new URLSearchParams(s);
  const leer = { hatBericht: false, laeuft: false };
  // No evaluation link: clamp an unreachable step to the start page.
  assert.equal(wizardAnzeigeSchritt("preis", leer, undefined, q("schritt=preis")), "hochladen");
  // Chip / resume link: stay on the requested step so progress or a lost-job error is visible.
  assert.equal(wizardAnzeigeSchritt("pruefen", leer, undefined, q("schritt=pruefen&eval=j1&job=j1")), "pruefen");
  assert.equal(wizardAnzeigeSchritt("preis", leer, undefined, q("schritt=preis&eval=lokal-3")), "preis");
  // Once the report is there, the requested step is used as usual.
  assert.equal(wizardAnzeigeSchritt("preis", { hatBericht: true, laeuft: false }, undefined, q("schritt=preis")), "preis");
});
