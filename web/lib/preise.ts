// Price comparison (Preisspiegel) for one BoQ: unit prices of the same work side by side, outliers by the IQR rule,
// and the median compared with unit prices from past projects. Only prices from the file and the history store are used.
import type { Position } from "./api";
import type { HistoryCase } from "./history-api";
import { gewerkVon } from "./einschaetzung";

export type Stufe = "gruen" | "gelb" | "rot";
export type PreisPosition = { oz: string; ep: number; abweichung: number; stufe: Stufe };
export type Vergleich = { median: number; projekte: number; abweichung: number; stufe: Stufe };
export type PreisGruppe = {
  schluessel: string; kurztext: string; einheit: string; gewerk: string | null;
  positionen: PreisPosition[]; min: number; q1: number; median: number; q3: number; max: number;
  auffaellig: number; historie: Vergleich | null;
};
export type Preisspiegel = { gruppen: PreisGruppe[]; zaehler: Record<Stufe, number>; zuWenig: number; ohnePreis: number };

/** Groups with fewer prices than this are listed as "too few to compare". */
export const MIN_GRUPPE = 4;

function quantil(sortiert: number[], q: number) {
  const pos = (sortiert.length - 1) * q;
  const unten = Math.floor(pos);
  return sortiert[unten] + (sortiert[Math.min(unten + 1, sortiert.length - 1)] - sortiert[unten]) * (pos - unten);
}

/**
 * Tukey fences: outside 1.5 × IQR is unusual (yellow), outside 3 × IQR is an outlier (red). A price must also be at
 * least 20 % off the median, so tight groups do not flag cent-level differences.
 */
export function stufeVon(ep: number, q1: number, median: number, q3: number): Stufe {
  const iqr = q3 - q1;
  const abw = Math.abs(ep / median - 1);
  if (abw < .2) return "gruen";
  if (ep < q1 - 3 * iqr || ep > q3 + 3 * iqr) return "rot";
  if (ep < q1 - 1.5 * iqr || ep > q3 + 1.5 * iqr) return "gelb";
  return "gruen";
}

/** Median unit price per trade and unit from past projects (metric "unit_price", unit "EUR/<unit>"). */
export function historienPreise(faelle: HistoryCase[]): Map<string, { werte: number[]; projekte: Set<string> }> {
  const karte = new Map<string, { werte: number[]; projekte: Set<string> }>();
  for (const c of faelle) {
    for (const m of c.estimated_values) {
      if (m.metric !== "unit_price" || m.value === null) continue;
      const p = c.lv.positionen.find((x) => x.oz === m.oz);
      const gewerk = gewerkVon(p?.kurztext ?? "");
      if (!gewerk) continue;
      const k = `${gewerk}|${m.unit.replace(/^EUR\//, "")}`;
      const e = karte.get(k) ?? { werte: [], projekte: new Set<string>() };
      e.werte.push(m.value);
      e.projekte.add(c.case_id);
      karte.set(k, e);
    }
  }
  return karte;
}

export function preisspiegel(positionen: Position[], faelle: HistoryCase[] | null): Preisspiegel {
  const gruppen = new Map<string, { kurztext: string; einheit: string; liste: { oz: string; ep: number }[] }>();
  let ohnePreis = 0;
  for (const p of positionen) {
    if (p.ep === null || p.ep <= 0 || !p.einheit) { ohnePreis += 1; continue; }
    const k = `${p.kurztext.trim().toLowerCase()}|${p.einheit.trim()}`;
    const g = gruppen.get(k) ?? { kurztext: p.kurztext.trim(), einheit: p.einheit.trim(), liste: [] };
    g.liste.push({ oz: p.oz, ep: p.ep });
    gruppen.set(k, g);
  }
  const hist = faelle ? historienPreise(faelle) : new Map();
  const zaehler: Record<Stufe, number> = { gruen: 0, gelb: 0, rot: 0 };
  let zuWenig = 0;
  const ergebnis: PreisGruppe[] = [];
  for (const [schluessel, g] of gruppen) {
    if (g.liste.length < MIN_GRUPPE) { zuWenig += g.liste.length; continue; }
    const s = g.liste.map((x) => x.ep).sort((a, b) => a - b);
    const q1 = quantil(s, .25), median = quantil(s, .5), q3 = quantil(s, .75);
    const pos = g.liste.map((x) => ({ ...x, abweichung: x.ep / median - 1, stufe: stufeVon(x.ep, q1, median, q3) }))
      .sort((a, b) => Math.abs(b.abweichung) - Math.abs(a.abweichung));
    for (const x of pos) zaehler[x.stufe] += 1;
    const gewerk = gewerkVon(g.kurztext);
    const h = gewerk ? hist.get(`${gewerk}|${g.einheit}`) : undefined;
    let historie: Vergleich | null = null;
    if (h && h.werte.length >= 3) {
      const hm = quantil([...h.werte].sort((a, b) => a - b), .5);
      const abw = median / hm - 1;
      historie = { median: hm, projekte: h.projekte.size, abweichung: abw, stufe: Math.abs(abw) <= .15 ? "gruen" : Math.abs(abw) <= .3 ? "gelb" : "rot" };
    }
    ergebnis.push({ schluessel, kurztext: g.kurztext, einheit: g.einheit, gewerk, positionen: pos,
      min: s[0], q1, median, q3, max: s[s.length - 1], auffaellig: pos.filter((x) => x.stufe !== "gruen").length, historie });
  }
  ergebnis.sort((a, b) => b.auffaellig - a.auffaellig || Math.abs(b.historie?.abweichung ?? 0) - Math.abs(a.historie?.abweichung ?? 0) || a.kurztext.localeCompare(b.kurztext));
  return { gruppen: ergebnis, zaehler, zuWenig, ohnePreis };
}
