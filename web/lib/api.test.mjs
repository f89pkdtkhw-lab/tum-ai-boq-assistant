// Run: node --test web/lib/api.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "./api.ts";

const evidence = {
  name: "LV15", items: 2, score: 65, traffic_light: "gelb",
  stated_total: 100, recalculated_total: 100, with_optional_total: null, history_expected_total: null,
  serious_items: 0, findings_by_rule: {}, change_order_findings: 1,
  price_outliers: [], unusual_prices: 0, trades: [], past_overrun_share: null, language: "de",
};
const antwort = {
  decision: "go_with_conditions", headline: "Bid only with conditions", summary: "Height left open.",
  predictions: [], recommendations: [], source: "model",
};

test("identical in-flight AI evaluations share one request", async () => {
  let calls = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /\/api\/lv\/ai-evaluation$/);
    calls += 1;
    await gate;
    return new Response(JSON.stringify(antwort), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const a = api.aiEvaluation(evidence);
    const b = api.aiEvaluation(evidence);
    release();
    const [ra, rb] = await Promise.all([a, b]);
    assert.equal(calls, 1);
    assert.equal(ra.decision, "go_with_conditions");
    assert.equal(rb.headline, antwort.headline);
  } finally {
    globalThis.fetch = original;
  }
});

test("a later AI evaluation after the first finished is sent normally", async () => {
  let calls = 0;
  const original = globalThis.fetch;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify(antwort), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await api.aiEvaluation(evidence);
    await api.aiEvaluation(evidence);
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = original;
  }
});
