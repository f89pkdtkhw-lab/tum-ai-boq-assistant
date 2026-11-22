// Admin: list accounts and plans, unlock company plans by hand (no payment). Allowed for ADMIN_EMAILS
// or with the developer-options code (DEV_OPTIONS_CODE, default 2211) in the x-admin-code header.
import { NextResponse } from "next/server";
import { aendern, lesenNur, neueFirmaId, nutzerHolen, type Daten } from "@/lib/saas/db";
import { adminCodeOk, istAdminEmail, sitzungsEmail } from "@/lib/saas/konto";
import { effektiverPlan, emailOk, firmaAktiv, monatsSchluessel } from "@/lib/saas/plaene";

export const dynamic = "force-dynamic";

async function erlaubt(req: Request): Promise<boolean> {
  if (adminCodeOk(req.headers.get("x-admin-code"))) return true;
  const s = await sitzungsEmail();
  return istAdminEmail(s?.email);
}

function uebersicht(d: Daten) {
  const m = monatsSchluessel();
  return {
    users: Object.values(d.users).map((n) => ({
      email: n.email, name: n.name ?? null, createdAt: n.createdAt,
      plan: effektiverPlan(n, n.companyId ? d.companies[n.companyId] : null),
      used: n.usage[m] ?? 0, companyId: n.companyId ?? null, subscriptionStatus: n.subscriptionStatus ?? null,
    })).sort((a, b) => a.email.localeCompare(b.email)),
    companies: Object.values(d.companies).map((f) => ({ ...f, aktiv: firmaAktiv(f) })).sort((a, b) => a.name.localeCompare(b.name)),
  };
}

export async function GET(req: Request) {
  if (!(await erlaubt(req))) return NextResponse.json({ fehler: "Not allowed." }, { status: 403 });
  return NextResponse.json(uebersicht(await lesenNur()), { headers: { "Cache-Control": "no-store" } });
}

type Aktion =
  | { aktion: "firma"; id?: string; name: string; seats: number; expiresAt?: string | null; members: string[] }
  | { aktion: "firma-loeschen"; id: string };

export async function POST(req: Request) {
  if (!(await erlaubt(req))) return NextResponse.json({ fehler: "Not allowed." }, { status: 403 });
  const a = (await req.json().catch(() => null)) as Aktion | null;
  if (!a) return NextResponse.json({ fehler: "Bad request." }, { status: 400 });
  try {
    const d = await aendern((d) => {
      if (a.aktion === "firma") {
        const name = String(a.name ?? "").trim().slice(0, 80);
        if (!name) throw new Error("Company name is missing.");
        const seats = Math.min(10000, Math.max(1, Math.round(Number(a.seats) || 1)));
        const members = [...new Set((a.members ?? []).map((e) => String(e).trim().toLowerCase()).filter(emailOk))];
        if (members.length > seats) throw new Error(`${members.length} members but only ${seats} seats.`);
        const ablauf = a.expiresAt ? new Date(a.expiresAt) : null;
        if (ablauf && Number.isNaN(ablauf.getTime())) throw new Error("Invalid expiry date.");
        const f = (a.id && d.companies[a.id]) || { id: neueFirmaId(), name, seats, expiresAt: null, members: [], quelle: "admin" as const, createdAt: new Date().toISOString() };
        for (const alt of f.members) if (!members.includes(alt) && d.users[alt]?.companyId === f.id) delete d.users[alt].companyId;
        Object.assign(f, { name, seats, members, expiresAt: ablauf ? ablauf.toISOString() : null });
        d.companies[f.id] = f;
        for (const e of members) nutzerHolen(d, e).companyId = f.id;
      } else if (a.aktion === "firma-loeschen") {
        const f = d.companies[a.id];
        if (f) {
          for (const e of f.members) if (d.users[e]?.companyId === f.id) delete d.users[e].companyId;
          delete d.companies[a.id];
        }
      }
      return d;
    });
    return NextResponse.json(uebersicht(d));
  } catch (e) {
    return NextResponse.json({ fehler: e instanceof Error ? e.message : "Error" }, { status: 400 });
  }
}
