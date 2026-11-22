// Email + password accounts: scrypt hashes (node:crypto, no extra package). Stored per user in saas.json
// (web/.data, git-ignored) as "scrypt$N$r$p$salt$hash" (base64url). Pure apart from crypto, so node --test can import it.
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

const N = 16384, R = 8, P = 1, LAENGE = 64;
export const MIN_PASSWORT = 8;

export function passwortOk(pw: unknown): pw is string {
  return typeof pw === "string" && pw.length >= MIN_PASSWORT && pw.length <= 200;
}

export function hashPasswort(pw: string): string {
  const salt = randomBytes(16);
  const hash = scryptSync(pw.normalize("NFKC"), salt, LAENGE, { N, r: R, p: P });
  return ["scrypt", N, R, P, salt.toString("base64url"), hash.toString("base64url")].join("$");
}

export function pruefePasswort(pw: string, gespeichert: string | undefined | null): boolean {
  if (typeof pw !== "string" || !gespeichert) return false;
  const teile = gespeichert.split("$");
  if (teile.length !== 6 || teile[0] !== "scrypt") return false;
  const [n, r, p] = teile.slice(1, 4).map(Number);
  if (![n, r, p].every((x) => Number.isInteger(x) && x > 0) || n > 1 << 20) return false;
  const soll = Buffer.from(teile[5], "base64url");
  if (soll.length === 0) return false;
  try {
    const ist = scryptSync(pw.normalize("NFKC"), Buffer.from(teile[4], "base64url"), soll.length, { N: n, r, p, maxmem: 256 * n * r + 1024 * 1024 });
    return timingSafeEqual(ist, soll);
  } catch {
    return false;
  }
}
