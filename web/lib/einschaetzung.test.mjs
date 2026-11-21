// Run: node --test web/lib/einschaetzung.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { einschaetzen, gewerkVon } from "./einschaetzung.ts";

const pos = (oz, kurztext, menge, ep, gp, typ = "normal") => ({ oz, kurztext, menge, ep, gp, typ, einheit: "m²", langtext: "", titel_pfad: [] });
const f = (oz, schwere, regel_id = "R") => ({ id: oz + regel_id, oz, schwere, regel_id, euro_wirkung: null });
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

test("team score: big rule problems cost 3.5–4 points, wide estimates 0.1 each, recommendations nothing", () => {
  const p = [pos("1", "Abdichtung X", 10, 10, 1000), pos("2", "Abdichtung Y", 10, 10, 100), pos("3", "Fenster Z", 1, 50, 50, "bedarf")];
  const e = einschaetzen(bericht(p, [f("1", "hoch", "RECHENFEHLER"), f("2", "kritisch"), f("3", "mittel", "MOCK_LLM")]),
    [{ trade: "Abdichtung", projects: 3, withActual: 3, avgDeviation: 30 }], { auffaellig: 2, verglichen: 3, rot: 1 });
  assert.deepEqual(e.positionen, { rot: 2, gelb: 0, gruen: 1 }); // mock finding ignored
  // like bewertung.py: rules have a critical finding → −4; prices: 1 outlier → −1; too wide: 2 items (>25 %) + 1 outlier → −0.3
  assert.equal(e.score, 4.7);
  assert.equal(e.punkte, 47);
  assert.equal(e.ampel, "rot");
  assert.equal(e.offiziell, false);
  assert.equal(e.zaehler.grosseProbleme, 3);
  assert.equal(e.zaehler.warnungen, 1);
  assert.equal(e.kosten.nachgerechnet, 200);
  assert.equal(e.kosten.historie, 260);
  assert.deepEqual(e.schaetzung, { mitte: 255, plusMinus: 55 }); // 200 … 260 + 50 optional
  assert.ok(e.empfehlungen.some((x) => x.text.startsWith("Correct {n} price errors") && x.werte.n === 1 && x.werte.euro === 900));
  assert.equal(e.faktoren[0].wert, "−4");
});

test("trade key matches the history grouping", () => {
  assert.equal(gewerkVon("Betonarbeiten Bodenplatte C25/30"), "Betonarbeiten");
  assert.equal(gewerkVon("WC"), null);
});

test("backend summary is the official score; the browser adds Report 2 only until the backend sends it", () => {
  const p = [pos("1", "Abdichtung X", 10, 10, 1000), pos("2", "Abdichtung Y", 10, 10, 100)];
  const z = (abzuege) => ({ score: 10 - abzuege.reduce((s, a) => s - a.punkte, 0), score_abzuege: abzuege, schaetzung_abweichung_eur: null,
    grosse_probleme: 1, warnungen: 0, hinweise: 0, empfehlungen: 2 });
  const r1 = [{ grund: "Report 1: 1 big problem", punkte: -3.5, bericht: "regelwerk" }];
  const ohneR2 = einschaetzen({ ...bericht(p, [f("1", "hoch", "RECHENFEHLER")]), zusammenfassung: z(r1) }, null, { auffaellig: 1, verglichen: 2, rot: 1 });
  assert.equal(ohneR2.offiziell, true);
  assert.equal(ohneR2.score, 5.4);         // backend 6.5, browser Report 2: −1 for the outlier, −0.1 as too-wide estimate
  assert.equal(ohneR2.faktoren[0].name, "Report {r}: {n} big problems");
  assert.deepEqual(ohneR2.faktoren[0].werte, { r: "1", n: "1" });
  const mitR2 = einschaetzen({ ...bericht(p, [f("1", "hoch", "RECHENFEHLER")]),
    zusammenfassung: z([...r1, { grund: "Report 2: 1 approximation too big", punkte: -0.1, bericht: "vergleich" }]) }, null, { auffaellig: 1, verglichen: 2, rot: 1 });
  assert.equal(mitR2.score, 6.4);          // backend only, no browser preview
  assert.equal(mitR2.urteil, "High risk – do not bid as is");
  assert.equal(mitR2.zaehler.empfehlungen >= 2, true);
});
