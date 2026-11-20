// Run: node --test web/lib/offline.test.mjs  (Node >= 23 strips the TypeScript types of offline.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bietetOffline, pruefeOfflineBericht } from "./offline.ts";

const snapshot = JSON.parse(readFileSync(new URL("../public/offline/beispiel-bericht.json", import.meta.url), "utf8"));

test("the committed snapshot is a review report whose findings cite existing items", () => {
  const bericht = pruefeOfflineBericht(snapshot);
  assert.ok(bericht.lv.positionen.length > 0);
  assert.ok(bericht.findings.length > 0);
  const oz = new Set(bericht.lv.positionen.map((p) => p.oz));
  for (const f of bericht.findings) assert.ok(oz.has(f.oz), f.oz);
  assert.equal(bericht.kennzahlen.positionen, bericht.lv.positionen.length);
});

test("a broken snapshot is rejected", () => {
  assert.throws(() => pruefeOfflineBericht({ lv: { positionen: [] }, findings: [], kennzahlen: {} }), /no items/);
  assert.throws(() => pruefeOfflineBericht(null), /no items/);
  const fremd = { ...snapshot, findings: [{ ...snapshot.findings[0], oz: "99.99" }] };
  assert.throws(() => pruefeOfflineBericht(fremd), /99\.99/);
});

test("the offer appears only for network errors, 5xx or an unreachable backend", () => {
  assert.equal(bietetOffline(new TypeError("Failed to fetch"), true), true);
  assert.equal(bietetOffline(new Error("Request failed (500). Please check the input."), true), true);
  assert.equal(bietetOffline(new Error("Request failed (502). Please check the input."), true), true);
  assert.equal(bietetOffline(new Error("anything"), false), true);
  assert.equal(bietetOffline(new Error("Request failed (422). Please check the input."), true), false);
  assert.equal(bietetOffline(new Error("The file is not a valid BoQ."), true), false);
});
