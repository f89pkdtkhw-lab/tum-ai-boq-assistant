// Run: node --test web/lib/marge-pdf.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { filtereVaultPdfs, istPdfName, margeVergleichHref, xlsxAusMargeAntwort } from "./marge-pdf.ts";

test("PDF names are detected case-insensitively; Excel and bare names are not", () => {
  assert.equal(istPdfName("angebot.pdf"), true);
  assert.equal(istPdfName("  Preisspiegel.PDF "), true);
  assert.equal(istPdfName("margin-demo.xlsx"), false);
  assert.equal(istPdfName("pdf"), false);
  assert.equal(istPdfName("angebot.pdf.xlsx"), false);
});

test("vault list keeps only PDF entries, newest stay in their original order", () => {
  const e = (id, dateiname) => ({ id, typ: "lv", dateiname, groesse: 1, hash: id, hochgeladen_am: "2026-11-22T08:00:00+00:00",
    tags: [], projekt: null, besitzer: null, quelle: "upload", lv_schluessel: null, lv_name: null, version: null });
  const liste = [e("a", "lv.xlsx"), e("b", "angebot.pdf"), e("c", "Regel.PDF"), e("d", "notiz.txt")];
  assert.deepEqual(filtereVaultPdfs(liste).map((x) => x.id), ["b", "c"]);
  assert.deepEqual(filtereVaultPdfs([]), []);
});

test("margin comparison link uses the vault id; Excel is decoded from the API payload", () => {
  assert.equal(margeVergleichHref("ab/cd"), "/marge?vault=ab%2Fcd");
  const bytes = Uint8Array.from([0x50, 0x4b, 0x03, 0x04]);
  const datei = xlsxAusMargeAntwort({ dateiname: "Kita-Nord-marge.xlsx", xlsx_base64: Buffer.from(bytes).toString("base64") });
  assert.equal(datei.name, "Kita-Nord-marge.xlsx");
  assert.equal(datei.type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  return datei.arrayBuffer().then((buf) => assert.deepEqual([...new Uint8Array(buf)], [...bytes]));
});
