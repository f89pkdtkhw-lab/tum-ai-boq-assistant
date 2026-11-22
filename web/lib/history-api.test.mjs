// Run: node --test web/lib/history-api.test.mjs  (Node >= 23 strips the TypeScript types of history-api.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { applyUpdate, filterCases, validateUpdate } from "./history-api.ts";

const h1 = () => ({
  case_id: "H1", date: "2026-11-20", description: "Mock: bridge repair case.", tags: ["bridge"], source: "model_mock",
  estimated_values: [{ oz: "01.001", title_path: ["Bridge"], metric: "hours", value: 100, unit: "h" }],
  real_values: [], comments: [], marks: [],
  lv: { name: "Synthetic bridge repair", quelle: "synthetic", positionen: [{ oz: "01.001" }] },
});
const actual = (value) => ({ oz: "01.001", title_path: ["Bridge"], metric: "hours", value, unit: "h" });

test("estimate and actual stay separate values", () => {
  const saved = applyUpdate(h1(), { real_values: [actual(120)] });
  assert.equal(saved.estimated_values[0].value, 100);
  assert.equal(saved.real_values[0].value, 120);
});

test("repeat saves do not duplicate values, comments or marks", () => {
  const update = { real_values: [actual(120)], comments: ["Access work"], marks: [{ oz: "01.001", title_path: ["Bridge"], status: "deviation", reason: "Access restriction" }] };
  const twice = applyUpdate(applyUpdate(h1(), update), update);
  assert.equal(twice.real_values.length, 1);
  assert.deepEqual(twice.comments, ["Access work"]);
  assert.equal(twice.marks.length, 1);
  const changed = applyUpdate(twice, { real_values: [actual(125)], marks: [{ oz: "01.001", title_path: [], status: "confirmed" }] });
  assert.equal(changed.real_values[0].value, 125);
  assert.equal(changed.marks[0].status, "confirmed");
});

test("empty explanation stays absent", () => {
  const saved = applyUpdate(h1(), { marks: [{ oz: "01.001", title_path: [], status: "confirmed", what_happened: "  ", reason: "" }] });
  assert.equal("reason" in saved.marks[0], false);
  assert.equal("what_happened" in saved.marks[0], false);
});

test("validation rejects unknown OZ, bad numbers and missing status", () => {
  assert.equal(validateUpdate(h1(), { real_values: [actual(120)] }), null);
  assert.equal(validateUpdate(h1(), { real_values: [actual(null)] }), null);
  assert.match(validateUpdate(h1(), { real_values: [{ ...actual(5), oz: "09.999" }] }), /unknown OZ/);
  assert.match(validateUpdate(h1(), { real_values: [actual(-3)] }), /non-negative/);
  assert.match(validateUpdate(h1(), { real_values: [actual("12")] }), /non-negative/);
  assert.match(validateUpdate(h1(), { marks: [{ oz: "01.001", status: " " }] }), /status/);
  assert.match(validateUpdate(h1(), []), /object/);
});

test("filter by tag, newest first", () => {
  const cases = [{ ...h1(), case_id: "A", date: "2026-01-01" }, { ...h1(), case_id: "B", date: "2026-05-01" }, { ...h1(), case_id: "C", tags: [] }];
  assert.deepEqual(filterCases(cases, "bridge").map((c) => c.case_id), ["B", "A"]);
  assert.deepEqual(filterCases(cases, null).map((c) => c.case_id), ["C", "B", "A"]);
});

test("similar positions match on the work type, newest first, with their own values", async () => {
  const { similarPositions } = await import("./history-api.ts");
  const old = { ...h1(), case_id: "A", date: "2025-01-01", lv: { name: "a", quelle: "s", positionen: [{ oz: "01.001", kurztext: "Erdarbeiten Baugrube" }, { oz: "01.002", kurztext: "Betonarbeiten" }] },
    real_values: [actual(120)], marks: [{ oz: "01.001", title_path: [], status: "deviation" }] };
  const neu = { ...h1(), case_id: "B", date: "2026-01-01", lv: { name: "b", quelle: "s", positionen: [{ oz: "9", kurztext: "erdarbeiten, Teilfläche" }] } };
  const hits = similarPositions([old, neu], "Erdarbeiten Teilfläche 3");
  assert.deepEqual(hits.map((h) => h.case.case_id), ["B", "A"]);
  assert.equal(hits[1].real[0].value, 120);
  assert.equal(hits[1].mark.status, "deviation");
  assert.deepEqual(similarPositions([old], ""), []);
  assert.deepEqual(similarPositions([old], "Mauerarbeiten"), []);
});

test("deviation by trade averages actual vs estimate per work type, worst first", async () => {
  const { deviationByTrade } = await import("./history-api.ts");
  const m = (oz, value) => ({ oz, metric: "hours", value, unit: "h" });
  const c = (id, est, real) => ({ ...h1(), case_id: id,
    lv: { name: id, quelle: "s", positionen: [{ oz: "1", kurztext: "Erdarbeiten X" }, { oz: "2", kurztext: "Betonarbeiten Y" }] },
    estimated_values: [m("1", 100), m("2", 100)], real_values: [m("1", est), ...(real === null ? [] : [m("2", real)])] });
  const stats = deviationByTrade([c("A", 110, 150), c("B", 130, null)]);
  assert.deepEqual(stats.map((s) => s.trade), ["Betonarbeiten", "Erdarbeiten"]);
  assert.equal(stats[0].avgDeviation, 50);
  assert.equal(stats[1].avgDeviation, 20);
  assert.equal(stats[1].projects, 2);
  assert.equal(stats[0].withActual, 1);
  // Betonarbeiten has one observation → no spread; Erdarbeiten 10 % and 30 % → sample std √200 ≈ 14.14
  assert.equal(stats[0].deviationSpread, null);
  assert.ok(Math.abs((stats[1].deviationSpread ?? 0) - Math.sqrt(200)) < 1e-9);
});
