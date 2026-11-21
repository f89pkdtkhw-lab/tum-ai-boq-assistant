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
export type Pruefbericht = { lv: LV; findings: Finding[]; kennzahlen: Kennzahlen; zusammenfassung?: Zusammenfassung;
  berichte?: Bericht[] | null; was_wenn?: WasWenn[] | null;
};
// Three reports, final report and what-if list (epic #93 B5): optional, absent on older backends.
export type BerichtId = "regelwerk" | "vergleich" | "was_wenn";
export type WasWenn = { oz: string | null; problem: string; chance: "hoch" | "niedrig"; empfehlung: string; case_ids: string[]; begruendung?: string };
export type Naeherung = {
  oz: string; kurztext: string; einheit: string; menge: number; geschaetzt: number; abweichung: number; abweichung_prozent: number;
  abweichung_eur: number | null; zu_gross: boolean; faktor: number; case_ids: string[]; note_id: string; warum: string;
};
export type BerichtZaehler = { grosse_probleme: number; warnungen: number; hinweise: number; empfehlungen: number; zu_grosse_naeherungen: number };
export type Bericht = {
  id: BerichtId; titel: string; status: "ok" | "nicht_verbunden" | "fehler"; meldung: string; finding_ids: string[];
  notes: { id?: string; oz?: string; text?: string; approval_required?: boolean }[]; neue_tags: string[];
  tags?: string[]; zaehler?: BerichtZaehler; naeherungen?: Naeherung[]; probleme?: WasWenn[];
};
export type Health = { ok: boolean; provider: string; model: string; mock: boolean };
export type Answer = { answer: string; provider: string; model: string; ms: number };
export type Example = { id: string; titel: string; beschreibung: string; lv: LV };

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
  ask: (question: string) => call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};
