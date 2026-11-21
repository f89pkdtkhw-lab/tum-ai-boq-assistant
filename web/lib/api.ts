// Shared contract: docs/schnittstelle.md and api/app/modelle.py.
// Coordinate changes with the backend and announce them to @all on the board first.
export type Position = {
  oz: string; kurztext: string; langtext: string; menge: number | null;
  einheit: string | null; ep: number | null; gp: number | null;
  typ: "normal" | "bedarf" | "alternativ" | "zulage" | "pauschal" | "stundenlohn";
  titel_pfad: string[];
};
export type LV = { name: string; quelle: string; positionen: Position[]; summen: Record<string, number> };
export type Finding = {
  id: string; oz: string; kategorie: "fehler" | "risiko" | "nachtrag";
  schwere: "kritisch" | "hoch" | "mittel" | "niedrig";
  titel: string; begruendung: string; vorschlag: string;
  quelle: "regel" | "modell"; regel_id: string; euro_wirkung: number | null;
};
export type Kennzahlen = { positionen: number; findings: number; kritisch: number; modell_mock: boolean };
export type ScoreAbzug = { grund: string; punkte: number; bericht: "regelwerk" | "vergleich" | "was_wenn" };
export type Zusammenfassung = {
  score: number; score_abzuege: ScoreAbzug[]; schaetzung_abweichung_eur: number | null;
  grosse_probleme: number; warnungen: number; hinweise: number; empfehlungen: number;
};
export type Pruefbericht = { lv: LV; findings: Finding[]; kennzahlen: Kennzahlen; zusammenfassung?: Zusammenfassung };
export type Health = { ok: boolean; provider: string; model: string; mock: boolean };
export type Answer = { answer: string; provider: string; model: string; ms: number };
export type Example = { id: string; titel: string; beschreibung: string; lv: LV };
// AI evaluation of a whole BoQ (api/app/ai/evaluation.py). The browser sends evidence it computed; the server answers.
export type AiEvidence = {
  name: string; items: number; score: number; traffic_light: "rot" | "gelb" | "gruen";
  stated_total: number | null; recalculated_total: number | null; with_optional_total: number | null; history_expected_total: number | null;
  serious_items: number; findings_by_rule: Record<string, number>; change_order_findings: number;
  price_outliers: { oz: string; work: string; deviation_pct: number }[]; unusual_prices: number;
  trades: { trade: string; avg_overrun_pct: number; projects: number }[]; past_overrun_share: number | null; language: "en" | "de";
};
export type AiEvaluation = {
  decision: "go" | "go_with_conditions" | "no_go"; headline: string; summary: string;
  predictions: { title: string; low: number | null; high: number | null; unit: string; confidence: "low" | "medium" | "high"; basis: string }[];
  recommendations: { priority: "now" | "before_bid" | "pricing" | "negotiation"; title: string; why: string }[];
  source: "model_mock";
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status}). Please check the input.`;
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  health: () => call<Health>("/health"),
  examples: () => call<{ items: Example[] }>("/api/beispiele").then((body) => body.items),
  importiere: (datei: File) => {
    const form = new FormData();
    form.append("datei", datei);
    return call<LV>("/api/lv/import", { method: "POST", body: form });
  },
  pruefen: (lv: LV) => call<Pruefbericht>("/api/lv/pruefen", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lv),
  }),
  aiEvaluation: (evidence: AiEvidence) => call<AiEvaluation>("/api/lv/ai-evaluation", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(evidence),
  }),
  ask: (question: string) => call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};
