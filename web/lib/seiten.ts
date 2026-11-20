/**
 * Pure paging for the review report tables (issue #67).
 * Pages are 0-based internally; the UI shows them 1-based.
 * Paging runs after every filter, on the already filtered list.
 */

export const SEITENGROESSEN = [50, 100, 250] as const;
export const STANDARD_SEITENGROESSE = 100;

/**
 * Current page together with the filter key it was chosen for.
 * If the filters change, the stored page no longer applies and page 0 is shown,
 * so no effect is needed to reset it.
 */
export type Blatt = { schluessel: string; seite: number };

export type Seite = {
  /** 0-based page after clamping. */
  seite: number;
  /** Number of pages, at least 1 (an empty list has one empty page). */
  seiten: number;
  /** First row index on this page (inclusive). */
  von: number;
  /** Row index after the last row on this page (exclusive). */
  bis: number;
  gesamt: number;
};

function gueltigeGroesse(groesse: number) {
  return Number.isFinite(groesse) && groesse >= 1 ? Math.floor(groesse) : STANDARD_SEITENGROESSE;
}

export function seitenAnzahl(gesamt: number, groesse: number): number {
  return Math.max(1, Math.ceil(Math.max(0, gesamt) / gueltigeGroesse(groesse)));
}

/** Clamps a page into 0 … seiten-1; NaN becomes 0, Infinity the last page. */
export function begrenze(seite: number, gesamt: number, groesse: number): number {
  if (Number.isNaN(seite)) return 0;
  return Math.min(Math.max(0, Math.floor(seite)), seitenAnzahl(gesamt, groesse) - 1);
}

/** Bounds of a page in a list of `gesamt` rows. O(1). */
export function seiteVon(gesamt: number, seite: number, groesse: number): Seite {
  const g = gueltigeGroesse(groesse);
  const n = Math.max(0, gesamt);
  const s = begrenze(seite, n, g);
  const von = Math.min(s * g, n);
  return { seite: s, seiten: seitenAnzahl(n, g), von, bis: Math.min(von + g, n), gesamt: n };
}

/** Visible rows of a page; O(page size), never more than `groesse` rows. */
export function ausschnitt<T>(liste: readonly T[], seite: Seite): T[] {
  return liste.slice(seite.von, seite.bis);
}

/** Page that contains row `index`; a negative index means page 0. */
export function seiteMitIndex(index: number, groesse: number): number {
  return index < 0 ? 0 : Math.floor(index / gueltigeGroesse(groesse));
}

/** Page of the first row matching `trifft`, or null if no row matches. One pass, O(n). */
export function seiteFuer<T>(liste: readonly T[], trifft: (zeile: T) => boolean, groesse: number): number | null {
  const index = liste.findIndex(trifft);
  return index < 0 ? null : seiteMitIndex(index, groesse);
}

/** Page to show for the current filter key: the stored page, or 0 after a filter change. */
export function aktuelleSeite(blatt: Blatt, schluessel: string): number {
  return blatt.schluessel === schluessel ? blatt.seite : 0;
}

/** After a page size change, the page that still contains the first visible row. */
export function seiteNachGroesse(seite: Seite, neueGroesse: number): number {
  return seiteMitIndex(seite.von, neueGroesse);
}

/** Text "rows X–Y of Z" (1-based, en dash); "no rows" for an empty list. */
export function zeilenText(seite: Seite, format: (n: number) => string = String): string {
  if (seite.gesamt === 0) return "no rows";
  return `rows ${format(seite.von + 1)}–${format(seite.bis)} of ${format(seite.gesamt)}`;
}
