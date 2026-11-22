// Server helpers shared by the /api/saas routes: who is signed in, their plan and quota, admin rights.
import { auth, googleAktiv } from "./auth";
import { lesenNur, type Daten } from "./db";
import { adminEmails, effektiverPlan, kontingent, monatsSchluessel, type Kontingent, type PlanId } from "./plaene";
import { stripeAktiv } from "./stripe";

export type KontoStand = {
  angemeldet: boolean;
  email: string | null;
  name: string | null;
  plan: PlanId;
  kontingent: Kontingent;
  firma: { name: string; seats: number; expiresAt: string | null } | null;
  abo: { status: string; intervall: string | null; periodEnd: string | null } | null;
  kunde: boolean;
  admin: boolean;
  konfiguriert: { google: boolean; email: boolean; stripe: boolean };
};

export async function sitzungsEmail(): Promise<{ email: string; name: string | null } | null> {
  try {
    const s = await auth();
    const email = s?.user?.email?.toLowerCase();
    return email ? { email, name: s?.user?.name ?? null } : null;
  } catch {
    return null;
  }
}

export function istAdminEmail(email: string | null | undefined): boolean {
  return Boolean(email && adminEmails(process.env.ADMIN_EMAILS).includes(email.toLowerCase()));
}

export function adminCodeOk(code: string | null | undefined): boolean {
  const soll = process.env.DEV_OPTIONS_CODE || "2211";
  return Boolean(code) && code === soll;
}

export function stand(d: Daten, s: { email: string; name: string | null } | null): KontoStand {
  const konfiguriert = { google: googleAktiv(), email: true, stripe: stripeAktiv() };
  if (!s) {
    return { angemeldet: false, email: null, name: null, plan: "gast", kontingent: kontingent("gast", 0), firma: null, abo: null, kunde: false, admin: false, konfiguriert };
  }
  const n = d.users[s.email] ?? { email: s.email, createdAt: "", usage: {} };
  const firma = n.companyId ? d.companies[n.companyId] : null;
  const plan = effektiverPlan(n, firma);
  const used = n.usage[monatsSchluessel()] ?? 0;
  return {
    angemeldet: true,
    email: s.email,
    name: n.name ?? s.name,
    plan,
    kontingent: kontingent(plan, used),
    firma: plan === "company" && firma ? { name: firma.name, seats: firma.seats, expiresAt: firma.expiresAt } : null,
    abo: n.subscriptionStatus ? { status: n.subscriptionStatus, intervall: n.subscriptionIntervall ?? null, periodEnd: n.periodEnd ?? null } : null,
    kunde: Boolean(n.stripeCustomerId),
    admin: istAdminEmail(s.email),
    konfiguriert,
  };
}

export async function aktuellerStand(): Promise<KontoStand> {
  return stand(await lesenNur(), await sitzungsEmail());
}
