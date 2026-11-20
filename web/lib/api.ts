// Gemeinsamer Vertrag: docs/schnittstelle.md und api/app/modelle.py.
// Änderungen zusammen mit dem Backend und vorher mit @all auf dem Board ankündigen.
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
export type Pruefbericht = { lv: LV; findings: Finding[]; kennzahlen: Kennzahlen };
export type Health = { ok: boolean; provider: string; model: string; mock: boolean };
export type Answer = { answer: string; provider: string; model: string; ms: number };
export type Example = { id: string; titel: string; beschreibung: string; lv: LV };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Anfrage fehlgeschlagen (${response.status}). Bitte Eingabe prüfen.`;
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
