// Offline demo fallback (#61): a committed report snapshot for the synthetic example BoQ,
// refreshed with `node web/scripts/offline-snapshot.mjs` while the API runs.
import type { Pruefbericht } from "./api";

export const OFFLINE_BERICHT_URL = "/offline/beispiel-bericht.json";

/**
 * Offer the snapshot only when the backend itself failed: unreachable, network error or 5xx.
 * `api.ts` keeps only the message, so 5xx is recognised by its "Request failed (5xx)" text.
 */
export function bietetOffline(fehler: unknown, erreichbar: boolean): boolean {
  if (!erreichbar || fehler instanceof TypeError) return true;
  return fehler instanceof Error && /\(5\d\d\)/.test(fehler.message);
}

/** Checks the snapshot shape so a broken file fails loudly instead of rendering an empty report. */
export function pruefeOfflineBericht(daten: unknown): Pruefbericht {
  const bericht = daten as Pruefbericht;
  if (!Array.isArray(bericht?.lv?.positionen) || bericht.lv.positionen.length === 0) {
    throw new Error("The offline example has no items.");
  }
  if (!Array.isArray(bericht.findings) || typeof bericht.kennzahlen !== "object" || bericht.kennzahlen === null) {
    throw new Error("The offline example is not a review report.");
  }
  const oz = new Set(bericht.lv.positionen.map((p) => p.oz));
  const fremd = bericht.findings.find((f) => !oz.has(f.oz));
  if (fremd) throw new Error(`The offline example cites item ${fremd.oz}, which is not in its BoQ.`);
  return bericht;
}

export async function ladeOfflineBericht(): Promise<Pruefbericht> {
  const antwort = await fetch(OFFLINE_BERICHT_URL);
  if (!antwort.ok) throw new Error(`The offline example could not be loaded (${antwort.status}).`);
  return pruefeOfflineBericht(await antwort.json());
}
