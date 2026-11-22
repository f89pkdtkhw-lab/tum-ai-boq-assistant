// Run: node --test web/lib/bewertungsmodell.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ampelVonScore, DEFAULT_MODELL, findingsAbzuege, groessenFaktor, istBewertungsmodell,
  MODELLE, MODELL_INFO, scoreAusAbzuegen, zusammenfassenLokal,
} from "./bewertungsmodell.ts";

const lv15 = [{ oz: "1.1.10", schwere: "hoch", kategorie: "risiko", quelle: "modell", regel_id: "KI" }];

test("default model is Balanced and all five ids are known", () => {
  assert.equal(DEFAULT_MODELL, "ausgewogen");
  assert.deepEqual([...MODELLE], ["streng", "gestaffelt", "anteil", "fehler_klaerung", "ausgewogen"]);
  for (const id of MODELLE) {
    assert.equal(istBewertungsmodell(id), true);
    assert.ok(MODELL_INFO[id].name && MODELL_INFO[id].text && MODELL_INFO[id].beispiel);
  }
  assert.equal(istBewertungsmodell("nope"), false);
});

test("LV15 (2 items, 1 high AI finding) for all five models", () => {
  const erwartet = {
    streng: { score: 6.5, ampel: "gelb", punkte: -3.5 },
    gestaffelt: { score: 9.0, ampel: "gruen", punkte: -1.0 },
    anteil: { score: 5.0, ampel: "gelb", punkte: -5.0 },
    fehler_klaerung: { score: 9.5, ampel: "gruen", punkte: -0.5 },
    ausgewogen: { score: 9.5, ampel: "gruen", punkte: -0.5 },
  };
  for (const [modell, z] of Object.entries(erwartet)) {
    const aus = zusammenfassenLokal(lv15, 2, modell);
    assert.equal(aus.score, z.score, modell);
    assert.equal(ampelVonScore(aus.score, modell), z.ampel, modell);
    assert.equal(aus.score_abzuege[0].punkte, z.punkte, modell);
    assert.equal(aus.bewertungsmodell, modell);
  }
  assert.match(zusammenfassenLokal(lv15, 2, "ausgewogen").score_abzuege[0].grund, /Report 1: 1 big problem \(−0\.5\)/);
  assert.match(zusammenfassenLokal(lv15, 2, "anteil").score_abzuege[0].grund, /Share of affected items: 50 % \(−5\.0\)/);
});

test("size factor leaves small BoQs unchanged and shrinks large ones", () => {
  assert.equal(groessenFaktor(2), 1);
  assert.equal(groessenFaktor(20), 1);
  assert.ok(Math.abs(groessenFaktor(80) - Math.sqrt(20 / 80)) < 1e-12);
});

test("Balanced caps finding deductions at 6 and scales large BoQs", () => {
  const viele = Array.from({ length: 40 }, (_, i) => ({ oz: `01.${i}`, schwere: "hoch", kategorie: "fehler", quelle: "regel", regel_id: "RECHENFEHLER" }));
  assert.equal(zusammenfassenLokal(viele, 20, "ausgewogen").score, 4.0); // 40 × 1, cap 6
  const gross = zusammenfassenLokal(viele, 80, "ausgewogen");
  // 40 × 1 × sqrt(20/80) = 20, cap 6 → 4.0
  assert.equal(gross.score, 4.0);
  const wenige = zusammenfassenLokal(viele.slice(0, 5), 80, "ausgewogen");
  // 5 × sqrt(20/80) = 2.5 → 7.5 green (on the line)
  assert.equal(wenige.score, 7.5);
  assert.equal(ampelVonScore(7.5, "ausgewogen"), "gruen");
});

test("warnings deduct in graduated models, notices never do", () => {
  const f = (schwere, kategorie = "fehler") => ({ oz: "1", schwere, kategorie, quelle: "regel", regel_id: "R" });
  assert.equal(zusammenfassenLokal([f("niedrig"), f("niedrig")], 2, "gestaffelt").score, 10);
  assert.equal(zusammenfassenLokal([f("mittel")], 2, "gestaffelt").score, 9.8);
  assert.equal(zusammenfassenLokal([f("mittel", "nachtrag")], 2, "fehler_klaerung").score, 9.9);
  assert.equal(zusammenfassenLokal([f("mittel")], 2, "streng").score, 10);
});

test("Share uses the fraction of affected items, not the raw count", () => {
  const fuenf = Array.from({ length: 5 }, (_, i) => ({ oz: `0${i}`, schwere: "hoch", kategorie: "fehler", quelle: "regel", regel_id: "R" }));
  // 5 of 300 → 10 * 5/300 ≈ 0.1667 → 0.2
  assert.equal(zusammenfassenLokal(fuenf, 300, "anteil").score, 9.8);
  assert.equal(zusammenfassenLokal(fuenf, 5, "anteil").score, 4.0); // 100 % → cap 6
});

test("Strict still uses the flat per-report deduction and the old lights", () => {
  const f = (schwere) => ({ oz: "01", schwere, kategorie: "fehler", quelle: "regel", regel_id: "R" });
  assert.equal(zusammenfassenLokal([f("hoch")], 2, "streng").score, 6.5);
  assert.equal(ampelVonScore(6.5, "streng"), "gelb");
  assert.equal(ampelVonScore(8.5, "streng"), "gruen");
  assert.equal(zusammenfassenLokal([f("kritisch")], 2, "streng").score, 6.0);
  assert.equal(zusammenfassenLokal(Array.from({ length: 5 }, () => f("hoch")), 2, "streng").score, 6.0);
  assert.equal(ampelVonScore(5.0, "ausgewogen"), "gelb");
  assert.equal(ampelVonScore(4.9, "ausgewogen"), "rot");
});

test("findingsAbzuege and scoreAusAbzuegen stay consistent", () => {
  const ab = findingsAbzuege(lv15, 2, "ausgewogen");
  assert.equal(scoreAusAbzuegen(ab), 9.5);
  assert.equal(scoreAusAbzuegen([]), 10);
});
