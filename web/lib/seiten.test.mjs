// Run: node --test web/lib/seiten.test.mjs  (Node >= 23 strips the TypeScript types of seiten.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aktuelleSeite, ausschnitt, begrenze, seiteFuer, seiteMitIndex, seiteNachGroesse, seitenAnzahl, seiteVon,
  SEITENGROESSEN, STANDARD_SEITENGROESSE, zeilenText,
} from "./seiten.ts";

test("defaults: 100 rows, selector 50/100/250", () => {
  assert.equal(STANDARD_SEITENGROESSE, 100);
  assert.deepEqual([...SEITENGROESSEN], [50, 100, 250]);
});

test("296 items at 100 rows give three pages", () => {
  assert.equal(seitenAnzahl(296, 100), 3);
  assert.deepEqual(seiteVon(296, 0, 100), { seite: 0, seiten: 3, von: 0, bis: 100, gesamt: 296 });
  assert.deepEqual(seiteVon(296, 2, 100), { seite: 2, seiten: 3, von: 200, bis: 296, gesamt: 296 });
  assert.equal(zeilenText(seiteVon(296, 2, 100)), "rows 201–296 of 296");
  assert.equal(seitenAnzahl(296, 250), 2);
  assert.equal(seitenAnzahl(296, 50), 6);
});

test("bounds: pages are clamped, exact multiples have no empty last page", () => {
  assert.equal(seitenAnzahl(200, 100), 2);
  assert.equal(begrenze(-3, 296, 100), 0);
  assert.equal(begrenze(99, 296, 100), 2);
  assert.equal(begrenze(1.7, 296, 100), 1);
  assert.equal(begrenze(Number.NaN, 296, 100), 0);
  assert.deepEqual(seiteVon(200, 5, 100), { seite: 1, seiten: 2, von: 100, bis: 200, gesamt: 200 });
  assert.deepEqual(seiteVon(1, 0, 100), { seite: 0, seiten: 1, von: 0, bis: 1, gesamt: 1 });
  // Invalid page sizes fall back to the default instead of dividing by zero.
  assert.equal(seitenAnzahl(296, 0), 3);
});

test("empty list: one empty page", () => {
  const seite = seiteVon(0, 4, 100);
  assert.deepEqual(seite, { seite: 0, seiten: 1, von: 0, bis: 0, gesamt: 0 });
  assert.deepEqual(ausschnitt([], seite), []);
  assert.equal(zeilenText(seite), "no rows");
  assert.equal(seiteFuer([], () => true, 100), null);
});

test("page containing a given index or row", () => {
  assert.equal(seiteMitIndex(0, 100), 0);
  assert.equal(seiteMitIndex(99, 100), 0);
  assert.equal(seiteMitIndex(100, 100), 1);
  assert.equal(seiteMitIndex(295, 100), 2);
  assert.equal(seiteMitIndex(-1, 100), 0);
  const liste = Array.from({ length: 296 }, (_, i) => ({ oz: `01.${i}` }));
  assert.equal(seiteFuer(liste, (p) => p.oz === "01.150", 100), 1);
  assert.equal(seiteFuer(liste, (p) => p.oz === "01.150", 50), 3);
  assert.equal(seiteFuer(liste, (p) => p.oz === "missing", 100), null);
});

test("reset: a changed filter key shows page 1, the same key keeps the page", () => {
  const blatt = { schluessel: "kategorie=fehler", seite: 2 };
  assert.equal(aktuelleSeite(blatt, "kategorie=fehler"), 2);
  assert.equal(aktuelleSeite(blatt, "kategorie=risiko"), 0);
  assert.equal(aktuelleSeite(blatt, ""), 0);
});

test("page size change keeps the first visible row on screen", () => {
  assert.equal(seiteNachGroesse(seiteVon(296, 2, 100), 50), 4);
  assert.equal(seiteNachGroesse(seiteVon(296, 2, 100), 250), 0);
  assert.equal(seiteNachGroesse(seiteVon(0, 0, 100), 250), 0);
});

test("9,000 synthetic positions: one pass to find a row, visible slice ≤ page size", () => {
  const n = 9000;
  const positionen = Array.from({ length: n }, (_, i) => ({ oz: `${String(Math.floor(i / 100)).padStart(2, "0")}.${i % 100}` }));

  // Finding the page of the last row calls the predicate at most n times (O(n), no nested scan).
  let aufrufe = 0;
  const seite = seiteFuer(positionen, (p) => { aufrufe += 1; return p.oz === "89.99"; }, 100);
  assert.equal(seite, 89);
  assert.ok(aufrufe <= n, `${aufrufe} predicate calls for ${n} rows`);

  // Slicing reads only the rows of the page, whatever the list length.
  for (const groesse of SEITENGROESSEN) {
    let gelesen = 0;
    const gezaehlt = new Proxy(positionen, {
      get(ziel, schluessel, empfaenger) {
        if (typeof schluessel === "string" && /^\d+$/.test(schluessel)) gelesen += 1;
        return Reflect.get(ziel, schluessel, empfaenger);
      },
    });
    for (const s of [0, 17, 10_000]) {
      gelesen = 0;
      const sichtbar = ausschnitt(gezaehlt, seiteVon(n, s, groesse));
      assert.ok(sichtbar.length <= groesse);
      assert.ok(gelesen <= groesse, `${gelesen} rows read for page size ${groesse}`);
    }
    assert.equal(seitenAnzahl(n, groesse), Math.ceil(n / groesse));
    const letzte = seiteVon(n, Infinity, groesse);
    assert.equal(letzte.bis, n);
    assert.equal(ausschnitt(positionen, letzte).at(-1).oz, "89.99");
  }
  assert.equal(zeilenText(seiteVon(n, 89, 100), (z) => z.toLocaleString("en-GB")), "rows 8,901–9,000 of 9,000");
});
