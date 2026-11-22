// One-time tokens for email confirmation and password reset. Only the SHA-256 hash and the expiry are stored
// (saas.json); the raw token exists only in the emailed link. Pure apart from crypto, so node --test can import it.
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export const BESTAETIGEN_MS = 24 * 60 * 60 * 1000; // confirmation link: 24 h
export const RESET_MS = 60 * 60 * 1000; // password reset link: 1 h

export type GespeicherterToken = { hash: string; expiresAt: string };

export function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function neuerToken(dauerMs: number, jetzt: Date = new Date()): { token: string; gespeichert: GespeicherterToken } {
  const token = randomBytes(32).toString("base64url");
  return { token, gespeichert: { hash: tokenHash(token), expiresAt: new Date(jetzt.getTime() + dauerMs).toISOString() } };
}

export function tokenOk(token: unknown, g: GespeicherterToken | undefined | null, jetzt: Date = new Date()): boolean {
  if (typeof token !== "string" || !token || !g?.hash) return false;
  if (!(new Date(g.expiresAt).getTime() > jetzt.getTime())) return false;
  const ist = Buffer.from(tokenHash(token), "hex");
  const soll = Buffer.from(g.hash, "hex");
  return ist.length === soll.length && timingSafeEqual(ist, soll);
}
