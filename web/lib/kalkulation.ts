// Priced bill in the report (issue #116, epic #93 "Price calculation"): original vs estimated bill.
import type {
  AenderungsStatus, Anpassung, GeschaetztesLv, GeschaetztePosition, Kalkulation, KalkulationPosition, Position,
  PreisQuelle, Pruefbericht,
} from "./api";

export type Zeile = {
  oz: string; kurztext: string; einheit: string | null; status: AenderungsStatus;
  mengeAlt: number | null; mengeNeu: number | null; ep: number | null; gpAlt: number | null; gpNeu: number | null;
  grund: string; findingId: string | null; freigabe: boolean; ohnePreis: boolean;
  /** t237: the EP is a fallback estimate (index price or web research), null for list/DB prices. */
  schaetzung?: Schaetzung | null;
  von?: number | null; bis?: number | null;
};

export type Schaetzung = {
  art: "index" | "recherche"; von: number | null; bis: number | null; quellen: PreisQuelle[]; hinweis: string;
};

/** Estimate details of a calculation row; null when the price came from the list or the database. */
export function schaetzungVon(p: KalkulationPosition | undefined): Schaetzung | null {
  if (!p || !p.geschaetzt || (p.treffer !== "index" && p.treffer !== "recherche")) return null;
  return { art: p.treffer, von: p.ep_von ?? null, bis: p.ep_bis ?? null, quellen: p.preis_quellen ?? [], hinweis: p.schaetzung_hinweis ?? "" };
}

/** Badge label for an estimated price (English key, translated by the caller). */
export function schaetzungLabel(art: Schaetzung["art"]): string {
  return art === "index" ? "Estimated – index" : "Estimated – research";
}

/** Label next to the colour, so the status is never shown by colour alone. */
export const STATUS: { wert: AenderungsStatus; name: string; marke: string }[] = [
  { wert: "added", name: "Added", marke: "+ new" },
  { wert: "removed", name: "Removed", marke: "− removed" },
  { wert: "updated", name: "Updated", marke: "old → new" },
  { wert: "unchanged", name: "Unchanged", marke: "unchanged" },
];

export function statusInfo(status: AenderungsStatus) {
  return STATUS.find((s) => s.wert === status) ?? STATUS[3];
}

/** True when the report carries anything to show; otherwise the section stays hidden. */
export function hatKalkulation(bericht: Pick<Pruefbericht, "kalkulation" | "geschaetztes_lv">): boolean {
  return Boolean(bericht.kalkulation || bericht.geschaetztes_lv);
}

/**
 * One row per position. With an estimated bill (B8) its rows are used, removed items included;
 * with only the priced original (B6) every row is "unchanged".
 */
export function kalkulationsZeilen(bericht: Pick<Pruefbericht, "lv" | "kalkulation" | "anpassungen" | "geschaetztes_lv">): Zeile[] {
  const { kalkulation: k, geschaetztes_lv: g } = bericht;
  const treffer = new Map<string, string>();
  const kpos = new Map<string, KalkulationPosition>();
  for (const p of k?.positionen ?? []) if (!treffer.has(p.oz)) { treffer.set(p.oz, p.treffer); kpos.set(p.oz, p); }
  if (g) {
    const anpassungen = new Map<string, Anpassung>((bericht.anpassungen ?? []).map((a) => [a.id, a]));
    return g.positionen.map((p) => ({
      oz: p.oz, kurztext: p.kurztext, einheit: p.einheit, status: p.status,
      mengeAlt: p.menge_alt, mengeNeu: p.menge_neu, ep: p.ep, gpAlt: p.gp_alt, gpNeu: p.gp_neu,
      grund: p.grund, freigabe: p.freigabe_noetig,
      findingId: p.anpassung_ids.map((id) => anpassungen.get(id)?.finding_id).find((id) => id) ?? null,
      ohnePreis: p.ep === null || treffer.get(p.oz) === "kein_treffer",
      schaetzung: p.status === "added" ? null : schaetzungVon(kpos.get(p.oz)),
      von: p.gp_von ?? null, bis: p.gp_bis ?? null,
    }));
  }
  if (!k) return [];
  const kurztexte = new Map<string, string>();
  for (const p of bericht.lv.positionen) if (!kurztexte.has(p.oz)) kurztexte.set(p.oz, p.kurztext);
  return k.positionen.map((p) => ({
    oz: p.oz, kurztext: p.kurztext || kurztexte.get(p.oz) || "", einheit: p.einheit, status: "unchanged",
    mengeAlt: p.menge, mengeNeu: p.menge, ep: p.ep, gpAlt: p.gp, gpNeu: p.gp,
    grund: "", findingId: null, freigabe: false, ohnePreis: p.ep === null || p.treffer === "kein_treffer",
    schaetzung: schaetzungVon(p),
  }));
}

export function zaehleStatus(zeilen: readonly Zeile[]): Record<AenderungsStatus, number> {
  const anzahl = { unchanged: 0, updated: 0, added: 0, removed: 0 };
  for (const z of zeilen) anzahl[z.status]++;
  return anzahl;
}

export function filtereStatus(zeilen: readonly Zeile[], status: AenderungsStatus | null): Zeile[] {
  return status === null ? [...zeilen] : zeilen.filter((z) => z.status === status);
}

export type Kosten = {
  originalNetto: number | null; geschaetztNetto: number | null; differenz: number | null; prozent: number | null;
  bruttoOriginal: number | null; bruttoGeschaetzt: number | null; ohnePreis: number; vollstaendig: boolean | null;
  geschaetzt: number; von: number | null; bis: number | null;
};

/** Cost tiles. Missing values stay null ("unknown"), never 0. */
export function kosten(k: Kalkulation | null | undefined, g: GeschaetztesLv | null | undefined, zeilen: readonly Zeile[]): Kosten {
  const originalNetto = k?.summe_netto ?? (g ? g.summe_netto - g.differenz_netto : null);
  return {
    originalNetto,
    geschaetztNetto: g?.summe_netto ?? null,
    differenz: g?.differenz_netto ?? null,
    prozent: g?.differenz_prozent ?? null,
    bruttoOriginal: k?.summe_brutto ?? null,
    bruttoGeschaetzt: g?.summe_brutto ?? null,
    ohnePreis: k?.ohne_preis ?? zeilen.filter((z) => z.ohnePreis).length,
    vollstaendig: k?.vollstaendig ?? null,
    geschaetzt: k?.geschaetzt_anzahl ?? zeilen.filter((z) => z.schaetzung).length,
    von: g?.summe_netto_von ?? null, bis: g?.summe_netto_bis ?? null,
  };
}

/** "old → new" when a value changed; one value otherwise. Added rows show the new, removed rows the old value. */
export function aenderung(alt: number | null, neu: number | null, status: AenderungsStatus, format: (n: number) => string): string {
  const f = (n: number | null) => (n === null ? "unknown" : format(n));
  if (status === "added") return f(neu);
  if (status === "removed" || alt === neu) return f(alt);
  return `${f(alt)} → ${f(neu)}`;
}

/** Signed amount with a real minus sign, e.g. "+€250.00" / "−€80.00". */
export function mitVorzeichen(wert: number, format: (n: number) => string): string {
  if (wert === 0) return format(0);
  return `${wert > 0 ? "+" : "−"}${format(Math.abs(wert))}`;
}

const runde = (n: number) => Math.round(n * 100) / 100;

/**
 * Synthetic price calculation for the preview page (`/bericht-vorschau?zustand=kalkulation`) until B6/B8 deliver it.
 * Invented prices only; built from the example BoQ that is itself synthetic.
 */
export function demoKalkulation(positionen: readonly Position[]): Pick<Pruefbericht, "kalkulation" | "anpassungen" | "geschaetztes_lv"> {
  const mwst = 0.19;
  const kpos = positionen.map((p, i) => {
    const ohne = i === 3;
    const ep = ohne ? null : runde(p.ep ?? 10 + (i % 7) * 4.5);
    const gp = ep === null || p.menge === null ? null : runde(ep * p.menge);
    return {
      oz: p.oz, menge: p.menge, einheit: p.einheit, ep, gp, ep_lv: p.ep, gp_lv: p.gp,
      treffer: ohne ? "kein_treffer" as const : "text" as const, preis_eintrag: ohne ? null : `demo-${i + 1}`,
      aehnlichkeit: ohne ? null : 1, in_summe: gp !== null,
    };
  });
  const summeAlt = runde(kpos.reduce((s, p) => s + (p.gp ?? 0), 0));
  const anpassungen: Anpassung[] = [];
  const gpos: GeschaetztePosition[] = kpos.map((p, i) => {
    const basis = {
      oz: p.oz, kurztext: positionen[i].kurztext, einheit: p.einheit, menge_alt: p.menge, ep: p.ep,
      gp_alt: p.gp, anpassung_ids: [] as string[], grund: "", freigabe_noetig: false,
    };
    if (i === 1 && p.menge !== null) {
      const menge = runde(p.menge * 1.2);
      anpassungen.push({ id: "a1", oz: p.oz, art: "menge", menge_alt: p.menge, menge_neu: menge, position: null, grund: "Demo: quantity below the comparable layer", bericht: "vergleich", finding_id: null });
      return { ...basis, status: "updated", menge_neu: menge, gp_neu: p.ep === null ? null : runde(p.ep * menge), anpassung_ids: ["a1"], grund: "Demo: quantity below the comparable layer" };
    }
    if (i === 2) {
      anpassungen.push({ id: "a2", oz: p.oz, art: "entfernen", menge_alt: p.menge, menge_neu: 0, position: null, grund: "Demo: duplicate of another item", bericht: "regelwerk", finding_id: null });
      return { ...basis, status: "removed", menge_neu: 0, gp_neu: 0, anpassung_ids: ["a2"], grund: "Demo: duplicate of another item", freigabe_noetig: true };
    }
    return { ...basis, status: "unchanged", menge_neu: p.menge, gp_neu: p.gp };
  });
  anpassungen.push({ id: "a3", oz: "99.9999", art: "hinzufuegen", menge_alt: null, menge_neu: 12, position: null, grund: "Demo: missing edge insulation", bericht: "was_wenn", finding_id: null });
  gpos.push({ oz: "99.9999", status: "added", kurztext: "Demo: edge insulation strip", einheit: "m", menge_alt: null, menge_neu: 12, ep: 4.5, gp_alt: null, gp_neu: 54, anpassung_ids: ["a3"], grund: "Demo: missing edge insulation", freigabe_noetig: true });
  const summeNeu = runde(gpos.reduce((s, p) => s + (p.gp_neu ?? 0), 0));
  const differenz = runde(summeNeu - summeAlt);
  const anzahl = { unchanged: 0, updated: 0, added: 0, removed: 0 };
  for (const p of gpos) anzahl[p.status]++;
  return {
    kalkulation: {
      waehrung: "EUR", mwst_satz: mwst, positionen: kpos, summe_netto: summeAlt, summe_brutto: runde(summeAlt * (1 + mwst)),
      ohne_preis: kpos.filter((p) => p.ep === null).length, vollstaendig: kpos.every((p) => p.ep !== null),
    },
    anpassungen,
    geschaetztes_lv: {
      positionen: gpos, summe_netto: summeNeu, summe_brutto: runde(summeNeu * (1 + mwst)), differenz_netto: differenz,
      differenz_prozent: summeAlt === 0 ? 0 : runde((differenz / summeAlt) * 100), anzahl,
    },
  };
}
