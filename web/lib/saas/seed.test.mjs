// Run: node --test web/lib/saas/seed.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { effektiverPlan } from "./plaene.ts";
import { mitSeedAbo, SEED_EMAIL, SEED_PLAN } from "./seed-plan.ts";

test("seed account is always upgraded to the highest plan, including an existing Free user", () => {
  assert.equal(SEED_PLAN, "company");
  const neu = mitSeedAbo({ email: SEED_EMAIL, createdAt: "2026-01-01T00:00:00Z", usage: {} });
  assert.equal(neu.emailVerified, true);
  assert.equal(neu.subscriptionPlan, "company");
  assert.equal(neu.subscriptionStatus, "active");
  assert.equal(effektiverPlan(neu, null), "company");

  const alt = mitSeedAbo({
    email: SEED_EMAIL, name: "Dummy", createdAt: "2026-01-01T00:00:00Z", usage: {},
    emailVerified: true, passwordHash: "already-set",
  });
  assert.equal(alt.passwordHash, "already-set");
  assert.equal(effektiverPlan(alt, null), "company");
});
