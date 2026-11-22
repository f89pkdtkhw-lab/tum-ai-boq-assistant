// Optional regulation document next to the bill (issue #102, epic #93 B3) and shared helpers for attachments.
import type { Bewertungsmodell, LV, Preisliste, Regelwerk } from "./api";

export const MAX_BEILAGE_BYTES = 10 * 1024 * 1024; // same limit as MAX_UPLOAD_BYTES in api/app/main.py
export const REGELWERK_FORMATE = [".pdf", ".txt", ".md"];

function endung(name: string) {
  const punkt = name.lastIndexOf(".");
  return punkt < 0 ? "" : name.slice(punkt).toLowerCase();
}

/** Local check before upload: readable reason or null. */
export function beilageFehler(datei: { name: string; size: number }, formate: readonly string[], art: string): string | null {
  if (!formate.includes(endung(datei.name))) {
    return `${art} “${datei.name}” has an unsupported format. Allowed: ${formate.map((f) => f.slice(1).toUpperCase()).join(", ")}.`;
  }
  if (datei.size === 0) return `${art} “${datei.name}” is empty.`;
  if (datei.size > MAX_BEILAGE_BYTES) return `${art} “${datei.name}” is larger than 10 MiB and was not uploaded.`;
  return null;
}

/** The backend does not offer this route yet (older backend): fall back instead of failing. */
export function routeFehlt(fehler: unknown): boolean {
  return typeof fehler === "object" && fehler !== null && (fehler as { status?: number }).status === 404;
}

/** Error text for a failed attachment import, naming the file. */
export function importFehlerText(art: string, dateiname: string, fehler: unknown): string {
  const grund = fehler instanceof TypeError ? "Cannot connect to the backend."
    : fehler instanceof Error && fehler.message ? fehler.message : "Unknown error.";
  return `${art} “${dateiname}” could not be imported: ${grund}`;
}

const plural = (n: number, eins: string, viele: string) => `${n} ${n === 1 ? eins : viele}`;

export function regelwerkText(r: Regelwerk): string {
  const teile = [plural(r.normverweise.length, "reference", "references"), plural(r.kennwerte.length, "key value", "key values")];
  if (r.warnungen.length > 0) teile.push(plural(r.warnungen.length, "warning", "warnings"));
  return `${r.dateiname}: ${teile.join(", ")}`;
}

/** Always /api/lv/analyse (#167): without attachments the price database still prices the bill and the
 *  estimated bill is built; the findings are the same as /api/lv/pruefen. */
export function analyseAnfrage(lv: LV, regelwerk: Regelwerk | null, preisliste: Preisliste | null,
  bewertungsmodell: Bewertungsmodell = "ausgewogen") {
  return { lv, regelwerk, preisliste, bewertungsmodell };
}
