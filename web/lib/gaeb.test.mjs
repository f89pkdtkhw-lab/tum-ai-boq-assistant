// Run: node --test web/lib/gaeb.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { gaebXml } = await import("./gaeb.ts");

const pos = (oz, menge, ep, gp, extra = {}) => ({ oz, kurztext: `Item ${oz} <&>`, langtext: "", menge, einheit: "m²", ep, gp, typ: "normal", titel_pfad: ["01 Rohbau"], ...extra });
const lv = { name: "Test", quelle: "t", summen: {}, positionen: [pos("01.0010", 2, 12.5, 25), pos("01.0020", 1, 10, 11), pos("02.0010A", 3, null, null)] };

test("X84 keeps the bill's own EP/GP, sections, index letters and escapes text", () => {
  const x = gaebXml(lv, "84", { datum: new Date("2026-11-21") });
  assert.match(x, /DA84\/3\.2/);
  assert.match(x, /<DP>84<\/DP>/);
  assert.match(x, /<BoQCtgy RNoPart="01"><LblTx><p>Rohbau<\/p>/);
  assert.match(x, /<Item RNoPart="0020"><Qty>1\.000<\/Qty><QU>m²<\/QU><UP>10\.00<\/UP><IT>11\.00<\/IT>/);
  assert.match(x, /<Item RNoPart="0010" RNoIndex="A">/);
  assert.match(x, /Item 01\.0010 &lt;&amp;&gt;/);
  assert.match(x, /<Total>36\.00<\/Total>/);
});

test("X83 has no prices; the estimated bill uses the price report", () => {
  assert.doesNotMatch(gaebXml(lv, "83"), /<UP>|<IT>|<Total>/);
  const preis = { zeilen: [{ epGeschaetzt: 15, geschaetzt: 30 }, { epGeschaetzt: 10, geschaetzt: 11 }, { epGeschaetzt: null, geschaetzt: null }] };
  const x = gaebXml(lv, "84", { preis });
  assert.match(x, /<UP>15\.00<\/UP><IT>30\.00<\/IT>/);
  assert.match(x, /<Total>41\.00<\/Total>/);
});
