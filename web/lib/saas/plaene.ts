// LV Scout plans and quota rules. Pure functions only (no fs, no network), so node --test can import this file.
// Prices live in Stripe (test mode, account "Print Pool") and are found by lookup_key; see docs/abo.md.

export type PlanId = "gast" | "free" | "pro" | "company";
export type Intervall = "month" | "year";

export type Plan = {
  id: Exclude<PlanId, "gast">;
  name: string;
  /** Evaluations per user and calendar month. Company: per seat. */
  quota: number;
  /** EUR per month (company: per seat) when paid monthly / per year when paid yearly. 0 = free. */
  preisMonat: number;
  preisJahr: number;
  lookupMonat?: string;
  lookupJahr?: string;
  features: string[];
};

export const PLAENE: Plan[] = [
  {
    id: "free", name: "Free", quota: 3, preisMonat: 0, preisJahr: 0,
    features: ["3 evaluations per month", "Rule and quantity checks", "Excel export"],
  },
  {
    id: "pro", name: "Pro", quota: 50, preisMonat: 29, preisJahr: 290,
    lookupMonat: "lv_scout_pro_monthly", lookupJahr: "lv_scout_pro_yearly",
    features: ["50 evaluations per month", "AI review with research and sources", "Margin and competitor pages", "PDF and Excel export"],
  },
  {
    id: "company", name: "Company", quota: 200, preisMonat: 49, preisJahr: 490,
    lookupMonat: "lv_scout_company_seat_monthly", lookupJahr: "lv_scout_company_seat_yearly",
    features: ["200 evaluations per seat and month", "Team seats, one invoice", "Shared price database", "Priority support"],
  },
];

export function plan(id: string | undefined | null): Plan {
  return PLAENE.find((p) => p.id === id) ?? PLAENE[0];
}

export function lookupKey(id: "pro" | "company", intervall: Intervall): string {
  const p = plan(id);
  return (intervall === "year" ? p.lookupJahr : p.lookupMonat) ?? "";
}

/** Plan and interval for a Stripe price lookup_key, or null when it is not one of ours. */
export function ausLookupKey(key: string | null | undefined): { plan: "pro" | "company"; intervall: Intervall } | null {
  for (const p of PLAENE) {
    if (p.id === "free") continue;
    if (key && key === p.lookupMonat) return { plan: p.id, intervall: "month" };
    if (key && key === p.lookupJahr) return { plan: p.id, intervall: "year" };
  }
  return null;
}

/** "2026-11": quota counters reset every calendar month (UTC). */
export function monatsSchluessel(d: Date = new Date()): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export type Firma = { id: string; name: string; seats: number; expiresAt: string | null; members: string[]; quelle: "admin" | "stripe"; createdAt: string };

export type Nutzer = {
  email: string;
  name?: string;
  createdAt: string;
  stripeCustomerId?: string;
  subscriptionId?: string;
  subscriptionStatus?: string;
  subscriptionPlan?: "pro" | "company";
  subscriptionIntervall?: Intervall;
  periodEnd?: string | null;
  companyId?: string;
  /** Email + password accounts only (scrypt, see passwort.ts). Never sent to the browser. */
  passwordHash?: string;
  /** Signed in with Google at least once: email registration for this address is refused. */
  google?: boolean;
  /** Email accounts: false until the confirmation link was opened (Google and the seed account count as confirmed). */
  emailVerified?: boolean;
  /** SHA-256 of the pending confirmation / reset token with expiry (lib/saas/token.ts); never the raw token. */
  verifyToken?: { hash: string; expiresAt: string };
  resetToken?: { hash: string; expiresAt: string };
  usage: Record<string, number>;
};

const AKTIV = new Set(["active", "trialing", "past_due"]);

export function firmaAktiv(f: Firma | undefined | null, jetzt: Date = new Date()): boolean {
  if (!f) return false;
  return !f.expiresAt || new Date(f.expiresAt).getTime() > jetzt.getTime();
}

/** Effective plan: an active company grant wins, then an active Pro subscription, otherwise Free. */
export function effektiverPlan(n: Nutzer, firma: Firma | null | undefined, jetzt: Date = new Date()): Plan["id"] {
  if (n.companyId && firmaAktiv(firma, jetzt) && firma!.members.includes(n.email)) return "company";
  if (n.subscriptionStatus && AKTIV.has(n.subscriptionStatus)) return n.subscriptionPlan === "company" ? "company" : "pro";
  return "free";
}

export type Kontingent = { plan: PlanId; quota: number | null; used: number; remaining: number | null; ueber: boolean };

/** Quota state for the banner. Guest (not signed in) is unlimited and never shows a banner. */
export function kontingent(planId: PlanId, used: number): Kontingent {
  if (planId === "gast") return { plan: "gast", quota: null, used, remaining: null, ueber: false };
  const quota = plan(planId).quota;
  const remaining = Math.max(0, quota - used);
  return { plan: planId, quota, used, remaining, ueber: used >= quota };
}

/** Stripe subscription status → what we store. Unknown or ended states fall back to Free. */
export function aboAusStripe(sub: { id: string; status: string; customer: string; current_period_end?: number | null; items?: { data?: { price?: { lookup_key?: string | null }; quantity?: number; current_period_end?: number | null }[] }; metadata?: Record<string, string> }) {
  const item = sub.items?.data?.[0];
  const lk = ausLookupKey(item?.price?.lookup_key);
  const meta = sub.metadata?.plan;
  const p = lk?.plan ?? (meta === "company" || meta === "pro" ? meta : "pro");
  const ende = sub.current_period_end ?? item?.current_period_end ?? null;
  return {
    subscriptionId: sub.id,
    subscriptionStatus: sub.status,
    subscriptionPlan: p as "pro" | "company",
    subscriptionIntervall: lk?.intervall,
    periodEnd: ende ? new Date(ende * 1000).toISOString() : null,
    seats: Math.max(1, item?.quantity ?? 1),
  };
}

export function emailOk(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export function adminEmails(raw: string | undefined): string[] {
  return (raw ?? "").split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean);
}
