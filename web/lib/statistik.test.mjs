// Run: node --test web/lib/statistik.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { genauigkeit } from "./statistik.ts";

test("estimate accuracy: mean absolute error, share within 10 % and yearly trend", () => {
  const m = (oz, value) => ({ oz, metric: "hours", value, unit: "h" });
  const c = (date, est, real) => ({ case_id: date, date, estimated_values: est, real_values: real, lv: { positionen: [] } });
  const g = genauigkeit([c("2024-01-01", [m("1", 100), m("2", 100)], [m("1", 105), m("2", 80)]), c("2025-01-01", [m("1", 100)], [m("1", 130)]), c("2025-02-01", [m("1", 50)], [])]);
  assert.equal(g.projekte, 4 - 1);
  assert.equal(g.abgeschlossen, 2);
  assert.equal(g.vergleiche, 3);
  assert.equal(g.mittlererFehler, (5 + 20 + 30) / 3);
  assert.equal(g.innerhalbZehn, 1 / 3);
  assert.deepEqual(g.jahre.map((j) => [j.jahr, j.abweichung]), [["2024", -7.5], ["2025", 30]]);
});
