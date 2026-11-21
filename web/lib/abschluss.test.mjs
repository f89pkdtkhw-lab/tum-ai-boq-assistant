// Run: node --test web/lib/abschluss.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { abschlussFehler, abschlussForm, pruefeAbschluss, tagListe, vergleich } = await import("./abschluss.ts");

const datei = (name, size = 10) => new File([new Uint8Array(size)], name);
const eingabe = (extra = {}) => ({ bericht: datei("our-report.json"), abrechnung: datei("final.x86"), beschreibung: "", tags: "", notiz: "", ...extra });

test("form validation per file", () => {
  assert.deepEqual(pruefeAbschluss(eingabe()), {});
  const leer = pruefeAbschluss(eingabe({ bericht: null, abrechnung: null }));
  assert.match(leer.bericht, /report or estimate/);
  assert.match(leer.abrechnung, /final bill/);
  assert.match(pruefeAbschluss(eingabe({ abrechnung: datei("final.docx") })).abrechnung, /“final.docx” has an unsupported format/);
  assert.match(pruefeAbschluss(eingabe({ bericht: datei("r.json", 0) })).bericht, /empty/);
});

test("request building: optional fields only when filled, tags cleaned", () => {
  assert.deepEqual(tagListe(" roof, timber ,, roof,"), ["roof", "timber"]);
  const ohne = abschlussForm(eingabe());
  assert.deepEqual([...ohne.keys()], ["bericht", "abrechnung"]);
  const mit = abschlussForm(eingabe({ beschreibung: " Synthetic house ", tags: "roof, timber", notiz: "Late delivery" }));
  assert.deepEqual([...mit.keys()], ["bericht", "abrechnung", "description", "tags", "note"]);
  assert.equal(mit.get("description"), "Synthetic house");
  assert.equal(mit.get("tags"), "roof,timber");
  assert.equal(mit.get("bericht").name, "our-report.json");
});

test("error display: 404 keeps manual entry, file-specific message passes through", () => {
  const e404 = abschlussFehler(Object.assign(new Error("Not Found"), { status: 404 }), eingabe());
  assert.equal(e404.routeFehlt, true);
  assert.match(e404.text, /manual entry/);
  const eDatei = abschlussFehler(Object.assign(new Error("final.x86: no items found"), { status: 422 }), eingabe());
  assert.deepEqual(eDatei, { text: "final.x86: no items found", routeFehlt: false });
  assert.match(abschlussFehler(new Error("bad"), eingabe()).text, /our-report.json \+ final.x86/);
});

test("record comparison counts matched and one-sided item numbers", () => {
  assert.deepEqual(vergleich({ expected_json: { "01": {}, "02": {} }, actual_json: { "02": {}, "03": {} } }), { beide: 1, nurSoll: 1, nurIst: 1 });
  assert.deepEqual(vergleich({ expected_json: { positionen: [{ oz: "01" }] }, actual_json: { positionen: [{ oz: "01" }] } }), { beide: 1, nurSoll: 0, nurIst: 0 });
});
