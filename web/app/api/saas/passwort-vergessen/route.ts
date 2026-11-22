// "Forgot password": emails a reset link (1 h) to an email account. Always answers ok (no account enumeration).
// Google-only accounts have no password and get no link.
import { NextResponse } from "next/server";
import { aendern } from "@/lib/saas/db";
import { emailOk } from "@/lib/saas/plaene";
import { RESET_MS, neuerToken } from "@/lib/saas/token";
import { resetMail, sendeMail } from "@/lib/saas/mail";
import { basisUrl } from "@/lib/saas/url";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as { email?: unknown } | null;
  const email = String(b?.email ?? "").trim().toLowerCase();
  if (!emailOk(email)) return NextResponse.json({ ok: true });
  const { token, gespeichert } = neuerToken(RESET_MS);
  const senden = await aendern((d) => {
    const n = d.users[email];
    if (!n?.passwordHash) return false;
    n.resetToken = gespeichert;
    return true;
  });
  if (senden) {
    const link = `${basisUrl(req)}/konto/passwort-neu?email=${encodeURIComponent(email)}&token=${token}`;
    const m = resetMail(link);
    await sendeMail(email, m.betreff, m.text, link).catch(() => undefined);
  }
  return NextResponse.json({ ok: true });
}
