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
// Price calculation (epic #93, B6/B7/B8): optional, absent until the backend prices the bill.
export type KalkulationPosition = {
  oz: string; menge: number | null; einheit: string | null; ep: number | null; gp: number | null;
  ep_lv: number | null; gp_lv: number | null; treffer: "oz" | "text" | "aehnlich" | "kein_treffer";
  preis_eintrag: string | null; aehnlichkeit: number | null; in_summe: boolean;
};
export type Kalkulation = {
  waehrung: string; mwst_satz: number; positionen: KalkulationPosition[];
  summe_netto: number; summe_brutto: number; ohne_preis: number; vollstaendig: boolean;
};
export type Anpassung = {
  id: string; oz: string; art: "menge" | "hinzufuegen" | "entfernen"; menge_alt: number | null; menge_neu: number | null;
  position: Position | null; grund: string; bericht: "regelwerk" | "vergleich" | "was_wenn"; finding_id: string | null;
};
export type AenderungsStatus = "unchanged" | "updated" | "added" | "removed";
export type GeschaetztePosition = {
  oz: string; status: AenderungsStatus; kurztext: string; einheit: string | null;
  menge_alt: number | null; menge_neu: number | null; ep: number | null; gp_alt: number | null; gp_neu: number | null;
  anpassung_ids: string[]; grund: string; freigabe_noetig: boolean;
};
export type GeschaetztesLv = {
  positionen: GeschaetztePosition[]; summe_netto: number; summe_brutto: number;
  differenz_netto: number; differenz_prozent: number; anzahl: Record<AenderungsStatus, number>;
};
export type Pruefbericht = {
  lv: LV; findings: Finding[]; kennzahlen: Kennzahlen;
  kalkulation?: Kalkulation | null; anpassungen?: Anpassung[] | null; geschaetztes_lv?: GeschaetztesLv | null;
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
