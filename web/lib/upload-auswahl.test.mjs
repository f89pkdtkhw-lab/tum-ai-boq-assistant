// Run: node --test web/lib/upload-auswahl.test.mjs  (Node >= 23 strips the TypeScript types of upload-auswahl.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { ladeAuswahl, leereAuswahl, merkeAuswahl } from "./upload-auswahl.ts";

const lv = new File(["{}"], "lv.json");
const preise = new File(["a;b"], "preise.csv");

test("the selection with its roles survives until it is cleared", () => {
  leereAuswahl();
  assert.deepEqual(ladeAuswahl(), []);
  merkeAuswahl([{ datei: lv, rolle: "lv" }, { datei: preise, rolle: "preise" }]);
  const wieder = ladeAuswahl();
  assert.equal(wieder.length, 2);
  assert.equal(wieder[0].datei, lv);
  assert.deepEqual(wieder.map((d) => d.rolle), ["lv", "preise"]);
  leereAuswahl();
  assert.deepEqual(ladeAuswahl(), []);
});

test("removing a file stores the shorter list; callers get copies", () => {
  merkeAuswahl([{ datei: lv, rolle: "lv" }, { datei: preise, rolle: "preise" }]);
  merkeAuswahl(ladeAuswahl().filter((d) => d.rolle !== "preise"));
  const liste = ladeAuswahl();
  assert.deepEqual(liste.map((d) => d.datei.name), ["lv.json"]);
  liste[0].rolle = "regel";
  assert.equal(ladeAuswahl()[0].rolle, "lv");
  leereAuswahl();
});
