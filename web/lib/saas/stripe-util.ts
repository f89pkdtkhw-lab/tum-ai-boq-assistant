// Small Stripe helpers without the SDK: form encoding for the REST API and webhook signature checks.
import { createHmac, timingSafeEqual } from "node:crypto";

type Wert = string | number | boolean | null | undefined | Wert[] | { [k: string]: Wert };

/** {a: {b: 1}, c: [{d: 2}]} → "a[b]=1&c[0][d]=2", the encoding Stripe's API expects. */
export function formKodieren(daten: Record<string, Wert>): string {
  const teile: string[] = [];
  const geh = (schluessel: string, wert: Wert) => {
    if (wert === undefined || wert === null) return;
    if (Array.isArray(wert)) wert.forEach((w, i) => geh(`${schluessel}[${i}]`, w));
    else if (typeof wert === "object") for (const [k, w] of Object.entries(wert)) geh(`${schluessel}[${k}]`, w);
    else teile.push(`${encodeURIComponent(schluessel)}=${encodeURIComponent(String(wert))}`);
  };
  for (const [k, w] of Object.entries(daten)) geh(k, w);
  return teile.join("&");
}

/** Checks a Stripe-Signature header (t=…,v1=…) against the raw body. Tolerance in seconds (default 5 minutes). */
export function signaturPruefen(rohBody: string, header: string | null, geheimnis: string, toleranz = 300, jetzt = Math.floor(Date.now() / 1000)): boolean {
  if (!header || !geheimnis) return false;
  const felder = header.split(",").map((s) => s.split("=") as [string, string]);
  const t = Number(felder.find(([k]) => k === "t")?.[1]);
  const signaturen = felder.filter(([k]) => k === "v1").map(([, v]) => v);
  if (!Number.isFinite(t) || signaturen.length === 0) return false;
  if (Math.abs(jetzt - t) > toleranz) return false;
  const erwartet = createHmac("sha256", geheimnis).update(`${t}.${rohBody}`).digest("hex");
  const e = Buffer.from(erwartet, "hex");
  return signaturen.some((s) => {
    const b = Buffer.from(s, "hex");
    return b.length === e.length && timingSafeEqual(b, e);
  });
}

/** Test helper and local tooling: builds a valid header for a body. */
export function signaturBauen(rohBody: string, geheimnis: string, t = Math.floor(Date.now() / 1000)): string {
  return `t=${t},v1=${createHmac("sha256", geheimnis).update(`${t}.${rohBody}`).digest("hex")}`;
}
