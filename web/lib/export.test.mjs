// Run: node --test web/lib/export.test.mjs  (Node >= 23 strips the TypeScript types of export.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

// export.ts uses extensionless relative imports (bundler style); resolve them to .ts for Node.
registerHooks({
  resolve(spec, ctx, next) {
    try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; }
  },
});
const { tabellen, xlsxDateien, STIL_IDS } = await import("./export.ts");
const { demoKalkulation } = await import("./kalkulation.ts");

const p = (oz, kurztext, menge, einheit, typ = "normal", titel = ["01 Earthworks"]) =>
  ({ oz, kurztext, langtext: "", menge, einheit, ep: null, gp: null, typ, titel_pfad: titel });
const f = (oz, kategorie, schwere, vorschlag, regel_id = "R1") =>
  ({ id: `${oz}-${regel_id}`, oz, kategorie, schwere, titel: `T ${oz}`, begruendung: "b", vorschlag, quelle: "regel", regel_id, euro_wirkung: null });
const bericht = (positionen, findings) => ({ lv: { name: "Test", quelle: "x", positionen }, findings, kennzahlen: { kritisch: 0 } });

test("adds Quantities and Bidder questions sheets with numeric quantities", () => {
  const b = bericht(
    [p("01.01", "Excavation", 10, "m³"), p("01.02", "Backfill", 2.5, "m³"), p("02.01", "Rebar", 3, "kg", "normal", ["02 Concrete"]),
      p("02.02", "Option", 9, "m³", "bedarf"), p("02.03", "No qty", null, "m³")],
    [f("02.01", "nachtrag", "mittel", "Confirm rebar grade?"), f("01.01", "risiko", "kritisch", "", "MOCK_LLM"), f("01.02", "fehler", "hoch", "x")],
  );
  const blaetter = tabellen(b);
  assert.deepEqual(blaetter.map((s) => s.name), ["Findings", "Items", "Quantities", "Bidder questions"]);
  assert.deepEqual(blaetter[2].zeilen, [
    ["Scope", "Title", "Unit", "Quantity", "Items"],
    ["Total", "", "m³", 12.5, 2],
    ["Total", "", "kg", 3, 1],
    ["Title", "01 Earthworks", "m³", 12.5, null],
    ["Title", "02 Concrete", "kg", 3, null],
    ["Excluded: optional or alternative", "", "", null, 1],
    ["Excluded: no quantity or unit", "", "", null, 1],
  ]);
  assert.deepEqual(blaetter[3].zeilen, [
    ["OZ", "Short description", "Title", "Question"],
    ["02.01", "Rebar", "T 02.01", "Confirm rebar grade?"],
  ]);
  const xml = xlsxDateien(b);
  assert.match(xml["xl/workbook.xml"], /name="Bidder questions" sheetId="4"/);
  assert.match(xml["xl/worksheets/sheet3.xml"], /<c r="D2"><v>12.5<\/v><\/c>/);
});

test("empty report gives header-only sheets", () => {
  const [, , mengen, fragen] = tabellen(bericht([], []));
  assert.equal(mengen.zeilen.length, 1);
  assert.equal(fragen.zeilen.length, 1);
});

test("Findings sheet carries review status and comment, Open when not reviewed", () => {
  const b = bericht([p("01.01", "Excavation", 10, "m³")], [f("01.01", "fehler", "hoch", "x"), f("01.01", "risiko", "mittel", "y", "R2")]);
  const [befunde] = tabellen(b, { "01.01-R2": { status: "verworfen", kommentar: "covered by 01.02" }, "unknown": { status: "bestaetigt", kommentar: "" } });
  assert.deepEqual(befunde.zeilen[0].slice(-2), ["Review status", "Comment"]);
  assert.deepEqual(befunde.zeilen[1].slice(-2), ["Open", ""]);
  assert.deepEqual(befunde.zeilen[2].slice(-2), ["Dismissed", "covered by 01.02"]);
  assert.deepEqual(tabellen(b)[0].zeilen[2].slice(-2), ["Open", ""], "no decisions means all Open");
  assert.match(xlsxDateien(b, { "01.01-R1": { status: "bestaetigt", kommentar: "" } })["xl/worksheets/sheet1.xml"], /<c r="J2" t="inlineStr" s="1"><is><t xml:space="preserve">Confirmed<\/t>/);
});

test("PDF content (#105): same rows as the XLSX, summary and reports when present, safe text and file name", async () => {
  const { pdfInhalt, pdfDateiname, pdfText } = await import("./export.ts");
  const b = bericht([p("01.01", "Excavation", 10, "m³")], [f("01.01", "fehler", "hoch", "Check it")]);
  b.kennzahlen = { positionen: 1, findings: 1, kritisch: 0, modell_mock: false };
  const ohne = pdfInhalt(b);
  const xlsxBlaetter = tabellen(b);
  assert.deepEqual(ohne.abschnitte.map((a) => a.name), xlsxBlaetter.map((t) => t.name));
  ohne.abschnitte.forEach((a, i) => {
    assert.equal(a.zeilen.length, xlsxBlaetter[i].zeilen.length - 1, a.name);
    assert.equal(a.kopf.length, xlsxBlaetter[i].zeilen[0].length);
  });
  assert.equal(ohne.zusammenfassung.length, 1);

  const mit = pdfInhalt({ ...b,
    zusammenfassung: { score: 8.5, score_abzuege: [{ grund: "Report 1: 1 big problem", punkte: -1, bericht: "regelwerk" }], schaetzung_abweichung_eur: null, grosse_probleme: 1, warnungen: 0, hinweise: 0, empfehlungen: 0 },
    berichte: [{ titel: "Report 1", status: "ok", meldung: "", finding_ids: ["x"] }, { titel: "Report 2", status: "nicht_verbunden", meldung: "DB offline", finding_ids: [] }] });
  assert.match(mit.zusammenfassung[1], /Score: 8\.5 \/ 10/);
  assert.match(mit.zusammenfassung[2], /not connected/);
  assert.match(mit.zusammenfassung[3], /Deduction -1\.0/);
  assert.equal(mit.abschnitte[0].name, "Reports");
  assert.deepEqual(mit.abschnitte[0].zeilen[1], ["Report 2", "not connected", "0", "DB offline"]);

  assert.equal(pdfText("10 → 12 · −5 € m³ Ä ✓"), "10 -> 12 · -5 € m³ Ä ?");
  assert.equal(pdfDateiname("Synthetic House Ü", new Date("2026-11-21T10:00:00Z")), "review-report-synthetic-house-u-2026-11-21.pdf");
});

test("priced and estimated bill sheets (#117): one row per position incl. added/removed, status, colours, sums", () => {
  const positionen = [p("01.01", "Excavation", 10, "m³"), p("01.02", "Backfill", 4, "m³"), p("01.03", "Rebar", 3, "kg"), p("01.04", "Formwork", 2, "m²")];
  const ohne = bericht(positionen, []);
  const mit = { ...ohne, ...demoKalkulation(positionen) };
  const vorher = tabellen(ohne);
  const nachher = tabellen(mit);
  assert.deepEqual(nachher.slice(0, vorher.length), vorher, "existing sheets unchanged");
  const [preis, schaetzung] = nachher.slice(vorher.length);
  assert.equal(preis.name, "Priced bill");
  assert.equal(preis.zeilen.length, 1 + positionen.length + 3);
  assert.deepEqual(preis.zeilen.at(-3).slice(0, 1), ["Net"]);
  assert.equal(preis.zeilen.at(-3)[5], mit.kalkulation.summe_netto);
  assert.equal(preis.zeilen[4][6], "no price");

  assert.equal(schaetzung.name, "Estimated bill");
  assert.equal(schaetzung.zeilen.length, 1 + positionen.length + 1 + 3, "removed item kept, added item appended");
  assert.deepEqual(schaetzung.zeilen.slice(1, 1 + positionen.length + 1).map((z) => z[0]), ["unchanged", "old → new", "− removed", "unchanged", "+ new"]);
  assert.deepEqual(schaetzung.stile.slice(1, 6), [undefined, "updated", "removed", undefined, "added"]);
  assert.equal(schaetzung.zeilen.at(-1)[8], mit.geschaetztes_lv.differenz_netto);

  const dateien = xlsxDateien(mit);
  const blatt = dateien[`xl/worksheets/sheet${vorher.length + 2}.xml`];
  for (const stil of ["added", "removed", "updated", "summe"]) assert.match(blatt, new RegExp(`s="${STIL_IDS[stil][0]}"`), stil);
  assert.match(dateien["xl/styles.xml"], /FFD1FAE5/);
  assert.match(dateien["xl/styles.xml"], /FFFEE2E2/);
  assert.match(dateien["xl/styles.xml"], /FFFEF3C7/);
  assert.match(dateien["xl/styles.xml"], /<strike\/>/);
  assert.match(dateien["xl/workbook.xml"], /name="Estimated bill"/);
});

test("without kalkulation/geschaetztes_lv no sheets are added and sheet XML is unchanged", () => {
  const b = bericht([p("01.01", "Excavation", 10, "m³")], []);
  const ohne = xlsxDateien(b);
  const leer = xlsxDateien({ ...b, kalkulation: null, geschaetztes_lv: null });
  assert.deepEqual(Object.keys(leer), Object.keys(ohne));
  assert.equal(tabellen(b).length, 4);
  assert.doesNotMatch(ohne["xl/workbook.xml"], /Priced bill|Estimated bill/);
});

test("with a price report the workbook starts with a summary and the final estimated price", () => {
  const preis = { war: 1000, geschaetzt: 1100, diff: 100, geaendert: 1,
    zeilen: [{ oz: "01.001", kurztext: "Aushub", menge: 10, einheit: "m³", war: 1000, geschaetzt: 1100, diff: 100, quelle: "historie", grund: "Past projects: {trade} {d} %", werte: { trade: "Erdarbeiten", d: "+10" } }] };
  const b = tabellen({ lv: { name: "LV", quelle: "q", positionen: [p("01.001", "Aushub", 10, "m³")], summen: {} }, findings: [], kennzahlen: { modell_mock: true } }, {}, preis);
  assert.deepEqual(b.slice(0, 2).map((x) => x.name), ["Summary", "Estimated prices"]);
  assert.deepEqual(b[0].zeilen.find((z) => z[0] === "Final estimated price (EUR)"), ["Final estimated price (EUR)", 1100]);
  assert.equal(b[1].zeilen[1][7], "Past projects: Erdarbeiten +10 %");
  assert.deepEqual(b[1].zeilen.at(-1).slice(4, 7), [1000, 1100, 100]);
  // Without a range the new columns stay empty (backwards compatible).
  assert.equal(b[0].zeilen.find((z) => z[0] === "Estimate range (EUR)"), undefined);
  assert.deepEqual(b[1].zeilen[0].slice(-3), ["Range low (EUR)", "Range high (EUR)", "Source"]);
  assert.deepEqual(b[1].zeilen[1].slice(-3), [null, null, "historie"]);
});

test("price-report range is exported on the summary and the estimated-prices sheet", () => {
  const preis = { war: 1000, geschaetzt: 1100, diff: 100, geaendert: 1, von: 990, bis: 1210,
    zeilen: [{ oz: "01.001", kurztext: "Aushub", menge: 10, einheit: "m³", war: 1000, geschaetzt: 1100, diff: 100, von: 990, bis: 1210, quelle: "historie", grund: "Past projects: {trade} {d} %", werte: { trade: "Erdarbeiten", d: "+10" } }] };
  const b = tabellen({ lv: { name: "LV", quelle: "q", positionen: [p("01.001", "Aushub", 10, "m³")], summen: {} }, findings: [], kennzahlen: { modell_mock: true } }, {}, preis);
  assert.deepEqual(b[0].zeilen.find((z) => z[0] === "Estimate range (EUR)"), ["Estimate range (EUR)", "990 – 1210"]);
  assert.deepEqual(b[1].zeilen[1].slice(-3), [990, 1210, "historie"]);
  assert.deepEqual(b[1].zeilen.at(-1).slice(-3), [990, 1210, ""]);
});
