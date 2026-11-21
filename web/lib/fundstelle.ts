// #170: where a finding's item stands in the uploaded original. Pure helpers, no React, so node --test covers them.
// The importers add `quelle` per item (api/app/modelle.py PositionQuelle); JSON bills and older reports have none,
// then the OZ alone is the location.
import type { Position, PositionQuelle } from "./api";

export type Format = "pdf" | "excel" | "gaeb" | "json" | "andere";
type Sprache = "en" | "de";

export function formatVon(dateiname: string): Format {
  const endung = dateiname.slice(dateiname.lastIndexOf(".") + 1).toLowerCase();
  if (endung === "pdf") return "pdf";
  if (endung === "xlsx" || endung === "xls") return "excel";
  if (/^[xd]8[1-6]$/.test(endung)) return "gaeb";
  if (endung === "json") return "json";
  return "andere";
}

const DE: Record<string, string> = {
  "page {n}": "Seite {n}", "line {n}": "Zeile {n}", "sheet “{name}”": "Blatt „{name}“", "row {n}": "Zeile {n}",
  "record line {n}": "Satzzeile {n}", "Source": "Fundstelle", "Open PDF at page {n}": "PDF auf Seite {n} öffnen",
  "Show in BoQ": "Im LV zeigen", "not in the BoQ": "nicht im LV",
  "The original file is only kept in this browser tab right after the upload; page and line still name the place.":
    "Die Originaldatei bleibt nur direkt nach dem Hochladen in diesem Tab verfügbar; Seite und Zeile nennen die Stelle trotzdem.",
};

export function text(sprache: Sprache, schluessel: string, werte: Record<string, string | number> = {}): string {
  const vorlage = sprache === "de" ? DE[schluessel] ?? schluessel : schluessel;
  return vorlage.replace(/\{(\w+)\}/g, (_, k: string) => String(werte[k] ?? `{${k}}`));
}

/** Location parts in reading order, e.g. ["lv.pdf", "page 2", "line 8", "OZ 01.02"]. */
export function fundstelleTeile(datei: string, oz: string, position: Position | undefined, sprache: Sprache = "en"): string[] {
  const q = position?.quelle;
  const teile = datei ? [datei] : [];
  if (q?.seite) teile.push(text(sprache, "page {n}", { n: q.seite }));
  if (q?.blatt) teile.push(text(sprache, "sheet “{name}”", { name: q.blatt }));
  if (q?.zeile) {
    const art = q.seite ? "line {n}" : q.blatt ? "row {n}" : formatVon(datei) === "gaeb" ? "record line {n}" : "line {n}";
    teile.push(text(sprache, art, { n: q.zeile }));
  }
  teile.push(`OZ ${oz}${position ? "" : ` (${text(sprache, "not in the BoQ")})`}`);
  return teile;
}

/**
 * PDF open parameters for the browser viewer (Chrome and Firefox/pdf.js): the page and, with a box, a 100 % zoom whose
 * top edge sits just above the item. The box uses a top-left origin; the viewer expects PDF user space (bottom-left).
 */
export function pdfAnker(quelle: PositionQuelle | undefined): string {
  if (!quelle?.seite) return "";
  const anker = `#page=${quelle.seite}`;
  if (!quelle.bbox || !quelle.seite_groesse) return anker;
  const hoehe = quelle.seite_groesse[1];
  const oben = Math.min(hoehe, Math.max(0, Math.round(hoehe - quelle.bbox[1] + 24)));
  return `${anker}&zoom=100,0,${oben}`;
}

/** The PDF link for an item, or null when the original is not at hand or the item has no page. */
export function pdfLink(originalUrl: string | null | undefined, position: Position | undefined): string | null {
  const anker = pdfAnker(position?.quelle);
  return originalUrl && anker ? originalUrl + anker : null;
}
