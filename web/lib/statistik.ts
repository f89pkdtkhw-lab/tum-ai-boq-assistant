// Estimate accuracy of past projects (used by the AI evaluation as the share of estimates that ran over).
import type { HistoryCase } from "./history-api";

export type Genauigkeit = {
  projekte: number; abgeschlossen: number; vergleiche: number;
  mittlererFehler: number | null; innerhalbZehn: number | null; ueberzogen: number | null;
  jahre: { jahr: string; abweichung: number; anzahl: number }[];
};

/** How close past estimates were to actual values: per position with both, as % deviation. */
export function genauigkeit(faelle: HistoryCase[]): Genauigkeit {
  const abw: { jahr: string; d: number }[] = [];
  for (const c of faelle) {
    for (const est of c.estimated_values) {
      const real = c.real_values.find((r) => r.oz === est.oz && r.metric === est.metric);
      if (est.value && real?.value != null) abw.push({ jahr: c.date.slice(0, 4), d: ((real.value - est.value) / est.value) * 100 });
    }
  }
  const jahre = new Map<string, number[]>();
  for (const a of abw) jahre.set(a.jahr, [...(jahre.get(a.jahr) ?? []), a.d]);
  const n = abw.length;
  return {
    projekte: faelle.length, abgeschlossen: faelle.filter((c) => c.real_values.length > 0).length, vergleiche: n,
    mittlererFehler: n ? abw.reduce((s, a) => s + Math.abs(a.d), 0) / n : null,
    innerhalbZehn: n ? abw.filter((a) => Math.abs(a.d) <= 10).length / n : null,
    ueberzogen: n ? abw.filter((a) => a.d > 0).length / n : null,
    jahre: [...jahre].sort(([a], [b]) => a.localeCompare(b)).map(([jahr, d]) => ({ jahr, anzahl: d.length, abweichung: d.reduce((s, x) => s + x, 0) / d.length })),
  };
}
