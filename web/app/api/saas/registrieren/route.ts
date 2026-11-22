// Email + password registration. Stores a scrypt hash in saas.json (web/.data, git-ignored) and sends a confirmation
// link (lib/saas/mail.ts); signing in works only after the link was opened. Google accounts and confirmed email
// accounts cannot be taken over; an unconfirmed registration may be repeated (new password, new link).
import { NextResponse } from "next/server";
import { aendern } from "@/lib/saas/db";
import { emailOk } from "@/lib/saas/plaene";
import { hashPasswort, passwortOk } from "@/lib/saas/passwort";
import { BESTAETIGEN_MS, neuerToken } from "@/lib/saas/token";
import { bestaetigungsMail, sendeMail } from "@/lib/saas/mail";
import { basisUrl } from "@/lib/saas/url";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as { email?: unknown; password?: unknown; name?: unknown } | null;
  const email = String(b?.email ?? "").trim().toLowerCase();
  const name = String(b?.name ?? "").trim().slice(0, 80);
  if (!emailOk(email)) return NextResponse.json({ fehler: "Please enter a valid email address." }, { status: 400 });
  if (!passwortOk(b?.password)) return NextResponse.json({ fehler: "The password needs at least 8 characters." }, { status: 400 });
  const hash = hashPasswort(b!.password as string);
  const { token, gespeichert } = neuerToken(BESTAETIGEN_MS);
  const ergebnis = await aendern((d) => {
    const n = d.users[email];
    if (n?.google) return "google";
    if (n?.passwordHash && n.emailVerified !== false) return "vorhanden";
    const neu = n ?? { email, createdAt: new Date().toISOString(), usage: {} };
    if (name && !neu.name) neu.name = name;
    neu.passwordHash = hash;
    neu.emailVerified = false;
    neu.verifyToken = gespeichert;
    d.users[email] = neu;
    return "ok";
  });
  if (ergebnis === "vorhanden") return NextResponse.json({ fehler: "An account with this email already exists. Please sign in." }, { status: 409 });
  if (ergebnis === "google") return NextResponse.json({ fehler: "This email uses Google sign-in. Please continue with Google." }, { status: 409 });
  const link = `${basisUrl(req)}/konto/bestaetigen?email=${encodeURIComponent(email)}&token=${token}`;
  const m = bestaetigungsMail(link);
  try {
    await sendeMail(email, m.betreff, m.text, link);
  } catch {
    return NextResponse.json({ fehler: "The email could not be sent." }, { status: 502 });
  }
  return NextResponse.json({ ok: true, bestaetigen: true });
}
