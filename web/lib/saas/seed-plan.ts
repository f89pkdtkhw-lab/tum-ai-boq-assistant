// Pure helpers for the fixed seed account (no fs/db), so node --test can import them.
import type { Nutzer } from "./plaene";

export const SEED_EMAIL = "dummy@gmail.com";
/** Highest paid plan in plaene.ts (quota 200). */
export const SEED_PLAN = "company" as const;

/** Upgrade or fill the seed user: confirmed email, Company subscription. Password is left to seed.ts. */
export function mitSeedAbo(n: Nutzer): Nutzer {
  n.emailVerified = true;
  n.subscriptionPlan = SEED_PLAN;
  n.subscriptionStatus = "active";
  return n;
}
