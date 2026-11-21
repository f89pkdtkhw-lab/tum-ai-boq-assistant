// Summary tiles (issue #103, epic #93 B1): score, estimate deviation, big problems, warnings, recommendations.
import type { Finding, Pruefbericht, ScoreAbzug } from "./api";

export type Gruppe = "gross" | "warnung" | "hinweis";

/** Same severity mapping as the backend (epic #93): big = kritisch+hoch, warning = mittel, notice = niedrig. */
export const GRUPPE_SCHWEREN: Record<Gruppe, Finding["schwere"][]> = {
  gross: ["kritisch", "hoch"], warnung: ["mittel"], hinweis: ["niedrig"],
};

export function inGruppe(finding: Finding, gruppe: Gruppe | null): boolean {
  return gruppe === null || GRUPPE_SCHWEREN[gruppe].includes(finding.schwere);
}

export type Uebersicht = {
  score: number | null; abzuege: ScoreAbzug[]; abweichung: number | null;
  grosseProbleme: number; warnungen: number; hinweise: number; empfehlungen: number | null;
  /** True when the backend sent no `zusammenfassung` and the counts come from the browser. */
  fallback: boolean;
};

/** Backend summary when present; otherwise counts from the findings, with score and recommendations unknown. */
export function uebersicht(bericht: Pick<Pruefbericht, "findings" | "zusammenfassung">): Uebersicht {
  const z = bericht.zusammenfassung;
  if (z) {
    return {
      score: z.score, abzuege: z.score_abzuege, abweichung: z.schaetzung_abweichung_eur,
      grosseProbleme: z.grosse_probleme, warnungen: z.warnungen, hinweise: z.hinweise, empfehlungen: z.empfehlungen, fallback: false,
    };
  }
  const zaehle = (g: Gruppe) => bericht.findings.filter((f) => inGruppe(f, g)).length;
  return {
    score: null, abzuege: [], abweichung: null,
    grosseProbleme: zaehle("gross"), warnungen: zaehle("warnung"), hinweise: zaehle("hinweis"), empfehlungen: null, fallback: true,
  };
}

/** "8.5 / 10", or "–" without a score. */
export function scoreText(score: number | null): string {
  return score === null || !Number.isFinite(score) ? "–" : `${(Math.round(score * 10) / 10).toFixed(1)} / 10`;
}

/** Signed euro deviation ("+€1,200.00", "−€80.00", "±€0.00"), or "not connected" without history. */
export function abweichungText(eur: number | null, format: (n: number) => string): string {
  if (eur === null || !Number.isFinite(eur)) return "not connected";
  if (eur === 0) return `±${format(0)}`;
  return `${eur > 0 ? "+" : "−"}${format(Math.abs(eur))}`;
}

/** Deduction points with a real minus sign, e.g. "−1.0". */
export function punkteText(punkte: number): string {
  return `${punkte < 0 ? "−" : punkte > 0 ? "+" : ""}${Math.abs(punkte).toFixed(1)}`;
}
