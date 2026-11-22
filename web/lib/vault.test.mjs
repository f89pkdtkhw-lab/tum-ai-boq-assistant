// Run: node --test web/lib/vault.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { besitzerKopf, defaultWettbewerb, filtereVault, groesseText, gruppiereNachLv, rolleFuerTyp, setzeBesitzer, sollStandardMargeLaden, tabAusQuery, tagsAusText } from "./vault.ts";

const e = (id, typ, am, extra = {}) => ({ id, typ, dateiname: `${id}.json`, groesse: 1, hash: id, hochgeladen_am: am, tags: [], projekt: null,
  besitzer: null, quelle: "analyse", lv_schluessel: null, lv_name: null, version: null, ...extra });

test("tab from the query falls back to bills; old routes map to real tabs", () => {
  assert.equal(tabAusQuery("preisdatenbank"), "preisdatenbank");
  assert.equal(tabAusQuery("historie"), "historie");
  assert.equal(tabAusQuery("einreichen"), "einreichen");
  assert.equal(tabAusQuery("wettbewerb"), "wettbewerb");
  assert.equal(tabAusQuery("quatsch"), "lvs");
  assert.equal(tabAusQuery(null), "lvs");
});

test("wizard roles only for uploaded document types", () => {
  assert.equal(rolleFuerTyp("lv"), "lv");
  assert.equal(rolleFuerTyp("regelwerk"), "regel");
  assert.equal(rolleFuerTyp("preisliste"), "preise");
  assert.equal(rolleFuerTyp("bericht"), null);
  assert.equal(rolleFuerTyp("wettbewerb"), null);
});

test("results are grouped per bill, versions newest first, groups by latest run", () => {
  const g = gruppiereNachLv([
    e("a1", "bericht", "2026-11-22T06:00:00+00:00", { lv_schluessel: "A", lv_name: "LV A" }),
    e("b1", "bericht", "2026-11-22T05:00:00+00:00", { lv_schluessel: "B", lv_name: "LV B" }),
    e("a2", "recherche", "2026-11-22T07:00:00+00:00", { lv_schluessel: "A", lv_name: "LV A" }),
    e("x", "auswertung", "2026-11-21T07:00:00+00:00", { lv_name: "LV C" }),
  ]);
  assert.deepEqual(g.map((x) => x.name), ["LV A", "LV B", "LV C"]);
  assert.deepEqual(g[0].eintraege.map((x) => x.id), ["a2", "a1"]);
});

test("search, tags, size and owner header", () => {
  const liste = [e("1", "lv", "x", { lv_name: "Schule Nord", tags: ["rohbau"] }), e("2", "lv", "x", { projekt: "Kita" })];
  assert.deepEqual(filtereVault(liste, "ROHBAU").map((x) => x.id), ["1"]);
  assert.deepEqual(filtereVault(liste, "kita").map((x) => x.id), ["2"]);
  assert.equal(filtereVault(liste, " ").length, 2);
  assert.deepEqual(tagsAusText("a, b , ,a"), ["a", "b"]);
  assert.equal(groesseText(2048), "2.0 KB");
  setzeBesitzer(null);
  assert.deepEqual(besitzerKopf(), {});
  setzeBesitzer("s@x.de");
  assert.deepEqual(besitzerKopf(), { "X-LV-Scout-User": "s@x.de" });
});


test("default competitor file is the seeded demo, then a file named margin-demo.xlsx", () => {
  assert.equal(defaultWettbewerb([]), null);
  const pdf = e("p", "wettbewerb", "2026-11-22T08:00:00+00:00", { dateiname: "margin-demo.pdf", quelle: "ki" });
  const upload = e("u", "wettbewerb", "2026-11-22T09:00:00+00:00", { dateiname: "andere.xlsx", quelle: "upload" });
  const named = e("n", "wettbewerb", "2026-11-22T10:00:00+00:00", { dateiname: "margin-demo.xlsx", quelle: "upload" });
  const seeded = e("s", "wettbewerb", "2026-11-22T07:00:00+00:00", { dateiname: "margin-demo.xlsx", quelle: "default" });
  assert.equal(defaultWettbewerb([pdf, upload]), null);
  assert.equal(defaultWettbewerb([pdf, upload, named])?.id, "n");
  assert.equal(defaultWettbewerb([named, seeded, upload])?.id, "s");
});

test("the margin page auto-loads the demo only when no other competitor Excel is in the vault", () => {
  const pdf = e("p", "wettbewerb", "2026-11-22T08:00:00+00:00", { dateiname: "angebot.pdf", quelle: "ki" });
  const upload = e("u", "wettbewerb", "2026-11-22T09:00:00+00:00", { dateiname: "andere.xlsx", quelle: "upload" });
  const seeded = e("s", "wettbewerb", "2026-11-22T07:00:00+00:00", { dateiname: "margin-demo.xlsx", quelle: "default" });
  assert.equal(sollStandardMargeLaden([]), "fallback");
  assert.equal(sollStandardMargeLaden([pdf]), "fallback");
  assert.equal(sollStandardMargeLaden([seeded, pdf])?.id, "s");
  assert.equal(sollStandardMargeLaden([seeded, upload]), null);
  assert.equal(sollStandardMargeLaden([upload]), null);
});
