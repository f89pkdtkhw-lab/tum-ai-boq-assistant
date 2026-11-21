// Price database page (issue #134, epic #93 D5): priced bill or price list → preview → POST /api/db/preise.
import type { NeuerPreis, PreisEintrag, Preisliste } from "./api";
import { routeFehlt } from "./regelwerk";

export type VorschauZeile = NeuerPreis & { quelle: string; gueltig: boolean };

/** One preview row per price-list entry; item falls back to the OZ, invalid rows stay visible but are not saved. */
export function vorschau(p: Preisliste): VorschauZeile[] {
  return p.eintraege.map((e) => {
    const item = (e.kurztext || e.oz || "").trim();
    const unit = (e.einheit || "").trim();
    return { item, unit, price_per_unit: e.ep, quelle: e.quelle, gueltig: item !== "" && unit !== "" && Number.isFinite(e.ep) && e.ep >= 0 };
  });
}

/** Body of POST /api/db/preise: valid rows only; same item+unit keeps the last price (the backend updates too). */
export function speicherBody(zeilen: readonly VorschauZeile[]): NeuerPreis[] {
  const nachSchluessel = new Map<string, NeuerPreis>();
  for (const z of zeilen) {
    if (z.gueltig) nachSchluessel.set(`${z.item.toLocaleLowerCase("de")}\u0000${z.unit}`, { item: z.item, unit: z.unit, price_per_unit: z.price_per_unit });
  }
  return [...nachSchluessel.values()];
}

/** Query string of GET /api/db/preise. */
export function abfrage(item: string, unit: string, limit = 200): string {
  const q = new URLSearchParams();
  if (item.trim()) q.set("item", item.trim());
  if (unit.trim()) q.set("unit", unit.trim());
  q.set("limit", String(limit));
  return `?${q}`;
}

/** Case-insensitive search by item text and exact-ish unit, also applied in the browser. */
export function filtere(eintraege: readonly PreisEintrag[], item: string, unit: string): PreisEintrag[] {
  const i = item.trim().toLocaleLowerCase("de");
  const u = unit.trim().toLocaleLowerCase("de");
  return eintraege.filter((e) => (!i || e.item.toLocaleLowerCase("de").includes(i)) && (!u || e.unit.toLocaleLowerCase("de") === u));
}

/** Readable error; a missing route (404) explains that the backend part is not there yet. */
export function preisFehler(schritt: "import" | "laden" | "speichern", fehler: unknown): string {
  if (routeFehlt(fehler)) {
    return schritt === "import"
      ? "This backend cannot read price lists yet. Nothing was uploaded."
      : schritt === "speichern"
        ? "The price database is not available on this backend yet. Nothing was saved."
        : "The price database is not available on this backend yet.";
  }
  const grund = fehler instanceof TypeError ? "Cannot connect to the backend." : fehler instanceof Error && fehler.message ? fehler.message : "Unknown error.";
  return { import: "Could not read the file: ", laden: "Could not load the price database: ", speichern: "Could not save the prices: " }[schritt] + grund;
}
