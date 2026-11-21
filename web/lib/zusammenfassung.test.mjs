// Run: node --test web/lib/zusammenfassung.test.mjs  (Node >= 23 strips the TypeScript types of zusammenfassung.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { abweichungText, inGruppe, punkteText, scoreText, uebersicht } from "./zusammenfassung.ts";

let n = 0;
const f = (schwere) => ({ id: `f${n++}`, oz: "01", kategorie: "fehler", schwere, titel: "", begruendung: "", vorschlag: "", quelle: "regel", regel_id: "R", euro_wirkung: null });
const findings = [f("kritisch"), f("hoch"), f("mittel"), f("mittel"), f("niedrig")];
const eur = (x) => `€${x.toFixed(2)}`;

test("fallback without zusammenfassung counts by the shared severity mapping", () => {
  const u = uebersicht({ findings });
  assert.deepEqual(u, { score: null, abzuege: [], abweichung: null, grosseProbleme: 2, warnungen: 2, hinweise: 1, empfehlungen: null, fallback: true });
  assert.deepEqual(uebersicht({ findings: [] }).grosseProbleme, 0);
});

test("backend summary wins over browser counts", () => {
  const z = { score: 8.5, score_abzuege: [{ grund: "Report 1: 2 big problems", punkte: -1, bericht: "regelwerk" }],
    schaetzung_abweichung_eur: 1200, grosse_probleme: 7, warnungen: 0, hinweise: 3, empfehlungen: 4 };
  const u = uebersicht({ findings, zusammenfassung: z });
  assert.equal(u.fallback, false);
  assert.deepEqual([u.score, u.grosseProbleme, u.empfehlungen, u.abweichung, u.abzuege.length], [8.5, 7, 4, 1200, 1]);
});

test("groups filter findings", () => {
  assert.equal(findings.filter((x) => inGruppe(x, "gross")).length, 2);
  assert.equal(findings.filter((x) => inGruppe(x, "warnung")).length, 2);
  assert.equal(findings.filter((x) => inGruppe(x, "hinweis")).length, 1);
  assert.equal(findings.filter((x) => inGruppe(x, null)).length, 5);
});

test("number formatting and null handling", () => {
  assert.equal(scoreText(8.5), "8.5 / 10");
  assert.equal(scoreText(10), "10.0 / 10");
  assert.equal(scoreText(0), "0.0 / 10");
  assert.equal(scoreText(null), "–");
  assert.equal(abweichungText(null, eur), "not connected");
  assert.equal(abweichungText(1200, eur), "+€1200.00");
  assert.equal(abweichungText(-80, eur), "−€80.00");
  assert.equal(abweichungText(0, eur), "±€0.00");
  assert.equal(punkteText(-1), "−1.0");
  assert.equal(punkteText(-0.1), "−0.1");
});
