// Final report helpers (#167): synthetic rows only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { hatInhalt, schlussTabelle, schlussZeilen } from "./schlussbericht.ts";

const zeile = (oz, extra = {}) => ({ oz, kurztext: `Item ${oz}`, menge: 10, einheit: "m2", geschaetzt: null, abweichung: null,
  abweichung_eur: null, warum: "", nachtrag: [], probleme: [], warnungen: [], empfehlungen: [], ...extra });
const problem = { finding_id: "F1", schwere: "hoch", titel: "Vague wording", quelle: "modell", regel_id: "LLM_VAGUE" };
const schlussbericht = {
  projektbeschreibung: "Synthetic: 3 item(s) in 1 section(s).",
  positionen: [zeile("01"), zeile("02", { probleme: [problem] }), zeile("03", { geschaetzt: 12, abweichung: 2, nachtrag: ["+2 m2"] })],
  allgemein: [{ ...problem, finding_id: "F9", quelle: "regel", regel_id: "SUMME" }], warnungen: ["Report 2: not connected"],
};

test("only rows with content are shown by default, all on request", () => {
  assert.equal(hatInhalt(zeile("x")), false);
  assert.deepEqual(schlussZeilen({ schlussbericht }).map((z) => z.oz), ["02", "03"]);
  assert.equal(schlussZeilen({ schlussbericht }, true).length, 3);
  assert.deepEqual(schlussZeilen({}), []);
});

test("export sheet keeps every item in LV order plus general problems and warnings", () => {
  const t = schlussTabelle({ schlussbericht });
  assert.equal(t[0][1], schlussbericht.projektbeschreibung);
  assert.deepEqual(t.slice(2, 5).map((r) => r[0]), ["01", "02", "03"]);
  assert.equal(t[3][9], "Vague wording (model LLM_VAGUE)");
  assert.equal(t[4][8], "+2 m2");
  assert.deepEqual(t.slice(5).map((r) => r[0]), ["General", "Warning"]);
  assert.equal(schlussTabelle({}), null);
});
