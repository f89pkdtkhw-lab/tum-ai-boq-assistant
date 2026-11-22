// Manual unit-price edits on the price step, kept with the running evaluation in sessionStorage
// (same store family as `lv-eval-sitzung-v1`).
import type { GeschaetztePosition, Kalkulation, KalkulationPosition, Pruefbericht, Zusammenfassung } from "./api";
import { ladeSitzung } from "./evaluation-session";
import { preisSpanne, type PreisAnpassungen } from "./preisbericht";

export const PREIS_ANPASSUNG_PRAEFIX = "lv-eval-preise-v1:";
export const PREIS_ANPASSUNG_AKTUELL = "lv-eval-preise-v1:aktuell";

export type { PreisAnpassungen };

const runde = (n: number) => Math.round(n * 100) / 100;

function speicher(): Storage | null {
  if (typeof window === "undefined") return null;
  try { return window.sessionStorage; } catch { return null; }
}

export function leseAnpassungen(roh: unknown): PreisAnpassungen {
  if (!roh || typeof roh !== "object" || Array.isArray(roh)) return {};
  const out: PreisAnpassungen = {};
  for (const [k, v] of Object.entries(roh as Record<string, unknown>)) {
    if (/^\d+$/.test(k) && typeof v === "number" && Number.isFinite(v)) out[k] = v;
  }
  return out;
}

export function evalIdFuerPreise(): string | null {
  return ladeSitzung().aktuell?.id ?? null;
}

export function ladePreisAnpassungen(id?: string | null): PreisAnpassungen {
  const s = speicher();
  if (!s) return {};
  const keys = [...(id ? [PREIS_ANPASSUNG_PRAEFIX + id] : []), PREIS_ANPASSUNG_AKTUELL];
  for (const key of keys) {
    try {
      const gelesen = leseAnpassungen(JSON.parse(s.getItem(key) ?? "null"));
      if (Object.keys(gelesen).length) return gelesen;
    } catch { /* try the next key */ }
  }
  return {};
}

export function speicherePreisAnpassungen(id: string | null | undefined, anp: PreisAnpassungen): void {
  const s = speicher();
  if (!s) return;
  const payload = JSON.stringify(anp);
  const keys = [PREIS_ANPASSUNG_AKTUELL, ...(id ? [PREIS_ANPASSUNG_PRAEFIX + id] : [])];
  for (const key of keys) {
    try {
      if (Object.keys(anp).length === 0) s.removeItem(key);
      else s.setItem(key, payload);
    } catch { /* blocked or full */ }
  }
}

/** Set or clear (reset) the manual unit price of one bill row, addressed by its index. */
export function setzePreisAnpassung(id: string | null | undefined, index: number, ep: number | null): PreisAnpassungen {
  const anp = { ...ladePreisAnpassungen(id) };
  if (ep === null || !Number.isFinite(ep)) delete anp[String(index)];
  else anp[String(index)] = runde(ep);
  speicherePreisAnpassungen(id, anp);
  return anp;
}

function zeileMitEp<T extends { menge: number | null; ep: number | null; gp?: number | null }>(p: T, ep: number): T & { ep: number; gp: number | null } {
  return { ...p, ep, gp: p.menge == null ? null : runde(p.menge * ep) };
}

function spanneFuer(ep: number, menge: number | null) {
  return preisSpanne({ ep, menge, quelle: "manuell" });
}

function kalkulationMitAnpassungen(k: Kalkulation, anp: PreisAnpassungen): Kalkulation {
  const positionen: KalkulationPosition[] = k.positionen.map((p, i) => {
    const ep = anp[String(i)];
    if (ep == null) return p;
    const neu = zeileMitEp(p, ep);
    const s = spanneFuer(ep, p.menge);
    return { ...neu, ep_von: s.epVon, ep_bis: s.epBis, geschaetzt: true, schaetzung_hinweis: "Manually adjusted" };
  });
  let netto = 0, ohne = 0, voll = true;
  for (const p of positionen) {
    if (p.ep == null) ohne += 1;
    if (p.in_summe) {
      if (p.gp == null) voll = false;
      else netto += p.gp;
    }
  }
  netto = runde(netto);
  return { ...k, positionen, summe_netto: netto, summe_brutto: runde(netto * (1 + k.mwst_satz)), ohne_preis: ohne, vollstaendig: voll };
}

function geschaetztesMitAnpassungen(bericht: Pruefbericht, anp: PreisAnpassungen, originalNetto: number | null) {
  const g = bericht.geschaetztes_lv;
  if (!g) return g;
  const n = bericht.lv.positionen.length;
  const positionen: GeschaetztePosition[] = g.positionen.map((p, i) => {
    const ep = i < n ? anp[String(i)] : undefined;
    if (ep == null) return p;
    const menge = p.status === "removed" ? 0 : p.menge_neu;
    const s = spanneFuer(ep, menge);
    const gp = menge == null ? null : runde(menge * ep);
    return { ...p, ep, gp_neu: p.status === "removed" ? 0 : gp, ep_von: s.epVon, ep_bis: s.epBis, gp_von: p.status === "removed" ? 0 : s.von, gp_bis: p.status === "removed" ? 0 : s.bis };
  });
  let netto = 0, von = 0, bis = 0, irgend = false;
  for (const p of positionen) {
    if (p.gp_neu == null) continue;
    irgend = true;
    netto += p.gp_neu;
    von += p.gp_von ?? p.gp_neu;
    bis += p.gp_bis ?? p.gp_neu;
  }
  if (!irgend) return { ...g, positionen };
  const original = originalNetto ?? (g.summe_netto - g.differenz_netto);
  const summe = runde(netto);
  const differenz = runde(summe - original);
  return {
    ...g, positionen, summe_netto: summe,
    summe_brutto: runde(summe * (1 + (bericht.kalkulation?.mwst_satz ?? 0.19))),
    differenz_netto: differenz,
    differenz_prozent: original === 0 ? g.differenz_prozent : runde((differenz / original) * 100),
    summe_netto_von: runde(von), summe_netto_bis: runde(bis),
  };
}

/** Copy of the report with manual unit prices applied to the calculation and estimated bill. */
export function berichtMitAnpassungen(bericht: Pruefbericht, anp: PreisAnpassungen): Pruefbericht {
  if (!Object.keys(anp).length) return bericht;
  const kalkulation = bericht.kalkulation ? kalkulationMitAnpassungen(bericht.kalkulation, anp) : bericht.kalkulation;
  const geschaetztes_lv = geschaetztesMitAnpassungen(bericht, anp, bericht.kalkulation?.summe_netto ?? null);
  let zusammenfassung: Zusammenfassung | undefined = bericht.zusammenfassung;
  if (zusammenfassung && geschaetztes_lv) {
    zusammenfassung = {
      ...zusammenfassung,
      schaetzung_abweichung_eur: geschaetztes_lv.differenz_netto ?? zusammenfassung.schaetzung_abweichung_eur,
      schaetzung_von: geschaetztes_lv.summe_netto_von ?? zusammenfassung.schaetzung_von,
      schaetzung_bis: geschaetztes_lv.summe_netto_bis ?? zusammenfassung.schaetzung_bis,
    };
  }
  return { ...bericht, kalkulation, geschaetztes_lv, zusammenfassung };
}
