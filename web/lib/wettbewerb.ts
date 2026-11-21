// Competitor memory: tender opening results (Submissionsergebnisse) per project, and per company its usual
// margin over OUR own costs (Selbstkosten) – a proxy, since we never see their costs. Companies that bid
// below our costs or far under the next bidder are flagged: competing with them only loses money.
import { AUFGREIFSCHWELLE } from "./zuschlag";

export type Gebot = { firma: string; summe: number };
export type Submission = { id: string; projekt: string; datum: string; selbstkosten: number; gebote: Gebot[] };
export type Einstufung = "unrealistisch" | "aggressiv" | "normal";
export type Firma = {
  firma: string; projekte: number; siege: number;
  marge: number;                      // median of (bid − our own costs) / bid, %
  min: number; max: number;
  sprunghaft: number;                 // times ≥ AUFGREIFSCHWELLE % under the next bidder
  punkte: { projekt: string; datum: string; marge: number; summe: number; erster: boolean; ausreisser: boolean }[];
  einstufung: Einstufung;
};

const SCHLUESSEL = "lv-submissionen-v1";
const median = (z: number[]) => { const s = [...z].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const r1 = (n: number) => Math.round(n * 10) / 10;

/** "Firma; 1.234.567,89" per line (also tab or colon); a line with only a number gets "Bidder n". */
export function leseZeilen(text: string): Gebot[] {
  return text.split(/\r?\n/).map((z) => z.trim()).filter(Boolean).map((z, i) => {
    const m = z.match(/^(.*?)[;:\t]\s*([^;:\t]*)$/);
    const [name, betrag] = m && /\d/.test(m[2]) ? [m[1].trim(), m[2]] : ["", z];
    return { firma: name || `Bidder ${i + 1}`, summe: zahl(betrag) };
  }).filter((g) => Number.isFinite(g.summe) && g.summe > 0);
}

/** German (1.234.567,89) or English (1,234,567.89) amount. */
export function zahl(text: string): number {
  const s = text.replace(/[€\s]|eur/gi, "");
  const de = /,\d{1,2}$/.test(s) || (/\.\d{3}(\D|$)/.test(s) && !/,\d{3}/.test(s));
  return Number(de ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, ""));
}

export function auswerten(subs: Submission[]): Firma[] {
  const map = new Map<string, Firma["punkte"]>();
  const sprung = new Map<string, number>();
  for (const s of subs) {
    const sortiert = [...s.gebote].sort((a, b) => a.summe - b.summe);
    sortiert.forEach((g, i) => {
      const key = g.firma.trim();
      if (!map.has(key)) map.set(key, []);
      const marge = r1((g.summe - s.selbstkosten) / g.summe * 100);
      map.get(key)!.push({ projekt: s.projekt, datum: s.datum, summe: g.summe, erster: i === 0, marge, ausreisser: istAusreisser(g.summe, marge, sortiert[i + 1]?.summe) });
      const naechstes = sortiert[i + 1];
      if (naechstes && g.summe <= naechstes.summe * (1 - AUFGREIFSCHWELLE / 100)) sprung.set(key, (sprung.get(key) ?? 0) + 1);
    });
  }
  return [...map].map(([firma, punkte]): Firma => {
    const m = punkte.map((p) => p.marge);
    const marge = r1(median(m));
    const sprunghaft = sprung.get(firma) ?? 0;
    // Unrealistic: usually below our own costs, or repeatedly far under everyone else.
    const einstufung: Einstufung = marge < 0 || sprunghaft >= 2 ? "unrealistisch" : marge < 3 || sprunghaft === 1 ? "aggressiv" : "normal";
    return { firma, projekte: punkte.length, siege: punkte.filter((p) => p.erster).length, marge, min: Math.min(...m), max: Math.max(...m), sprunghaft,
      punkte: punkte.sort((a, b) => a.datum.localeCompare(b.datum)), einstufung };
  }).sort((a, b) => a.marge - b.marge);
}

export function lade(): Submission[] {
  try { const d = JSON.parse(window.localStorage.getItem(SCHLUESSEL) ?? "[]"); return Array.isArray(d) ? d : []; } catch { return []; }
}
export function speichere(subs: Submission[]): boolean {
  try { window.localStorage.setItem(SCHLUESSEL, JSON.stringify(subs)); return true; } catch { return false; }
}

/** Synthetic demo history (fictional bidders, no partner data): 10 tenders, 6 bidders with fixed habits. */
export function demo(): Submission[] {
  let x = 7;
  const zufall = () => { x = (x * 16807) % 2147483647; return x / 2147483647; };
  // Usual margin over our own costs per bidder (%), spread ±; "Bidder E" dumps prices.
  const firmen: [string, number, number][] = [["Bidder A", 9, 2], ["Bidder B", 6, 2.5], ["Bidder C", 12, 3], ["Bidder D", 3, 2], ["Bidder E", -9, 4], ["Bidder F", 7, 5]];
  const projekte = ["Kita Nord", "Schule Ost – Rohbau", "Wohnanlage Park", "Sporthalle", "Bürogebäude Mitte", "Tiefgarage Süd", "Feuerwache", "Pflegeheim", "Gewerbehalle", "Rathaus Anbau"];
  return projekte.map((projekt, i) => {
    const selbstkosten = Math.round((800000 + zufall() * 4200000) / 1000) * 1000;
    const dabei = firmen.filter(() => zufall() > 0.25);
    const gebote = (dabei.length >= 3 ? dabei : firmen.slice(0, 4)).map(([firma, m, s]) => {
      const marge = m + (zufall() * 2 - 1) * s;
      return { firma, summe: Math.round(selbstkosten / (1 - marge / 100) / 100) * 100 };
    });
    return { id: `demo-${i}`, projekt, datum: `2026-${String(i + 1).padStart(2, "0")}-15`, selbstkosten, gebote };
  });
}

// ---- Bidder documents, outliers and the bid prediction ----

/** A bid is an outlier (a bidder going very low on purpose): ≥ AUFGREIFSCHWELLE % under the next bid, or clearly below our own costs. */
export const AUSREISSER_MARGE = -5;
export function istAusreisser(summe: number, marge: number, naechstes?: number): boolean {
  return marge <= AUSREISSER_MARGE || (naechstes !== undefined && summe <= naechstes * (1 - AUFGREIFSCHWELLE / 100));
}

const BETRAG = /(\d{1,3}(?:[.,\u00a0 ]\d{3})+(?:[.,]\d{1,2})?|\d{4,}(?:[.,]\d{1,2})?)\s*(?:€|eur|euro)?\s*$/i;

/** Reads a tender opening document (Submissionsergebnis / Niederschrift) saved as text or CSV:
 *  a table with a bidder and an amount column, or lines like "1. Muster Bau GmbH, Ort … 1.234.567,89 €".
 *  Header, total and empty lines are skipped. */
export function leseDokument(text: string): Gebot[] {
  const zeilen = text.split(/\r?\n/).map((z) => z.trim()).filter(Boolean);
  const trenner = [";", "\t", ","].find((c) => (zeilen[0] ?? "").split(c).length > 1 && /bieter|firma|company|bidder|name|unternehmen/i.test(zeilen[0]));
  if (trenner) {
    const kopf = zeilen[0].split(trenner).map((k) => k.trim().toLowerCase());
    const iName = kopf.findIndex((k) => /bieter|firma|company|bidder|name|unternehmen/.test(k));
    const iBetrag = kopf.findIndex((k) => /summe|betrag|angebot|total|bid|preis|price|brutto|netto/.test(k) && !/rang|rank|nr/.test(k));
    if (iName >= 0 && iBetrag >= 0) {
      return zeilen.slice(1).map((z) => z.split(trenner)).map((f) => ({ firma: (f[iName] ?? "").trim().replace(/^"|"$/g, ""), summe: zahl((f[iBetrag] ?? "").replace(/"/g, "")) }))
        .filter((g) => g.firma && g.summe > 0);
    }
  }
  return zeilen.flatMap((z) => {
    if (/^(summe|gesamt|total|rang|nr\.?\s|bieter\s*;?\s*angebot)/i.test(z)) return [];
    const m = z.match(BETRAG);
    if (!m) return [];
    const firma = z.slice(0, m.index).replace(/^\s*\d+\s*[.)]?\s+/, "").replace(/[;:,\t|–-]+\s*$/, "").trim();
    const summe = zahl(m[1].replace(/[\u00a0 ]/g, "."));
    return firma && /\p{L}/u.test(firma) && summe > 0 ? [{ firma, summe }] : [];
  });
}

export type Zeile = Gebot & { marge: number; ausreisser: boolean; rang: number };
/** One tender: each bid with its margin over our own costs and the outlier mark. */
export function bewerte(gebote: Gebot[], selbstkosten: number): Zeile[] {
  const s = [...gebote].sort((a, b) => a.summe - b.summe);
  return s.map((g, i) => {
    const marge = r1((g.summe - selbstkosten) / g.summe * 100);
    return { ...g, rang: i + 1, marge, ausreisser: istAusreisser(g.summe, marge, s[i + 1]?.summe) };
  });
}

const quantil = (z: number[], q: number) => { const s = [...z].sort((a, b) => a - b); const p = (s.length - 1) * q; const u = Math.floor(p); return s[u] + (s[Math.ceil(p)] - s[u]) * (p - u); };

export type Vorhersage = { firma: string; marge: number; summe: number; projekte: number };
export type Empfehlung = {
  vorhersagen: Vorhersage[];          // serious bidders, cheapest expected first
  ignoriert: string[];                // unrealistic bidders left out
  empfohlen: number; marge: number;   // our bid and the margin left in it
  grund: "unter_guenstigstem" | "mindestmarge" | "keine_historie";
  siegquote: number | null;           // share of past tenders this margin would have won (serious bidders only)
};

/** What to bid: expect each serious bidder at the low end of its own history (25th percentile of its non-outlier margins),
 *  go `unterbieten` % under the cheapest expectation, but keep at least `minMarge` % over our own costs. */
export function empfehle(selbstkosten: number, firmen: Firma[], subs: Submission[], opt: { unterbieten: number; minMarge: number; nur?: string[] }): Empfehlung {
  const ernst = firmen.filter((f) => f.einstufung !== "unrealistisch" && (!opt.nur || opt.nur.includes(f.firma)));
  const vorhersagen = ernst.map((f): Vorhersage => {
    const m = f.punkte.filter((p) => !p.ausreisser).map((p) => p.marge);
    const marge = r1(quantil(m.length ? m : f.punkte.map((p) => p.marge), 0.25));
    return { firma: f.firma, marge, summe: Math.round(selbstkosten / (1 - marge / 100)), projekte: f.projekte };
  }).sort((a, b) => a.summe - b.summe);
  const ignoriert = firmen.filter((f) => f.einstufung === "unrealistisch" && (!opt.nur || opt.nur.includes(f.firma))).map((f) => f.firma);
  const boden = selbstkosten / (1 - opt.minMarge / 100);
  let empfohlen = boden, grund: Empfehlung["grund"] = "keine_historie";
  if (vorhersagen.length) {
    const ziel = vorhersagen[0].summe * (1 - opt.unterbieten / 100);
    [empfohlen, grund] = ziel >= boden ? [ziel, "unter_guenstigstem"] : [boden, "mindestmarge"];
  }
  empfohlen = Math.round(empfohlen);
  const marge = r1((empfohlen - selbstkosten) / empfohlen * 100);
  // Back-test: would this margin have beaten every serious, non-outlier bid in past tenders?
  const ernstNamen = new Set(ernst.map((f) => f.firma));
  const relevant = subs.map((s) => bewerte(s.gebote, s.selbstkosten).filter((z) => ernstNamen.has(z.firma.trim()) && !z.ausreisser)).filter((z) => z.length);
  const siegquote = relevant.length ? r1(relevant.filter((z) => Math.min(...z.map((x) => x.marge)) > marge).length / relevant.length * 100) : null;
  return { vorhersagen, ignoriert, empfohlen, marge, grund, siegquote };
}
