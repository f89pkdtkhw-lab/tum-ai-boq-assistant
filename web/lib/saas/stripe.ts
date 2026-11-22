// Stripe REST calls via fetch (no SDK). Reads STRIPE_SECRET_KEY only from the environment; never logs it.
import { formKodieren } from "./stripe-util";

export function stripeAktiv(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY);
}

export class StripeFehler extends Error {}

export async function stripe<T = Record<string, unknown>>(methode: "GET" | "POST", pfad: string, daten: Record<string, unknown> = {}): Promise<T> {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new StripeFehler("Stripe is not configured.");
  const qs = formKodieren(daten as never);
  const url = `https://api.stripe.com/v1/${pfad}${methode === "GET" && qs ? `?${qs}` : ""}`;
  const r = await fetch(url, {
    method: methode,
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: methode === "POST" ? qs : undefined,
    cache: "no-store",
  });
  const json = (await r.json().catch(() => ({}))) as { error?: { message?: string } };
  if (!r.ok) throw new StripeFehler(json.error?.message || `Stripe error ${r.status}`);
  return json as T;
}

const preisCache = new Map<string, string>();

/** Price ID for one of our lookup keys (created in test mode on the "Print Pool" account, see docs/abo.md). */
export async function preisId(lookupKey: string): Promise<string> {
  const c = preisCache.get(lookupKey);
  if (c) return c;
  const r = await stripe<{ data: { id: string }[] }>("GET", "prices", { lookup_keys: [lookupKey], active: true, limit: 1 });
  const id = r.data[0]?.id;
  if (!id) throw new StripeFehler(`No Stripe price with lookup key ${lookupKey}.`);
  preisCache.set(lookupKey, id);
  return id;
}
