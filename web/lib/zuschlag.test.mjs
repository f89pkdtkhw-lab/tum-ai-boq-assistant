// Run: node --test web/lib/zuschlag.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { gebot, kalkuliere, leseGebote, STANDARD } from "./zuschlag.ts";

test("markups as shares of the bid total: 8 + 12 + 5 = 25 % → bid = EKT / 0.75", () => {
  const k = kalkuliere(750000, STANDARD);
  assert.equal(k.angebot, 1000000);
  assert.deepEqual([k.bgk, k.agk, k.wg, k.selbstkosten], [80000, 120000, 50000, 950000]);
  assert.equal(k.zuschlagAufEkt, 33.3);
});

test("AGK per month × months is a fixed amount", () => {
  const k = kalkuliere(700000, { ...STANDARD, agkModus: "monat", agkMonat: 10000, monate: 5 });
  assert.equal(k.agk, 50000);
  assert.equal(k.angebot, Math.round(750000 / 0.87 * 100) / 100);
});

test("bid advice: undercut, but not below own costs or 10 % under the next bid", () => {
  const k = kalkuliere(750000, STANDARD); // bid 1.0m, own costs 0.95m
  assert.equal(gebot(k, [], STANDARD).grund, "kalkuliert");                          // no competitors: own calculation
  assert.deepEqual([gebot(k, [1100000], STANDARD).empfohlen, gebot(k, [1100000], STANDARD).grund], [1078000, "angehoben"]); // keep the margin
  const g = gebot(k, [980000, 1200000], STANDARD);                         // 2 % under 980k = 960.4k
  assert.deepEqual([g.empfohlen, g.grund, g.rang], [960400, "unterbietet", 1]);
  assert.equal(gebot(k, [900000], STANDARD).grund, "selbstkosten");        // would be below 950k
  assert.equal(gebot(k, [900000], { unterbieten: 15 }).empfohlen, 950000);
  const tief = kalkuliere(100000, STANDARD);
  assert.deepEqual([gebot(tief, [200000], { unterbieten: 30 }).empfohlen, gebot(tief, [200000], { unterbieten: 30 }).grund], [180000, "schwelle"]);
});

test("competitor bids in German or English format", () => {
  assert.deepEqual(leseGebote("1.234.567,89 €\n980,000\n1200000; 2.500.000"), [1234567.89, 980000, 1200000, 2500000]);
});
