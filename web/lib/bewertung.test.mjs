// Run: node --test web/lib/bewertung.test.mjs  (Node >= 23 strips the TypeScript types of bewertung.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { anzahlGeprueft, bewertungVon, leseBewertungen, setze, speicherSchluessel } from "./bewertung.ts";

const f = (id) => ({ id, oz: "01", kategorie: "fehler", schwere: "mittel", titel: "", begruendung: "", vorschlag: "", quelle: "regel", regel_id: "R", euro_wirkung: null });
const findings = [f("a"), f("b"), f("c")];

test("set and clear status; default is Open", () => {
  assert.deepEqual(bewertungVon({}, "a"), { status: "offen", kommentar: "" });
  let b = setze({}, "a", { status: "bestaetigt" });
  assert.deepEqual(b, { a: { status: "bestaetigt", kommentar: "" } });
  b = setze(b, "a", { kommentar: "  check plan  " });
  assert.deepEqual(b.a, { status: "bestaetigt", kommentar: "check plan" });
  b = setze(b, "a", { status: "offen" });
  assert.deepEqual(b.a, { status: "offen", kommentar: "check plan" }, "an Open finding keeps its comment");
  assert.deepEqual(setze(b, "a", { kommentar: "   " }), {}, "Open with a blank comment is cleared");
});

test("setze does not mutate its input", () => {
  const b = Object.freeze({ a: Object.freeze({ status: "verworfen", kommentar: "x" }) });
  setze(b, "a", { status: "offen", kommentar: "" });
  assert.equal(b.a.status, "verworfen");
});

test("key per LV name", () => {
  assert.equal(speicherSchluessel("LV 1"), "lv-bewertung-v1:LV 1");
  assert.notEqual(speicherSchluessel("LV 1"), speicherSchluessel("LV 2"));
});

test("counts reviewed findings only", () => {
  const b = { a: { status: "bestaetigt", kommentar: "" }, b: { status: "offen", kommentar: "note" }, c: { status: "verworfen", kommentar: "" } };
  assert.equal(anzahlGeprueft(findings, b), 2);
  assert.equal(anzahlGeprueft([f("a")], b), 1, "decisions for findings not shown are not counted");
});

test("parsing ignores unknown ids, bad statuses and broken JSON", () => {
  const text = JSON.stringify({
    a: { status: "verworfen", kommentar: " duplicate " }, gone: { status: "bestaetigt", kommentar: "" },
    b: { status: "maybe" }, c: { status: "offen", kommentar: "" },
  });
  assert.deepEqual(leseBewertungen(text, findings), { a: { status: "verworfen", kommentar: "duplicate" } });
  assert.deepEqual(leseBewertungen("{nope", findings), {});
  assert.deepEqual(leseBewertungen(null, findings), {});
  assert.deepEqual(leseBewertungen("[1]", findings), {});
});
