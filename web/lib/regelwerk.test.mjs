// Run: node --test web/lib/regelwerk.test.mjs  (Node >= 23 strips the TypeScript types of regelwerk.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { analyseAnfrage, beilageFehler, importFehlerText, REGELWERK_FORMATE, regelwerkText, routeFehlt } from "./regelwerk.ts";

const lv = { name: "Synthetic", quelle: "test", positionen: [], summen: {} };
const r = { id: "r1", dateiname: "spec.txt", warnungen: [], normverweise: [{ norm_id: "DIN 1045-2", ausgabe: null, fundstelle: "x" }],
  kennwerte: [{ norm: null, kennwert: "a", wert: "1", einheit: null, fundstelle: "x" }, { norm: null, kennwert: "b", wert: "2", einheit: null, fundstelle: "x" }] };
const p = { id: "p1", dateiname: "prices.csv", waehrung: "EUR", warnungen: [], eintraege: [] };

test("request building: always /api/lv/analyse, also for a bill without attachments (#167)", () => {
  assert.deepEqual(analyseAnfrage(lv, null, null), { lv, regelwerk: null, preisliste: null, bewertungsmodell: "ausgewogen" });
  assert.deepEqual(analyseAnfrage(lv, r, null), { lv, regelwerk: r, preisliste: null, bewertungsmodell: "ausgewogen" });
  assert.deepEqual(analyseAnfrage(lv, null, p), { lv, regelwerk: null, preisliste: p, bewertungsmodell: "ausgewogen" });
  assert.deepEqual(analyseAnfrage(lv, r, p), { lv, regelwerk: r, preisliste: p, bewertungsmodell: "ausgewogen" });
});

test("fallback decision: only HTTP 404 means the route is missing", () => {
  assert.equal(routeFehlt(Object.assign(new Error("Not Found"), { status: 404 })), true);
  assert.equal(routeFehlt(Object.assign(new Error("bad"), { status: 422 })), false);
  assert.equal(routeFehlt(new TypeError("fetch failed")), false);
  assert.equal(routeFehlt(null), false);
});

test("local checks and error texts name the file", () => {
  assert.equal(beilageFehler({ name: "spec.PDF", size: 10 }, REGELWERK_FORMATE, "Regulation document"), null);
  assert.match(beilageFehler({ name: "spec.docx", size: 10 }, REGELWERK_FORMATE, "Regulation document"), /“spec.docx” has an unsupported format. Allowed: PDF, TXT, MD/);
  assert.match(beilageFehler({ name: "a.txt", size: 0 }, REGELWERK_FORMATE, "Regulation document"), /empty/);
  assert.match(beilageFehler({ name: "a.txt", size: 11 * 1024 * 1024 }, REGELWERK_FORMATE, "Regulation document"), /10 MiB/);
  assert.equal(importFehlerText("Price list", "p.csv", new Error("Row 3: unit missing")), "Price list “p.csv” could not be imported: Row 3: unit missing");
  assert.match(importFehlerText("Price list", "p.csv", new TypeError("x")), /Cannot connect/);
});

test("summary shows references and key values", () => {
  assert.equal(regelwerkText(r), "spec.txt: 1 reference, 2 key values");
  assert.equal(regelwerkText({ ...r, warnungen: ["w"] }), "spec.txt: 1 reference, 2 key values, 1 warning");
});
