// Auth.js (NextAuth v5): Google when AUTH_GOOGLE_ID/AUTH_GOOGLE_SECRET are set, plus an email-only demo login.
// Without AUTH_SECRET a random secret is generated once and kept in the data folder (git-ignored), so a fresh
// checkout works with no configuration at all.
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { aendern, datenOrdner, nutzerHolen } from "./db";
import { emailOk } from "./plaene";

export function googleAktiv(): boolean {
  return Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
}

export function demoLoginAktiv(): boolean {
  return process.env.AUTH_DEMO_LOGIN !== "0";
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
if (demoLoginAktiv()) {
  providers.push(Credentials({
    id: "demo",
    name: "Demo",
    credentials: { email: { label: "Email", type: "email" } },
    authorize: async (c) => {
      const email = String(c?.email ?? "").trim().toLowerCase();
      if (!emailOk(email)) return null;
      return { id: email, email, name: email.split("@")[0] };
    },
  }));
}

export const { handlers, auth, signOut } = NextAuth({
  secret: geheimnis(),
  trustHost: true,
  session: { strategy: "jwt" },
  providers,
  pages: { signIn: "/konto" },
  events: {
    // Remember every account once, so /admin can list it and grant company seats.
    signIn: async ({ user }) => {
      if (user?.email) await aendern((d) => { nutzerHolen(d, user.email!, user.name); }).catch(() => undefined);
    },
  },
});
