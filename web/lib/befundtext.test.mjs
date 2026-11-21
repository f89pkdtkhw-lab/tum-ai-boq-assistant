// Run: node --test web/lib/befundtext.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { befundAnzeige } from "./befundtext.ts";

const f = (titel, begruendung, vorschlag) => ({ id: "x", oz: "1", kategorie: "fehler", schwere: "hoch", titel, begruendung, vorschlag, quelle: "regel", regel_id: "R", euro_wirkung: null });

test("German texts keep numbers and names; the ranking tail is dropped in both languages", () => {
  const a = f("Arithmetic error in total price", "11 × 20 = 220, supplied total price 999.", "Correct the total price to quantity × unit price.");
  assert.deepEqual([befundAnzeige(a, "de").titel, befundAnzeige(a, "de").begruendung, befundAnzeige(a, "de").vorschlag],
    ["Rechenfehler im Gesamtpreis", "11 × 20 = 220, angegebener Gesamtpreis 999.", "Gesamtpreis auf Menge × Einheitspreis korrigieren."]);
  const r = f("Optional work", "OZ 1: The item is explicitly optional (bedarf). Scope or quantity needs clarification; this does not establish an entitlement to additional payment. Priority view: rank 1/453. Order: x.",
    "OZ 1: Under which conditions will this optional work be instructed, and what quantity is expected?");
  assert.equal(befundAnzeige(r, "en").begruendung.includes("Priority view"), false);
  assert.equal(befundAnzeige(r, "de").begruendung, "OZ 1: Die Position ist ausdrücklich als Bedarfsposition ausgeschrieben. Umfang oder Menge sind zu klären; daraus folgt kein Anspruch auf Mehrvergütung.");
  assert.equal(befundAnzeige(r, "de").titel, "Bedarfsleistung");
  const s = f("Unusual layer area for floor slab", "381,07 m² deviates -35% from the median 589,79 m² of the floor slab layers in section “Haus A” (OZ 1).", "x");
  assert.equal(befundAnzeige(s, "de").titel, "Ungewöhnliche Schichtfläche: Bodenplatte");
  assert.equal(befundAnzeige(s, "de").begruendung, "381,07 m² weicht -35% vom Median 589,79 m² der Schichten „Bodenplatte“ im Abschnitt “Haus A” ab (OZ 1).");
});

test("norm check texts are translated, sources kept", () => {
  const n = f("Withdrawn standard referenced: DIN 1053-1", "The item refers to DIN 1053-1; the norm register lists it as withdrawn. Register: DIN 1053-1 is replaced by DIN EN 1996. Source: norm register entry DIN 1053-1, https://x.de (retrieved 2026-11-21).",
    "OZ 1: The item refers to DIN 1053-1 (withdrawn). Does DIN EN 1996 apply instead? Please confirm.");
  const d = befundAnzeige(n, "de");
  assert.equal(d.titel, "Zurückgezogene Norm zitiert: DIN 1053-1");
  assert.equal(d.vorschlag, "OZ 1: Die Position verweist auf DIN 1053-1 (zurückgezogen). Gilt stattdessen DIN EN 1996? Bitte bestätigen.");
  assert.equal(d.begruendung, "Die Position verweist auf DIN 1053-1; das Normregister führt sie als zurückgezogen. Register: DIN 1053-1 wird ersetzt durch DIN EN 1996. Quelle: Normregister-Eintrag DIN 1053-1, https://x.de (abgerufen 2026-11-21).");
});
