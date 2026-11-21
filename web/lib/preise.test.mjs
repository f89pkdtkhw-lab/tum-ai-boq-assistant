// Run: node --test web/lib/preise.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

// preise.ts uses extensionless relative imports (bundler style); resolve them to .ts for Node, as in export.test.mjs.
registerHooks({
  resolve(spec, ctx, next) {
    try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; }
  },
});
const { preisspiegel, stufeVon } = await import("./preise.ts");

const pos = (oz, ep, kurztext = "Betonarbeiten Wand", einheit = "m³") => ({ oz, kurztext, einheit, ep, menge: 1, gp: ep, typ: "normal", langtext: "", titel_pfad: [] });

test("IQR rule: normal spread stays green, far prices turn yellow or red", () => {
  assert.equal(stufeVon(250, 220, 240, 260), "gruen");
  assert.equal(stufeVon(200, 220, 240, 260), "gruen"); // < 20 % off the median
  assert.equal(stufeVon(360, 220, 240, 260), "gelb");  // above Q3 + 1.5 × IQR, 50 % off
  assert.equal(stufeVon(1000, 220, 240, 260), "rot");  // above Q3 + 3 × IQR
  assert.equal(stufeVon(40, 220, 240, 260), "rot");
});

test("groups same work and unit, flags the outlier, skips small groups and missing prices", () => {
  const p = [pos("1", 230), pos("2", 240), pos("3", 250), pos("4", 245), pos("5", 960), pos("6", 20, "Fenster X", "St"), pos("7", null)];
  const s = preisspiegel(p, null);
  assert.equal(s.gruppen.length, 1);
  const g = s.gruppen[0];
  assert.equal(g.median, 245);
  assert.equal(g.positionen[0].oz, "5");
  assert.equal(g.positionen[0].stufe, "rot");
  assert.equal(g.auffaellig, 1);
  assert.deepEqual(s.zaehler, { gruen: 4, gelb: 0, rot: 1 });
  assert.equal(s.zuWenig, 1);
  assert.equal(s.ohnePreis, 1);
});

test("median is compared with past projects of the same trade and unit", () => {
  const fall = (id, v) => ({ case_id: id, estimated_values: [{ oz: "1", metric: "unit_price", value: v, unit: "EUR/m³" }], real_values: [], lv: { positionen: [{ oz: "1", kurztext: "Betonarbeiten Bodenplatte" }] } });
  const s = preisspiegel([pos("1", 300), pos("2", 300), pos("3", 300), pos("4", 300)], [fall("A", 200), fall("B", 200), fall("C", 250)]);
  const h = s.gruppen[0].historie;
  assert.equal(h.median, 200);
  assert.equal(h.projekte, 3);
  assert.equal(h.abweichung, .5);
  assert.equal(h.stufe, "rot");
});
