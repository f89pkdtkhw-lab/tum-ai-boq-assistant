// Run: node --test web/lib/berichte.test.mjs  (Node >= 23 strips the TypeScript types of berichte.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { abschnitte, chanceName, hatBerichte, prozentText, wasWennListe } from "./berichte.ts";

const f = (id) => ({ id, oz: "01", kategorie: "fehler", schwere: "hoch", titel: id, begruendung: "", vorschlag: "", quelle: "regel", regel_id: "R", euro_wirkung: null });
const b = (id, extra = {}) => ({ id, titel: id, status: "ok", meldung: "", finding_ids: [], notes: [], neue_tags: [], ...extra });
const findings = [f("a"), f("b"), f("c")];

test("missing field: no berichte means today's view", () => {
  assert.equal(hatBerichte({}), false);
  assert.equal(hatBerichte({ berichte: null }), false);
  assert.equal(hatBerichte({ berichte: [] }), false);
  assert.deepEqual(abschnitte({ findings }), []);
  assert.deepEqual(wasWennListe({}), []);
});

test("grouping: findings resolved per report in backend order, unknown ids kept visible", () => {
  const a = abschnitte({ findings, berichte: [b("regelwerk", { finding_ids: ["b", "a", "zz"] }), b("vergleich"), b("was_wenn")] });
  assert.deepEqual(a.map((x) => x.bericht.id), ["regelwerk", "vergleich", "was_wenn"]);
  assert.deepEqual(a[0].findings.map((x) => x.id), ["b", "a"]);
  assert.deepEqual(a[0].fehlend, ["zz"]);
  assert.equal(a[0].leer, null);
});

test("empty states: not connected, error, nothing to report", () => {
  const a = abschnitte({ findings, berichte: [
    b("regelwerk"), b("vergleich", { status: "nicht_verbunden", meldung: "DB offline." }), b("was_wenn", { status: "fehler" }),
  ] });
  assert.equal(a[0].leer, "Nothing to report.");
  assert.equal(a[1].leer, "DB offline.");
  assert.equal(abschnitte({ findings, berichte: [b("vergleich", { status: "nicht_verbunden" })] })[0].leer, "History database not connected.");
  assert.equal(a[2].leer, "This report could not be created.");
  // Not connected wins even if the report carries leftovers.
  assert.match(abschnitte({ findings, berichte: [b("vergleich", { status: "nicht_verbunden", finding_ids: ["a"] })] })[0].leer, /not connected/);
});

test("what-if list: top-level list, else Report 3 problems; high chance first", () => {
  const w = (problem, chance) => ({ oz: null, problem, chance, empfehlung: "", case_ids: [] });
  assert.deepEqual(wasWennListe({ was_wenn: [w("x", "niedrig"), w("y", "hoch"), w("z", "niedrig")] }).map((x) => x.problem), ["y", "x", "z"]);
  assert.deepEqual(wasWennListe({ berichte: [b("was_wenn", { probleme: [w("p", "niedrig")] })] }).map((x) => x.problem), ["p"]);
  assert.equal(chanceName("hoch"), "High chance");
});

test("percent formatting", () => {
  assert.equal(prozentText(12), "+12 %");
  assert.equal(prozentText(-8.46), "−8.5 %");
  assert.equal(prozentText(0), "±0 %");
});
