// Run: node --test web/lib/einschaetzung.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { einschaetzen, gewerkVon, grundVorlage } from "./einschaetzung.ts";

const pos = (oz, kurztext, menge, ep, gp, typ = "normal") => ({ oz, kurztext, menge, ep, gp, typ, einheit: "m²", langtext: "", titel_pfad: [] });
const f = (oz, schwere, regel_id = "R", extra = {}) => ({ id: oz + regel_id, oz, schwere, regel_id, euro_wirkung: null, ...extra });
const bericht = (positionen, findings) => ({ lv: { name: "LV", quelle: "s", positionen, summen: {} }, findings, kennzahlen: {} });

test("clean BoQ is green with a go recommendation", () => {
  const e = einschaetzen(bericht([pos("1", "Erdarbeiten A", 10, 10, 100), pos("2", "Betonarbeiten B", 5, 20, 100)], []), null);
  assert.equal(e.ampel, "gruen");
  assert.equal(e.score, 10);
  assert.equal(e.punkte, 100);
  assert.deepEqual(e.positionen, { rot: 0, gelb: 0, gruen: 2 });
  assert.equal(e.kosten.angegeben, 200);
  assert.equal(e.kosten.nachgerechnet, 200);
  assert.equal(e.kosten.historie, null);
  assert.match(e.empfehlungen[0].text, /No blocking issues/);
});

test("Balanced: graduated real errors, browser Report 2 preview, softer lights", () => {
  const p = [pos("1", "Abdichtung X", 10, 10, 1000), pos("2", "Abdichtung Y", 10, 10, 100), pos("3", "Fenster Z", 1, 50, 50, "bedarf")];
  const e = einschaetzen(bericht(p, [f("1", "hoch", "RECHENFEHLER"), f("2", "kritisch"), f("3", "mittel", "MOCK_LLM")]),
    [{ trade: "Abdichtung", projects: 3, withActual: 3, avgDeviation: 30 }], { auffaellig: 2, verglichen: 3, rot: 1 }, "ausgewogen");
  assert.deepEqual(e.positionen, { rot: 2, gelb: 0, gruen: 1 }); // mock finding ignored
  // findings: hoch error −1 + kritisch error −2 = −3 → 7.0; prices: 1 outlier −1; too wide: 2 items + 1 outlier −0.3
  assert.equal(e.score, 5.7);
  assert.equal(e.punkte, 57);
  assert.equal(e.ampel, "gelb");
  assert.equal(e.offiziell, false);
  assert.equal(e.zaehler.grosseProbleme, 3);
  assert.equal(e.zaehler.warnungen, 1);
  assert.equal(e.kosten.nachgerechnet, 200);
  assert.equal(e.kosten.historie, 260);
  assert.deepEqual(e.schaetzung, { mitte: 255, plusMinus: 55 });
  assert.ok(e.empfehlungen.some((x) => x.text.startsWith("Correct {n} price errors") && x.werte.n === 1 && x.werte.euro === 900));
  assert.equal(e.faktoren[0].wert, "−3");
  assert.equal(e.faktoren.at(-1).name, "Notices and what-if cases (no penalty)");
});

test("Strict keeps the flat per-report deduction and the old traffic light", () => {
  const p = [pos("1", "Abdichtung X", 10, 10, 1000), pos("2", "Abdichtung Y", 10, 10, 100)];
  const e = einschaetzen(bericht(p, [f("1", "hoch", "RECHENFEHLER"), f("2", "kritisch")]),
    [{ trade: "Abdichtung", projects: 3, withActual: 3, avgDeviation: 30 }], { auffaellig: 2, verglichen: 3, rot: 1 }, "streng");
  // rules have a critical finding → −4; prices: 1 outlier → −1; too wide: 2 + 1 → −0.3
  assert.equal(e.score, 4.7);
  assert.equal(e.ampel, "rot");
  assert.equal(e.faktoren.at(-1).name, "Warnings and what-if cases (no penalty)");
});

test("LV15-like BoQ: all five models", () => {
  const p = [pos("1.1.10", "Bauleitung", 1, 10, 10), pos("1.1.20", "Sonstiges", 1, 10, 10)];
  const findings = [f("1.1.10", "hoch", "KI", { kategorie: "risiko", quelle: "modell" })];
  const erwartet = { streng: [6.5, "gelb"], gestaffelt: [9, "gruen"], anteil: [5, "gelb"], fehler_klaerung: [9.5, "gruen"], ausgewogen: [9.5, "gruen"] };
  for (const [modell, [score, ampel]] of Object.entries(erwartet)) {
    const e = einschaetzen(bericht(p, findings), null, null, modell);
    assert.equal(e.score, score, modell);
    assert.equal(e.ampel, ampel, modell);
  }
});

test("trade key matches the history grouping", () => {
  assert.equal(gewerkVon("Betonarbeiten Bodenplatte C25/30"), "Betonarbeiten");
  assert.equal(gewerkVon("WC"), null);
});

test("backend summary is the official score; the browser adds Report 2 only until the backend sends it", () => {
  const p = [pos("1", "Abdichtung X", 10, 10, 1000), pos("2", "Abdichtung Y", 10, 10, 100)];
  const z = (abzuege, modell) => ({ score: 10 - abzuege.reduce((s, a) => s - a.punkte, 0), score_abzuege: abzuege, schaetzung_abweichung_eur: null,
    grosse_probleme: 1, warnungen: 0, hinweise: 0, empfehlungen: 2, bewertungsmodell: modell });
  const r1 = [{ grund: "Report 1: 1 big problem (−0.5)", punkte: -0.5, bericht: "regelwerk" }];
  const ohneR2 = einschaetzen({ ...bericht(p, [f("1", "hoch", "RECHENFEHLER")]), zusammenfassung: z(r1, "ausgewogen") }, null, { auffaellig: 1, verglichen: 2, rot: 1 }, "ausgewogen");
  assert.equal(ohneR2.offiziell, true);
  assert.equal(ohneR2.score, 8.4);         // backend 9.5, browser Report 2: −1 for the outlier, −0.1 as too-wide estimate
  assert.equal(ohneR2.faktoren[0].name, "Report {r}: {n} big problems (−{p})");
  assert.deepEqual(ohneR2.faktoren[0].werte, { r: "1", n: "1", p: "0.5" });
  const mitR2 = einschaetzen({ ...bericht(p, [f("1", "hoch", "RECHENFEHLER")]),
    zusammenfassung: z([...r1, { grund: "Report 2: 1 approximation too big", punkte: -0.1, bericht: "vergleich" }], "ausgewogen") }, null, { auffaellig: 1, verglichen: 2, rot: 1 }, "ausgewogen");
  assert.equal(mitR2.score, 9.4);          // backend only, no browser preview
  assert.equal(mitR2.urteil, "Looks good – ready to price");
  assert.equal(mitR2.zaehler.empfehlungen >= 2, true);
});

test("changing the model ignores a backend summary computed under a different model", () => {
  const p = [pos("1.1.10", "Bauleitung", 1, 10, 10), pos("1.1.20", "Sonstiges", 1, 10, 10)];
  const findings = [f("1.1.10", "hoch", "KI", { kategorie: "risiko", quelle: "modell" })];
  const z = { score: 6.5, score_abzuege: [{ grund: "Report 1: 1 big problem (−3.5)", punkte: -3.5, bericht: "regelwerk" }],
    schaetzung_abweichung_eur: null, grosse_probleme: 1, warnungen: 0, hinweise: 0, empfehlungen: 0, bewertungsmodell: "streng" };
  const e = einschaetzen({ ...bericht(p, findings), zusammenfassung: z }, null, null, "ausgewogen");
  assert.equal(e.offiziell, false);
  assert.equal(e.score, 9.5);
  assert.equal(e.ampel, "gruen");
});

test("grundVorlage keeps old and new reason texts translatable", () => {
  assert.deepEqual(grundVorlage("Report 1: 1 big problem"), { name: "Report {r}: {n} big problems", werte: { r: "1", n: "1" } });
  assert.deepEqual(grundVorlage("Report 1: 5 big problems (critical or 5+)"), { name: "Report {r}: {n} big problems (critical or 5+)", werte: { r: "1", n: "5" } });
  assert.deepEqual(grundVorlage("Report 1: 1 big problem (−0.5)"), { name: "Report {r}: {n} big problems (−{p})", werte: { r: "1", n: "1", p: "0.5" } });
  assert.deepEqual(grundVorlage("Report 1: 2 big problems, 1 warning (−2.2)"), { name: "Report {r}: {n} big problems, {w} warnings (−{p})", werte: { r: "1", n: "2", w: "1", p: "2.2" } });
  assert.deepEqual(grundVorlage("Share of affected items: 50 % (−5.0)"), { name: "Share of affected items: {pct} % (−{p})", werte: { pct: "50", p: "5.0" } });
  assert.deepEqual(grundVorlage("Report 2: 3 approximation(s) too big"), { name: "Report 2: {n} approximations too big", werte: { n: "3" } });
});
