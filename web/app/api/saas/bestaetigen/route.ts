// Opens the confirmation link: checks the hashed token and its expiry, then marks the email as confirmed.
import { NextResponse } from "next/server";
import { aendern } from "@/lib/saas/db";
import { tokenOk } from "@/lib/saas/token";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as { email?: unknown; token?: unknown } | null;
  const email = String(b?.email ?? "").trim().toLowerCase();
  const ok = await aendern((d) => {
    const n = d.users[email];
    if (!n) return false;
    if (n.emailVerified !== false) return Boolean(n.passwordHash); // already confirmed: the link just says so
    if (!tokenOk(b?.token, n.verifyToken)) return false;
    n.emailVerified = true;
    delete n.verifyToken;
    return true;
  });
  if (!ok) return NextResponse.json({ fehler: "This link is invalid or has expired." }, { status: 400 });
  return NextResponse.json({ ok: true });
}
