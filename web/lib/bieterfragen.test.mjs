// Run: node --test web/lib/bieterfragen.test.mjs  (Node >= 23 strips the TypeScript types of bieterfragen.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { bieterfragen, alsText } from "./bieterfragen.ts";

const f = (id, oz, kategorie, schwere, quelle = "regel", regel_id = "R1", vorschlag = `Ask about ${id}`) =>
  ({ id, oz, kategorie, schwere, titel: `Title ${id}`, begruendung: "", vorschlag, quelle, regel_id, euro_wirkung: null });
const p = (oz, kurztext) =>
  ({ oz, kurztext, langtext: "", menge: null, einheit: null, ep: null, gp: null, typ: "normal", titel_pfad: [] });

test("keeps only risk and change-order findings, by severity then OZ, offline-model placeholders left out", () => {
  const fragen = bieterfragen([
    f("e", "01.01", "fehler", "kritisch"),
    f("a", "01.10", "risiko", "mittel"),
    f("b", "01.2", "nachtrag", "mittel"),
    f("c", "02.01", "risiko", "hoch", "modell", "MOCK_LLM"),
    f("d", "09.99", "nachtrag", "niedrig", "regel", "R2", "  "),
  ], [p("01.2", "Excavation"), p("01.2", "Duplicate"), p("01.10", "")]);

  assert.deepEqual(fragen.map((x) => x.id), ["b", "a", "d"]);
  assert.equal(fragen.some((x) => "mock" in x), false);
  assert.equal(fragen[0].kurztext, "Excavation");
  assert.equal(fragen[1].kurztext, null);
  assert.equal(fragen[2].frage, "Title d"); // empty vorschlag falls back to the title
  assert.equal(alsText(fragen), "01.2 – Ask about b\n01.10 – Ask about a\n09.99 – Title d");
});

test("no risk or change-order findings gives an empty list", () => {
  assert.deepEqual(bieterfragen([f("e", "1", "fehler", "hoch")], []), []);
  assert.equal(alsText([]), "");
});
