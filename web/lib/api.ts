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
// Optional inputs of POST /api/lv/analyse (epic #93): regulation document (B3) and price list (D4).
export type Regelwerk = {
  id: string; dateiname: string; warnungen: string[];
  normverweise: { norm_id: string; ausgabe: string | null; fundstelle: string }[];
  kennwerte: { norm: string | null; kennwert: string; wert: string; einheit: string | null; fundstelle: string }[];
};
export type Preisliste = {
  id: string; dateiname: string; waehrung: string; warnungen: string[];
  eintraege: { id: string; oz: string | null; kurztext: string; einheit: string; ep: number; quelle: string }[];
};
/** Error from the backend; `status` lets callers tell a missing route (404) from other failures. */
export type ApiFehler = Error & { status?: number };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status}). Please check the input.`;
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return body as T;
}

function upload<T>(path: string, datei: File) {
  const form = new FormData();
  form.append("datei", datei);
  return call<T>(path, { method: "POST", body: form });
}

export const api = {
  health: () => call<Health>("/health"),
  examples: () => call<{ items: Example[] }>("/api/beispiele").then((body) => body.items),
  importiere: (datei: File) => {
    const form = new FormData();
    form.append("datei", datei);
    return call<LV>("/api/lv/import", { method: "POST", body: form });
  },
  importiereRegelwerk: (datei: File) => upload<Regelwerk>("/api/regelwerk/import", datei),
  importierePreisliste: (datei: File) => upload<Preisliste>("/api/preisliste/import", datei),
  analyse: (body: { lv: LV; regelwerk: Regelwerk | null; preisliste: Preisliste | null }) => call<Pruefbericht>("/api/lv/analyse", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  pruefen: (lv: LV) => call<Pruefbericht>("/api/lv/pruefen", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lv),
  }),
  ask: (question: string) => call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};
