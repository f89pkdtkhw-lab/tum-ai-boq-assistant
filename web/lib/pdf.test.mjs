// Run: node --test web/lib/pdf.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { PdfSchreiber, umbrechen } = await import("./pdf.ts");
const { berichtPdf } = await import("./berichtpdf.ts");

const latin1 = (bytes) => Array.from(bytes, (b) => String.fromCharCode(b)).join("");

test("structure: header, one page object per page, valid xref offsets, umlauts and euro in WinAnsi", () => {
  const p = new PdfSchreiber();
  p.text(36, 50, "Größe (1) € – ok");
  p.neueSeite();
  p.text(36, 50, "Seite 2");
  const s = latin1(p.bytes());
  assert.ok(s.startsWith("%PDF-1.4"));
  assert.match(s, /\/Count 2/);
  assert.ok(s.includes("Gr\xf6\xdfe \\(1\\) \x80 \x96 ok"));
  const xref = Number(s.match(/startxref\n(\d+)/)[1]);
  assert.ok(s.slice(xref).startsWith("xref"));
  const ersterOffset = Number(s.slice(xref).split("\n")[3].slice(0, 10));
  assert.ok(s.slice(ersterOffset).startsWith("1 0 obj"));
});

test("wrapping keeps words and cuts only overlong ones", () => {
  assert.deepEqual(umbrechen("eins zwei drei", 40, 10), ["eins", "zwei", "drei"]);
  assert.ok(umbrechen("x".repeat(80), 60, 10).length > 1);
});

test("report PDF lists every finding in the chosen language and breaks pages", () => {
  const f = (i) => ({ id: `R:${i}`, oz: `01.${i}`, kategorie: "fehler", schwere: i % 2 ? "hoch" : "mittel", titel: "Missing unit", begruendung: "Missing unit.",
    vorschlag: "Add the unit specified in the work description.", quelle: "regel", regel_id: "EINHEIT_FEHLT", euro_wirkung: i * 100 });
  const bericht = { lv: { name: "LV", quelle: "test", positionen: [{ oz: "1", gp: 1000 }], summen: {} }, findings: Array.from({ length: 80 }, (_, i) => f(i)),
    kennzahlen: { modell_mock: false }, zusammenfassung: { score: 8, score_abzuege: [], schaetzung_abweichung_eur: null, grosse_probleme: 40, warnungen: 40, hinweise: 0, empfehlungen: 2 } };
  const s = latin1(berichtPdf(bericht, { t: (x) => x, sprache: "de", status: () => "", titel: "Test" }));
  assert.ok(Number(s.match(/\/Count (\d+)/)[1]) >= 3);
  assert.ok(s.includes("(Einheit fehlt) Tj"));
  assert.ok(s.includes("(8.0 / 10) Tj"));
});
