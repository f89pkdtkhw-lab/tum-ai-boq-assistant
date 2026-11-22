// Auth.js (NextAuth v5): Google when AUTH_GOOGLE_ID/AUTH_GOOGLE_SECRET are set, plus email + password accounts
// (registered via POST /api/saas/registrieren, scrypt hash in saas.json, see passwort.ts).
// Without AUTH_SECRET a random secret is generated once and kept in the data folder (git-ignored), so a fresh
// checkout works with no configuration at all.
import NextAuth, { CredentialsSignin } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { aendern, datenOrdner, lesenNur, nutzerHolen } from "./db";
import { pruefePasswort } from "./passwort";
import { seedKonto } from "./seed";
import { emailOk } from "./plaene";

/** Correct password, but the confirmation link was not opened yet; the sign-in page offers to resend it. */
class Unbestaetigt extends CredentialsSignin {
  code = "unbestaetigt";
}

export function googleAktiv(): boolean {
  return Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
}

function geheimnis(): string {
  if (process.env.AUTH_SECRET) return process.env.AUTH_SECRET;
  const datei = path.join(datenOrdner(), "auth-secret");
  try {
    return readFileSync(datei, "utf8").trim();
  } catch {
    const neu = randomBytes(32).toString("hex");
    try {
      mkdirSync(datenOrdner(), { recursive: true });
      writeFileSync(datei, neu, { mode: 0o600 });
    } catch { /* read-only disk: sessions last until the next restart */ }
    return neu;
  }
}

const providers = [];
if (googleAktiv()) providers.push(Google);
providers.push(Credentials({
  id: "passwort",
  name: "Email",
  credentials: { email: { label: "Email", type: "email" }, password: { label: "Password", type: "password" } },
  authorize: async (c) => {
    const email = String(c?.email ?? "").trim().toLowerCase();
    const pw = String(c?.password ?? "");
    if (!emailOk(email) || !pw) return null;
    await seedKonto();
    const n = (await lesenNur()).users[email];
    if (!n?.passwordHash || !pruefePasswort(pw, n.passwordHash)) return null;
    if (n.emailVerified === false) throw new Unbestaetigt();
    return { id: email, email, name: n.name ?? email.split("@")[0] };
  },
}));

export const { handlers, auth, signOut } = NextAuth({
  secret: geheimnis(),
  trustHost: true,
  session: { strategy: "jwt" },
  providers,
  pages: { signIn: "/konto" },
  events: {
    // Remember every account once, so /admin can list it and grant company seats.
    signIn: async ({ user, account }) => {
      if (user?.email) {
        await aendern((d) => {
          const n = nutzerHolen(d, user.email!, user.name);
          if (account?.provider === "google") { n.google = true; n.emailVerified = true; }
        }).catch(() => undefined);
      }
    },
  },
});
