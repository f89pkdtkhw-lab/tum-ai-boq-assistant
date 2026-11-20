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
const { tabellen, xlsxDateien } = await import("./export.ts");

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
    ["OZ", "Short description", "Title", "Question", "Note"],
    ["01.01", "Excavation", "T 01.01", "T 01.01", "Demonstration (mock)"],
    ["02.01", "Rebar", "T 02.01", "Confirm rebar grade?", ""],
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
  assert.match(xlsxDateien(b, { "01.01-R1": { status: "bestaetigt", kommentar: "" } })["xl/worksheets/sheet1.xml"], /<c r="K2" t="inlineStr" s="1"><is><t xml:space="preserve">Confirmed<\/t>/);
});
