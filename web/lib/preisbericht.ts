// Full estimated price report (team sketch, level 3): every bill item with its original price, an estimate and the reason.
// Source order: price list (price database) → past projects of the same trade → index/research fallback → unchanged.
// No price is invented. Every priced item carries a low–high range (#225); unpriced items have none.
import type { KalkulationPosition, Position } from "./api";
import type { TradeStat } from "./history-api";
import { gewerkVon } from "./einschaetzung";
import { findePreis, type Preis } from "./preisliste";

export type Quelle = "preisliste" | "historie" | "index" | "recherche" | "unveraendert" | "ohne_preis" | "manuell";
export type PreisVerweis = { titel: string; url?: string | null };
export type PreisAnpassungen = Record<string, number>; // bill-row index → manual unit price
export type PreisZeile = {
  oz: string; kurztext: string; menge: number | null; einheit: string | null;
  war: number | null; geschaetzt: number | null; diff: number | null;
  epWar: number | null; epGeschaetzt: number | null; quelle: Quelle; grund: string;
  werte?: Record<string, string | number>;
  // #225: estimate range (totals and unit prices); null when there is no price
  von: number | null; bis: number | null; epVon: number | null; epBis: number | null;
  verweise: PreisVerweis[];
};
export type Preisbericht = {
  zeilen: PreisZeile[]; war: number; geschaetzt: number; diff: number; geaendert: number;
  von: number | null; bis: number | null;
};

const SCHWELLE = .02; // changes below 2 % count as unchanged

// Relative half-width of the estimate, by source (kept in sync with api/app/pruefung/spannen.py).
export const PREISLISTE_REL = 0.05;
export const UNVERAENDERT_REL = 0.15;
export const FALLBACK_REL = 0.20;
export const HISTORIE_MIN_REL = 0.05;
export const HISTORIE_OHNE_STREUUNG_REL = 0.10;
export const MANUELL_REL = 0.05; // user-entered unit price: as narrow as a list match
export const GENESIS_URL = "https://www-genesis.destatis.de/datenbank/online/table/61261-0001";

export const QUELLE_NAME: Record<Quelle, string> = {
  preisliste: "Price list", historie: "Past projects", index: "Index price",
  recherche: "Web research", unveraendert: "Unchanged", ohne_preis: "No price in the bill", manuell: "Manual",
};

const runde = (n: number) => Math.round(n * 100) / 100;

export function relFuer(quelle: Quelle, streuungProzent: number | null = null): number | null {
  if (quelle === "preisliste" || quelle === "manuell") return MANUELL_REL;
  if (quelle === "unveraendert") return UNVERAENDERT_REL;
  if (quelle === "index" || quelle === "recherche") return FALLBACK_REL;
  if (quelle === "historie") {
    if (streuungProzent === null || !Number.isFinite(streuungProzent)) return HISTORIE_OHNE_STREUUNG_REL;
    return Math.max(Math.abs(streuungProzent) / 100, HISTORIE_MIN_REL);
  }
  return null;
}

/** Unit-price and total range for one estimate. All null when there is no price. */
export function preisSpanne(opts: {
  ep: number | null; menge: number | null; quelle: Quelle;
  epVon?: number | null; epBis?: number | null; streuungProzent?: number | null;
}): { epVon: number | null; epBis: number | null; von: number | null; bis: number | null } {
  const { ep, menge, quelle } = opts;
  if (quelle === "ohne_preis" || (ep === null && opts.epVon == null)) {
    return { epVon: null, epBis: null, von: null, bis: null };
  }
  let ev: number, eb: number;
  if (opts.epVon != null && opts.epBis != null) {
    ev = runde(Math.min(opts.epVon, opts.epBis));
    eb = runde(Math.max(opts.epVon, opts.epBis));
  } else {
    const rel = relFuer(quelle, opts.streuungProzent ?? null);
    if (rel === null || ep === null) return { epVon: null, epBis: null, von: null, bis: null };
    ev = Math.max(0, runde(ep * (1 - rel)));
    eb = runde(ep * (1 + rel));
  }
  return {
    epVon: ev, epBis: eb,
    von: menge === null ? null : runde(menge * ev),
    bis: menge === null ? null : runde(menge * eb),
  };
}

/** Sum of item ranges; priced items without a range contribute the point estimate. */
export function summeSpannen(zeilen: Pick<PreisZeile, "geschaetzt" | "von" | "bis">[]): { von: number | null; bis: number | null } {
  let von = 0, bis = 0, n = 0;
  for (const z of zeilen) {
    if (z.geschaetzt === null) continue;
    n += 1;
    if (z.von !== null && z.bis !== null) { von += z.von; bis += z.bis; }
    else { von += z.geschaetzt; bis += z.geschaetzt; }
  }
  return n === 0 ? { von: null, bis: null } : { von: runde(von), bis: runde(bis) };
}

function verweiseVon(quelle: Quelle, treffer: { item: string } | null, k: KalkulationPosition | undefined): PreisVerweis[] {
  const out: PreisVerweis[] = [];
  if (treffer?.item) out.push({ titel: treffer.item });
  for (const q of k?.preis_quellen ?? []) {
    if (q.titel || q.url) out.push({ titel: q.titel || q.url || "", url: q.url });
  }
  if (quelle === "index" && !out.some((v) => v.url && /genesis/i.test(v.url))) {
    out.push({ titel: "Destatis GENESIS 61261-0001", url: GENESIS_URL });
  }
  return out;
}

function mitSpanne(zeile: Omit<PreisZeile, "von" | "bis" | "epVon" | "epBis">, extra?: {
  epVon?: number | null; epBis?: number | null; streuungProzent?: number | null;
}): PreisZeile {
  const s = preisSpanne({
    ep: zeile.epGeschaetzt, menge: zeile.menge, quelle: zeile.quelle,
    epVon: extra?.epVon, epBis: extra?.epBis, streuungProzent: extra?.streuungProzent,
  });
  return { ...zeile, verweise: zeile.verweise ?? [], ...s };
}

export function mitManuellemEp(zeile: PreisZeile, ep: number): PreisZeile {
  const g = zeile.menge == null ? null : runde(zeile.menge * ep);
  return mitSpanne({
    ...zeile, epGeschaetzt: ep, geschaetzt: g,
    diff: zeile.war == null || g == null ? null : runde(g - zeile.war),
    quelle: "manuell", grund: "Manually adjusted",
  });
}

export function preisbericht(
  positionen: Position[],
  gewerke: TradeStat[] | null,
  preisliste: Preis[],
  kalkulation: KalkulationPosition[] | null = null,
  anpassungen: PreisAnpassungen | null = null,
): Preisbericht {
  const abw = new Map((gewerke ?? []).filter((g) => g.avgDeviation !== null).map((g) => [g.trade, g.avgDeviation as number]));
  const streuung = new Map((gewerke ?? []).map((g) => [g.trade, g.deviationSpread ?? null]));
  const fallback = new Map<string, KalkulationPosition>();
  for (const k of kalkulation ?? []) if (!fallback.has(k.oz)) fallback.set(k.oz, k);
  const zeilenRoh = positionen.map((p, i): PreisZeile => {
    const war = p.gp ?? (p.menge !== null && p.ep !== null ? p.menge * p.ep : null);
    const epWar = p.ep ?? (war !== null && p.menge ? war / p.menge : null);
    const basis = { oz: p.oz, kurztext: p.kurztext, menge: p.menge, einheit: p.einheit, war, epWar };
    const ep = (g: number) => (p.menge ? runde(g / p.menge) : null);
    const treffer = p.menge !== null ? findePreis(preisliste, p.kurztext, p.einheit) : null;
    const k = fallback.get(p.oz) ?? kalkulation?.[i];
    const refs = (quelle: Quelle) => verweiseVon(quelle, treffer, k);
    if (treffer && p.menge !== null) {
      const g = runde(treffer.preis * p.menge);
      return mitSpanne({ ...basis, geschaetzt: g, diff: war === null ? null : runde(g - war), epGeschaetzt: treffer.preis, quelle: "preisliste", grund: "Price list: {item} {preis} per {unit}", werte: { item: treffer.item, preis: treffer.preis, unit: treffer.unit || p.einheit || "" }, verweise: refs("preisliste") });
    }
    const d = abw.get(gewerkVon(p.kurztext) ?? "");
    if (war !== null && d !== undefined && Math.abs(d) / 100 >= SCHWELLE) {
      const g = runde(war * (1 + d / 100));
      return mitSpanne({ ...basis, geschaetzt: g, diff: runde(g - war), epGeschaetzt: ep(g), quelle: "historie", grund: "Past projects: {trade} {d} %", werte: { trade: gewerkVon(p.kurztext) ?? "", d: `${d > 0 ? "+" : ""}${Math.round(d)}` }, verweise: refs("historie") }, { streuungProzent: streuung.get(gewerkVon(p.kurztext) ?? "") ?? null });
    }
    if (k && (k.treffer === "index" || k.treffer === "recherche") && k.ep != null) {
      const g = k.gp ?? (p.menge !== null ? runde(k.ep * p.menge) : null);
      return mitSpanne({
        ...basis, geschaetzt: g, diff: war === null || g === null ? null : runde(g - war),
        epGeschaetzt: k.ep, quelle: k.treffer,
        grund: k.treffer === "index" ? "Index price: {von}–{bis} per {unit}" : "Web research: {von}–{bis} per {unit}",
        werte: { von: k.ep_von ?? "", bis: k.ep_bis ?? "", unit: p.einheit || "" },
        verweise: refs(k.treffer),
      }, { epVon: k.ep_von, epBis: k.ep_bis });
    }
    if (war === null) return mitSpanne({ ...basis, geschaetzt: null, diff: null, epGeschaetzt: null, quelle: "ohne_preis", grund: "No price in the bill", verweise: refs("ohne_preis") });
    return mitSpanne({ ...basis, geschaetzt: war, diff: 0, epGeschaetzt: epWar, quelle: "unveraendert", grund: "No reason to change", verweise: refs("unveraendert") });
  });
  const zeilen = zeilenRoh.map((z, i) => {
    const ep = anpassungen?.[String(i)];
    return typeof ep === "number" && Number.isFinite(ep) ? mitManuellemEp(z, ep) : z;
  });
  const summe = (f: (z: PreisZeile) => number | null) => runde(zeilen.reduce((s, z) => s + (f(z) ?? 0), 0));
  const war = summe((z) => z.war);
  const geschaetzt = summe((z) => z.geschaetzt);
  const { von, bis } = summeSpannen(zeilen);
  return { zeilen, war, geschaetzt, diff: runde(geschaetzt - war), von, bis,
    geaendert: zeilen.filter((z) => z.war && z.diff !== null && Math.abs(z.diff) / Math.abs(z.war) >= SCHWELLE).length };
}
