// Run: node --test web/lib/preisbericht.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { preisbericht } = await import("./preisbericht.ts");

const pos = (oz, kurztext, menge, ep, gp = menge * ep) => ({ oz, kurztext, langtext: "", menge, einheit: "m³", ep, gp, typ: "normal", titel_pfad: [] });

test("price list first, then past projects, else unchanged; totals and changed count", () => {
  const b = preisbericht(
    [pos("1", "Betonarbeiten Wand", 10, 100), pos("2", "Erdarbeiten Aushub", 10, 20), pos("3", "Malerarbeiten Anstrich", 10, 5), { ...pos("4", "Fenster", null, null), gp: null }],
    [{ trade: "Erdarbeiten", projects: 5, withActual: 5, avgDeviation: 10 }, { trade: "Malerarbeiten", projects: 5, withActual: 5, avgDeviation: 1 }],
    [{ item: "Betonarbeiten", unit: "m³", preis: 120 }]);
  assert.deepEqual(b.zeilen.map((z) => [z.oz, z.quelle, z.geschaetzt]), [["1", "preisliste", 1200], ["2", "historie", 220], ["3", "unveraendert", 50], ["4", "ohne_preis", null]]);
  assert.equal(b.war, 1250);
  assert.equal(b.geschaetzt, 1470);
  assert.equal(b.diff, 220);
  assert.equal(b.geaendert, 2);
});
