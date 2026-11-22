// Sets a new password from a reset link (hashed token, 1 h). Opening the link proves the mailbox, so the email
// counts as confirmed afterwards. The token works once.
import { NextResponse } from "next/server";
import { aendern } from "@/lib/saas/db";
import { hashPasswort, passwortOk } from "@/lib/saas/passwort";
import { tokenOk } from "@/lib/saas/token";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as { email?: unknown; token?: unknown; password?: unknown } | null;
  const email = String(b?.email ?? "").trim().toLowerCase();
  if (!passwortOk(b?.password)) return NextResponse.json({ fehler: "The password needs at least 8 characters." }, { status: 400 });
  const hash = hashPasswort(b!.password as string);
  const ok = await aendern((d) => {
    const n = d.users[email];
    if (!n?.passwordHash || !tokenOk(b?.token, n.resetToken)) return false;
    n.passwordHash = hash;
    n.emailVerified = true;
    delete n.resetToken;
    delete n.verifyToken;
    return true;
  });
  if (!ok) return NextResponse.json({ fehler: "This link is invalid or has expired." }, { status: 400 });
  return NextResponse.json({ ok: true });
}
