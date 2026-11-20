// Run: node --test web/lib/suche.test.mjs  (Node >= 23 strips the TypeScript types of suche.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { filtereFindings, positionTrifft } from "./suche.ts";

const p = (oz, kurztext = "", langtext = "") =>
  ({ oz, kurztext, langtext, menge: 1, einheit: "m", ep: null, gp: null, typ: "normal", titel_pfad: [] });
const f = (id, oz, schwere = "mittel", titel = "", begruendung = "") =>
  ({ id, oz, kategorie: "fehler", schwere, titel, begruendung, vorschlag: "", quelle: "regel", regel_id: "R", euro_wirkung: null });

test("OZ matches as prefix only", () => {
  assert.equal(positionTrifft(p("01.02.0030"), "01.02"), true);
  assert.equal(positionTrifft(p("01.02.0030"), " 01.02.0030 "), true);
  assert.equal(positionTrifft(p("01.02.0030"), "02.0030"), false);
  assert.equal(positionTrifft(p("01.02.0030"), ""), true);
});

test("text matches ignore case and umlaut encoding, long text included", () => {
  assert.equal(positionTrifft(p("1", "Bodenaushub ÜBERSCHUSS"), "überschuss"), true);
  assert.equal(positionTrifft(p("1", "Übergabe"), "Übergabe".toLowerCase()), true);
  assert.equal(positionTrifft(p("1", "Mauerwerk", "inkl. Schalung für Stürze"), "STÜRZE"), true);
  assert.equal(positionTrifft(p("1", "Mauerwerk"), "beton"), false);
});

test("findings match by OZ, title, explanation or item text, combined with severity", () => {
  const positionen = [p("01.01", "Beton C25/30"), p("02.01", "Mauerwerk")];
  const findings = [
    f("a", "01.01", "kritisch"),
    f("b", "01.01", "niedrig"),
    f("c", "02.01", "kritisch", "Menge fehlt"),
    f("d", "02.01", "kritisch", "", "Einheitspreis für Beton auffällig"),
  ];
  const ids = (suche, schwere = null) =>
    filtereFindings(findings, positionen, { suche, kategorie: null, schwere }).map((x) => x.id);
  assert.deepEqual(ids("beton"), ["a", "b", "d"]);
  assert.deepEqual(ids("beton", "kritisch"), ["a", "d"]);
  assert.deepEqual(ids("02"), ["c", "d"]);
  assert.deepEqual(ids("MENGE"), ["c"]);
  assert.deepEqual(ids("", "niedrig"), ["b"]);
});
