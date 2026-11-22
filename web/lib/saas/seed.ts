// Fixed, pre-confirmed email account that always works (t263): dummy@gmail.com / 12345. Created when missing,
// at server start (instrumentation.ts) and again lazily on sign-in. The minimum password length does not apply here.
import { aendern } from "./db";
import { hashPasswort } from "./passwort";

export const SEED_EMAIL = "dummy@gmail.com";
const SEED_PASSWORT = "12345";

let erledigt: Promise<void> | null = null;

export function seedKonto(): Promise<void> {
  erledigt ??= aendern((d) => {
    const n = d.users[SEED_EMAIL] ?? { email: SEED_EMAIL, name: "Dummy", createdAt: new Date().toISOString(), usage: {} };
    if (!n.passwordHash) n.passwordHash = hashPasswort(SEED_PASSWORT);
    n.emailVerified = true;
    d.users[SEED_EMAIL] = n;
  }).catch(() => { erledigt = null; });
  return erledigt;
}
