// Run: node --test web/lib/fundstelle.test.mjs  (Node >= 23 strips the TypeScript types of fundstelle.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { formatVon, fundstelleTeile, pdfAnker, pdfLink } from "./fundstelle.ts";

const p = (oz, quelle) => ({ oz, kurztext: "", langtext: "", menge: 1, einheit: "m", ep: null, gp: null, typ: "normal", titel_pfad: [], quelle });

test("format follows the file extension", () => {
  assert.equal(formatVon("lv.PDF"), "pdf");
  assert.equal(formatVon("angebot.xlsx"), "excel");
  assert.equal(formatVon("offer.x84"), "gaeb");
  assert.equal(formatVon("offer.D83"), "gaeb");
  assert.equal(formatVon("lv.json"), "json");
});

test("location note names file, page/line, sheet/row and OZ", () => {
  assert.deepEqual(fundstelleTeile("lv.pdf", "1...2", p("1...2", { seite: 2, zeile: 8 })), ["lv.pdf", "page 2", "line 8", "OZ 1...2"]);
  assert.deepEqual(fundstelleTeile("a.xlsx", "01.02", p("01.02", { blatt: "LV", zeile: 5 })), ["a.xlsx", "sheet “LV”", "row 5", "OZ 01.02"]);
  assert.deepEqual(fundstelleTeile("a.d83", "01", p("01", { zeile: 2 })), ["a.d83", "record line 2", "OZ 01"]);
  assert.deepEqual(fundstelleTeile("lv.json", "01", p("01")), ["lv.json", "OZ 01"]);
  assert.deepEqual(fundstelleTeile("lv.json", "09", undefined), ["lv.json", "OZ 09 (not in the BoQ)"]);
  assert.deepEqual(fundstelleTeile("lv.pdf", "1", p("1", { seite: 3, zeile: 4 }), "de"), ["lv.pdf", "Seite 3", "Zeile 4", "OZ 1"]);
});

test("PDF anchor opens the page and scrolls to the item's top edge in PDF user space", () => {
  assert.equal(pdfAnker(undefined), "");
  assert.equal(pdfAnker({ blatt: "LV", zeile: 3 }), "");
  assert.equal(pdfAnker({ seite: 2 }), "#page=2");
  assert.equal(pdfAnker({ seite: 2, bbox: [57, 210, 292, 245], seite_groesse: [595, 842] }), "#page=2&zoom=100,0,656");
  assert.equal(pdfLink("blob:x", p("1", { seite: 1 })), "blob:x#page=1");
  assert.equal(pdfLink(null, p("1", { seite: 1 })), null);
  assert.equal(pdfLink("blob:x", p("1", { blatt: "LV", zeile: 1 })), null);
});
