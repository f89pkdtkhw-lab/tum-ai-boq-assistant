// Closing a project (team spec, UI step 7): our estimate and the real final bill become one history case.
// Items are matched by OZ; prices are compared per item and marked "confirmed" (within 10 %) or "deviation".
import type { LV } from "./api";
import type { Mark, Measurement } from "./history-api";

export type Abschluss = { estimated_values: Measurement[]; real_values: Measurement[]; marks: Mark[]; nurGeschaetzt: string[]; nurReal: string[] };

const TOLERANZ = .1;

/** Reads an uploaded JSON: a review report ({ lv, findings }) or a plain BoQ ({ positionen }). */
export function lvAusJson(daten: unknown): LV | null {
  const d = daten as { lv?: LV; positionen?: unknown };
  if (d && typeof d === "object" && d.lv && Array.isArray(d.lv.positionen)) return d.lv;
  if (d && typeof d === "object" && Array.isArray(d.positionen)) return d as LV;
  return null;
}

export function abschliessen(geschaetzt: LV, real: LV): Abschluss {
  const preis = (p: LV["positionen"][number]) => p.gp ?? (p.menge !== null && p.ep !== null ? p.menge * p.ep : null);
  const realNachOz = new Map(real.positionen.map((p) => [p.oz, p]));
  const geschaetztOz = new Set(geschaetzt.positionen.map((p) => p.oz));
  const estimated_values: Measurement[] = [];
  const real_values: Measurement[] = [];
  const marks: Mark[] = [];
  for (const p of geschaetzt.positionen) {
    const e = preis(p);
    if (e === null || e < 0) continue;
    estimated_values.push({ oz: p.oz, title_path: p.titel_pfad, metric: "price", value: Math.round(e * 100) / 100, unit: "EUR" });
    const r = realNachOz.get(p.oz);
    const rp = r ? preis(r) : null;
    if (rp === null || rp < 0) continue;
    real_values.push({ oz: p.oz, title_path: p.titel_pfad, metric: "price", value: Math.round(rp * 100) / 100, unit: "EUR" });
    const abw = e ? (rp - e) / e : 0;
    marks.push(Math.abs(abw) <= TOLERANZ
      ? { oz: p.oz, title_path: p.titel_pfad, status: "confirmed" }
      : { oz: p.oz, title_path: p.titel_pfad, status: "deviation", what_happened: `Real price ${abw > 0 ? "+" : ""}${Math.round(abw * 100)} % vs. estimate` });
  }
  return {
    estimated_values, real_values, marks,
    nurGeschaetzt: geschaetzt.positionen.filter((p) => !realNachOz.has(p.oz)).map((p) => p.oz),
    nurReal: real.positionen.filter((p) => !geschaetztOz.has(p.oz)).map((p) => p.oz),
  };
}
