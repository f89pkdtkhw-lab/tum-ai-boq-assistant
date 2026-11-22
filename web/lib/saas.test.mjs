// Run: node --test web/lib/saas.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { aboAusStripe, adminEmails, ausLookupKey, effektiverPlan, kontingent, lookupKey, monatsSchluessel } from "./saas/plaene.ts";
import { formKodieren, signaturBauen, signaturPruefen } from "./saas/stripe-util.ts";

const basis = { email: "a@b.de", createdAt: "2026-11-01T00:00:00Z", usage: {} };

test("lookup keys round-trip", () => {
  assert.equal(lookupKey("pro", "month"), "lv_scout_pro_monthly");
  assert.equal(lookupKey("company", "year"), "lv_scout_company_seat_yearly");
  assert.deepEqual(ausLookupKey("lv_scout_pro_yearly"), { plan: "pro", intervall: "year" });
  assert.equal(ausLookupKey("other"), null);
});

test("effective plan: company grant > active subscription > free", () => {
  assert.equal(effektiverPlan(basis, null), "free");
  assert.equal(effektiverPlan({ ...basis, subscriptionStatus: "active", subscriptionPlan: "pro" }, null), "pro");
  assert.equal(effektiverPlan({ ...basis, subscriptionStatus: "canceled", subscriptionPlan: "pro" }, null), "free");
  const firma = { id: "f1", name: "X", seats: 5, expiresAt: "2099-01-01T00:00:00Z", members: ["a@b.de"], quelle: "admin", createdAt: "" };
  assert.equal(effektiverPlan({ ...basis, companyId: "f1" }, firma), "company");
  assert.equal(effektiverPlan({ ...basis, companyId: "f1" }, { ...firma, expiresAt: "2020-01-01T00:00:00Z" }), "free");
  assert.equal(effektiverPlan({ ...basis, companyId: "f1" }, { ...firma, members: [] }), "free");
});

test("quota is soft and demo is unlimited", () => {
  assert.deepEqual(kontingent("demo", 9), { plan: "demo", quota: null, used: 9, remaining: null, ueber: false });
  assert.equal(kontingent("free", 2).remaining, 1);
  assert.equal(kontingent("free", 3).ueber, true);
  assert.equal(kontingent("free", 7).remaining, 0);
  assert.equal(kontingent("pro", 7).quota, 50);
});

test("month key and admin list", () => {
  assert.equal(monatsSchluessel(new Date("2026-11-22T01:00:00Z")), "2026-11");
  assert.deepEqual(adminEmails(" A@b.de, c@d.de;"), ["a@b.de", "c@d.de"]);
});

test("Stripe subscription mapping", () => {
  const s = aboAusStripe({ id: "sub_1", status: "active", customer: "cus_1", items: { data: [{ price: { lookup_key: "lv_scout_company_seat_monthly" }, quantity: 4, current_period_end: 1800000000 }] } });
  assert.equal(s.subscriptionPlan, "company");
  assert.equal(s.seats, 4);
  assert.equal(s.periodEnd, new Date(1800000000 * 1000).toISOString());
});

test("form encoding and webhook signatures", () => {
  assert.equal(formKodieren({ a: { b: 1 }, c: [{ d: "x y" }], e: undefined }), "a%5Bb%5D=1&c%5B0%5D%5Bd%5D=x%20y");
  const body = '{"id":"evt_1"}';
  const h = signaturBauen(body, "whsec_test", 1000);
  assert.equal(signaturPruefen(body, h, "whsec_test", 300, 1100), true);
  assert.equal(signaturPruefen(body + " ", h, "whsec_test", 300, 1100), false);
  assert.equal(signaturPruefen(body, h, "whsec_test", 300, 2000), false);
  assert.equal(signaturPruefen(body, null, "whsec_test"), false);
});

test("German plan texts keep their placeholders", async () => {
  const { DE_SAAS } = await import("./saas/i18n-saas.ts");
  const platzhalter = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join();
  for (const [en, de] of Object.entries(DE_SAAS)) assert.equal(platzhalter(de), platzhalter(en), en);
});
