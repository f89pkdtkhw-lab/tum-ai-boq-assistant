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
// Price calculation (epic #93, B6/B7/B8): optional, absent until the backend prices the bill.
export type KalkulationPosition = {
  oz: string; kurztext?: string; menge: number | null; einheit: string | null; ep: number | null; gp: number | null;
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
  lv: LV; findings: Finding[]; kennzahlen: Kennzahlen; zusammenfassung?: Zusammenfassung;
  kalkulation?: Kalkulation | null; anpassungen?: Anpassung[] | null; geschaetztes_lv?: GeschaetztesLv | null;
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
export type Health = {
  ok: boolean; provider: string; model: string; mock: boolean;
  key_set?: boolean; key_source?: "ui" | "env" | null; reason?: string | null;
};
// #156: Claude API key entered in the UI. Answers never contain the key, only whether one is set.
export type KeyState = {
  provider: string; model: string; mock: boolean; key_set: boolean; key_source: "ui" | "env" | null;
  reason: string | null; ui_enabled: boolean; persisted?: boolean;
};
export type KeyProbe = { ok: boolean; provider: string; model: string; ms?: number; error?: string };
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
// Price database (epic #93 D5): unit prices kept across projects.
export type PreisEintrag = { id: number; item: string; unit: string; price_per_unit: number };
export type NeuerPreis = { item: string; unit: string; price_per_unit: number };
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
  preise: (query: string) => call<PreisEintrag[]>(`/api/db/preise${query}`),
  speicherePreise: (preise: NeuerPreis[]) => call<PreisEintrag[]>("/api/db/preise", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preise),
  }),
  analyse: (body: { lv: LV; regelwerk: Regelwerk | null; preisliste: Preisliste | null }) => call<Pruefbericht>("/api/lv/analyse", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  pruefen: (lv: LV) => call<Pruefbericht>("/api/lv/pruefen", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lv),
  }),
  keyState: () => call<KeyState>("/api/ai/key"),
  setKey: (body: { key: string; model?: string; persist?: boolean }) => call<KeyState>("/api/ai/key", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  clearKey: () => call<KeyState>("/api/ai/key", { method: "DELETE" }),
  testKey: () => call<KeyProbe>("/api/ai/key/test", { method: "POST" }),
  ask: (question: string) => call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};
