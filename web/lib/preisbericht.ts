// Full estimated price report (team sketch, level 3): every bill item with its original price, an estimate and the reason.
// Source order: price list (price database) → past projects of the same trade → unchanged. No price is invented.
import type { Position } from "./api";
import type { TradeStat } from "./history-api";
import { gewerkVon } from "./einschaetzung";
import { findePreis, type Preis } from "./preisliste";

export type Quelle = "preisliste" | "historie" | "unveraendert" | "ohne_preis";
export type PreisZeile = { oz: string; kurztext: string; menge: number | null; einheit: string | null; war: number | null; geschaetzt: number | null; diff: number | null; epWar: number | null; epGeschaetzt: number | null; quelle: Quelle; grund: string; werte?: Record<string, string | number> };
export type Preisbericht = { zeilen: PreisZeile[]; war: number; geschaetzt: number; diff: number; geaendert: number };

const SCHWELLE = .02; // changes below 2 % count as unchanged

export function preisbericht(positionen: Position[], gewerke: TradeStat[] | null, preisliste: Preis[]): Preisbericht {
  const abw = new Map((gewerke ?? []).filter((g) => g.avgDeviation !== null).map((g) => [g.trade, g.avgDeviation as number]));
  const zeilen = positionen.map((p): PreisZeile => {
    const war = p.gp ?? (p.menge !== null && p.ep !== null ? p.menge * p.ep : null);
    const epWar = p.ep ?? (war !== null && p.menge ? war / p.menge : null);
    const basis = { oz: p.oz, kurztext: p.kurztext, menge: p.menge, einheit: p.einheit, war, epWar };
    const ep = (g: number) => (p.menge ? Math.round((g / p.menge) * 100) / 100 : null);
    if (war === null) return { ...basis, geschaetzt: null, diff: null, epGeschaetzt: null, quelle: "ohne_preis", grund: "No price in the bill" };
    const treffer = p.menge !== null ? findePreis(preisliste, p.kurztext, p.einheit) : null;
    if (treffer && p.menge !== null) {
      const g = Math.round(treffer.preis * p.menge * 100) / 100;
      return { ...basis, geschaetzt: g, diff: g - war, epGeschaetzt: treffer.preis, quelle: "preisliste", grund: "Price list: {item} {preis} per {unit}", werte: { item: treffer.item, preis: treffer.preis, unit: treffer.unit || p.einheit || "" } };
    }
    const d = abw.get(gewerkVon(p.kurztext) ?? "");
    if (d !== undefined && Math.abs(d) / 100 >= SCHWELLE) {
      const g = Math.round(war * (1 + d / 100) * 100) / 100;
      return { ...basis, geschaetzt: g, diff: g - war, epGeschaetzt: ep(g), quelle: "historie", grund: "Past projects: {trade} {d} %", werte: { trade: gewerkVon(p.kurztext) ?? "", d: `${d > 0 ? "+" : ""}${Math.round(d)}` } };
    }
    return { ...basis, geschaetzt: war, diff: 0, epGeschaetzt: epWar, quelle: "unveraendert", grund: "No reason to change" };
  });
  const summe = (f: (z: PreisZeile) => number | null) => Math.round(zeilen.reduce((s, z) => s + (f(z) ?? 0), 0) * 100) / 100;
  const war = summe((z) => z.war);
  const geschaetzt = summe((z) => z.geschaetzt);
  return { zeilen, war, geschaetzt, diff: Math.round((geschaetzt - war) * 100) / 100,
    geaendert: zeilen.filter((z) => z.war && z.diff !== null && Math.abs(z.diff) / Math.abs(z.war) >= SCHWELLE).length };
}
