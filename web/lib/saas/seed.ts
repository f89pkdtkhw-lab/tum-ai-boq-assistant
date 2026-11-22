// Fixed, pre-confirmed email account that always works (t263): dummy@gmail.com / 12345. Created when missing,
// at server start (instrumentation.ts) and again lazily on sign-in. The minimum password length does not apply here.
// The seed account is always on the highest plan (Company), including when the local store already has it as Free.
import { aendern } from "./db";
import { hashPasswort } from "./passwort";
import { mitSeedAbo, SEED_EMAIL } from "./seed-plan";

const SEED_PASSWORT = "12345";

let erledigt: Promise<void> | null = null;

export { mitSeedAbo, SEED_EMAIL, SEED_PLAN } from "./seed-plan";

export function seedKonto(): Promise<void> {
  erledigt ??= aendern((d) => {
    const n = d.users[SEED_EMAIL] ?? { email: SEED_EMAIL, name: "Dummy", createdAt: new Date().toISOString(), usage: {} };
    if (!n.passwordHash) n.passwordHash = hashPasswort(SEED_PASSWORT);
    d.users[SEED_EMAIL] = mitSeedAbo(n);
  }).catch(() => { erledigt = null; });
  return erledigt;
}
