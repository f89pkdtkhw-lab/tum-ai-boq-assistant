// Sends a new confirmation link to an unconfirmed email account. Always answers ok (no account enumeration).
import { NextResponse } from "next/server";
import { aendern } from "@/lib/saas/db";
import { emailOk } from "@/lib/saas/plaene";
import { BESTAETIGEN_MS, neuerToken } from "@/lib/saas/token";
import { bestaetigungsMail, sendeMail } from "@/lib/saas/mail";
import { basisUrl } from "@/lib/saas/url";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as { email?: unknown } | null;
  const email = String(b?.email ?? "").trim().toLowerCase();
  if (!emailOk(email)) return NextResponse.json({ ok: true });
  const { token, gespeichert } = neuerToken(BESTAETIGEN_MS);
  const senden = await aendern((d) => {
    const n = d.users[email];
    if (!n?.passwordHash || n.emailVerified !== false) return false;
    n.verifyToken = gespeichert;
    return true;
  });
  if (senden) {
    const link = `${basisUrl(req)}/konto/bestaetigen?email=${encodeURIComponent(email)}&token=${token}`;
    const m = bestaetigungsMail(link);
    await sendeMail(email, m.betreff, m.text, link).catch(() => undefined);
  }
  return NextResponse.json({ ok: true });
}
