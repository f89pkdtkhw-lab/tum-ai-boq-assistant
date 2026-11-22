import { besitzerKopf } from "./vault.ts";
// Shared contract: docs/schnittstelle.md and api/app/modelle.py.
// Coordinate changes with the backend and announce them to @all on the board first.
export type Position = {
  oz: string; kurztext: string; langtext: string; menge: number | null;
  einheit: string | null; ep: number | null; gp: number | null;
  typ: "normal" | "bedarf" | "alternativ" | "zulage" | "pauschal" | "stundenlohn";
  titel_pfad: string[];
  // #170, optional: location in the uploaded original (absent for JSON bills and older reports).
  quelle?: PositionQuelle;
};
/** #170: PDF page/line/box (points, top-left origin), Excel sheet/row, GAEB XML element path or GAEB 90 record line. */
export type PositionQuelle = {
  seite?: number; zeile?: number; bbox?: [number, number, number, number]; seite_groesse?: [number, number];
  blatt?: string; pfad?: string;
};
export type LV = { name: string; quelle: string; positionen: Position[]; summen: Record<string, number> };
export type Finding = {
  id: string; oz: string; kategorie: "fehler" | "risiko" | "nachtrag";
  schwere: "kritisch" | "hoch" | "mittel" | "niedrig";
  titel: string; begruendung: string; vorschlag: string;
  quelle: "regel" | "modell"; regel_id: string; euro_wirkung: number | null;
};
export type Kennzahlen = {
  positionen: number; findings: number; kritisch: number; modell_mock: boolean;
  // #147/#168/#167, optional: why the model was not (fully) used, which model reviewed, batches sent and failed.
  modell_reason?: string | null; modell?: string | null; modell_batches?: number | null; modell_batches_fehlgeschlagen?: number | null;
};
// D (#168): how each AI step ran; absent when every step ran as the configured mock (no key).
export type KiSchrittStatus = "ok" | "mock" | "fehler" | "aus";
export type KiSchritt = { schritt: string; titel: string; status: KiSchrittStatus; grund?: string | null; modell?: string | null };
export type ScoreAbzug = { grund: string; punkte: number; bericht: "regelwerk" | "vergleich" | "was_wenn" };
export type Bewertungsmodell = "streng" | "gestaffelt" | "anteil" | "fehler_klaerung" | "ausgewogen";
export type Zusammenfassung = {
  score: number; score_abzuege: ScoreAbzug[]; schaetzung_abweichung_eur: number | null;
  schaetzung_von?: number | null; schaetzung_bis?: number | null;
  grosse_probleme: number; warnungen: number; hinweise: number; empfehlungen: number;
  bewertungsmodell?: Bewertungsmodell;
};
// Price calculation (epic #93, B6/B7/B8): optional, absent until the backend prices the bill.
export type KalkulationPosition = {
  oz: string; kurztext?: string; menge: number | null; einheit: string | null; ep: number | null; gp: number | null;
  ep_lv: number | null; gp_lv: number | null; treffer: "oz" | "text" | "aehnlich" | "kein_treffer" | "index" | "recherche";
  preis_eintrag: string | null; aehnlichkeit: number | null; in_summe: boolean;
  // t237: fallback estimate (index price or web research); absent for list/DB prices
  geschaetzt?: boolean; ep_von?: number | null; ep_bis?: number | null;
  preis_quellen?: PreisQuelle[]; schaetzung_hinweis?: string | null;
};
export type PreisQuelle = { titel: string; url?: string | null };
export type Kalkulation = {
  waehrung: string; mwst_satz: number; positionen: KalkulationPosition[];
  summe_netto: number; summe_brutto: number; ohne_preis: number; vollstaendig: boolean;
  warnungen?: string[]; enthaelt_schaetzungen?: boolean; geschaetzt_anzahl?: number;
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
  ep_von?: number | null; ep_bis?: number | null; gp_von?: number | null; gp_bis?: number | null;
};
export type GeschaetztesLv = {
  positionen: GeschaetztePosition[]; summe_netto: number; summe_brutto: number;
  differenz_netto: number; differenz_prozent: number; anzahl: Record<AenderungsStatus, number>;
  summe_netto_von?: number | null; summe_netto_bis?: number | null;
};
export type Pruefbericht = {
  lv: LV; findings: Finding[]; kennzahlen: Kennzahlen; zusammenfassung?: Zusammenfassung;
  kalkulation?: Kalkulation | null; anpassungen?: Anpassung[] | null; geschaetztes_lv?: GeschaetztesLv | null;
  berichte?: Bericht[] | null; was_wenn?: WasWenn[] | null; schlussbericht?: Schlussbericht | null;
  ki_schritte?: KiSchritt[] | null; // D #168
  recherche?: Recherche | null; // E #169: absent without a Claude key
};
// Deep web research (E #169): what ran, its cost, and sourced results per finding/item/report problem.
export type RechercheQuelle = { url: string; titel: string };
export type RechercheErgebnis = {
  schritt: "positionen" | "preise" | "berichte"; gruppe: string; oz: string | null; finding_id: string | null;
  einschaetzung: "bestaetigt" | "abgeschwaecht" | "unklar" | "plausibel" | "zu_hoch" | "zu_niedrig";
  text: string; quellen: RechercheQuelle[]; marktpreis_von: number | null; marktpreis_bis: number | null;
};
export type Recherche = {
  status: "ok" | "teilweise" | "fehler" | "aus"; meldung: string; aufrufe: number; suchen: number; ergebnisse: RechercheErgebnis[];
};
// Final report (epic #93 B5, shown and exported since #167): one row per bill item, none dropped.
export type ProblemVerweis = {
  finding_id: string; schwere: Finding["schwere"]; titel: string; quelle: "regel" | "modell"; regel_id: string; bericht?: BerichtId;
};
export type SchlussPosition = {
  oz: string; kurztext: string; menge: number | null; einheit: string | null; geschaetzt: number | null; abweichung: number | null;
  abweichung_eur: number | null; warum: string; nachtrag: string[]; probleme: ProblemVerweis[]; warnungen: string[]; empfehlungen: string[];
};
export type Schlussbericht = { projektbeschreibung: string; positionen: SchlussPosition[]; allgemein: ProblemVerweis[]; warnungen: string[] };
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

// t256: AI reading of a competitor PDF for the margin page (Claude or Grok Bot, never mock).
export type MargePdfAntwort = {
  dateiname: string; hinweis: string | null; gebote: number; xlsx_base64: string;
  vault: { id: string; typ: string; dateiname: string; version: number | null } | null;
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
export type DevProvider = "anthropic" | "mock" | "grokbot";
export type DevOptionsState = {
  provider: string; model: string; mock: boolean; reason: string | null;
  providers: DevProvider[]; queue_dir: string; timeout_s: number;
};
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
  source: "model_mock" | "model";
  model?: string | null; // #167: live model name
  reason?: string | null; // D #168: why a configured model did not answer
};

// Background analysis job with progress (#165): POST /api/lv/analyse/start, then poll GET /api/lv/analyse/status/{job_id}.
export type AnalyseJobAnfrage = { lv: LV; regelwerk: Regelwerk | null; preisliste: Preisliste | null; nur_pruefen?: boolean; bewertungsmodell?: Bewertungsmodell };
export type AnalyseStatus = {
  job_id: string; status: "laeuft" | "fertig" | "fehler"; schritt: number; schritte_gesamt: number; prozent: number;
  meldung: string; fertige_schritte: { schritt: number; meldung: string; sekunden: number }[]; fehler: string[];
  sekunden: number; ergebnis?: Pruefbericht | null;
};

// Synchronous model calls (Grok Bot queue up to 900 s). Reuse an identical in-flight POST
// so a remount or a retry after a dropped proxy does not enqueue a second job.
const LANGSAME_POSTS = new Set(["/api/lv/ai-evaluation", "/api/ask", "/api/marge/pdf"]);
const laufendePosts = new Map<string, Promise<unknown>>();

async function once<T>(path: string, init: RequestInit | undefined, run: () => Promise<T>): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method !== "POST" || !LANGSAME_POSTS.has(path) || typeof init?.body !== "string") return run();
  const schluessel = `${path}\n${init.body}`;
  const offen = laufendePosts.get(schluessel);
  if (offen) return offen as Promise<T>;
  const lauf = run().finally(() => { if (laufendePosts.get(schluessel) === lauf) laufendePosts.delete(schluessel); });
  laufendePosts.set(schluessel, lauf);
  return lauf;
}

/** t243: the signed-in e-mail goes along as X-LV-Scout-User, so vault entries record their owner. */
function mitBesitzer(init?: RequestInit): RequestInit | undefined {
  const kopf = besitzerKopf();
  if (!kopf["X-LV-Scout-User"]) return init;
  return { ...init, headers: { ...kopf, ...(init?.headers as Record<string, string> | undefined) } };
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  return once(path, init, async () => {
    // No short AbortController: the Grok Bot bridge may need the full proxyTimeout (960 s).
    const response = await fetch(`/backend${path}`, mitBesitzer(init));
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status}). Please check the input.`;
      throw Object.assign(new Error(detail), { status: response.status });
    }
    return body as T;
  });
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
  /** `lv`: optional tender bill (D83/X83/…) that gives a D84 offer its item texts. */
  importierePreisliste: (datei: File, lv?: File | null) => {
    const form = new FormData();
    form.append("datei", datei);
    if (lv) form.append("lv", lv);
    return call<Preisliste>("/api/preisliste/import", { method: "POST", body: form });
  },
  preise: (query: string) => call<PreisEintrag[]>(`/api/db/preise${query}`),
  speicherePreise: (preise: NeuerPreis[]) => call<PreisEintrag[]>("/api/db/preise", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preise),
  }),
  analyse: (body: { lv: LV; regelwerk: Regelwerk | null; preisliste: Preisliste | null }) => call<Pruefbericht>("/api/lv/analyse", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  pruefen: (lv: LV, bewertungsmodell: Bewertungsmodell = "ausgewogen") => call<Pruefbericht>(`/api/lv/pruefen?bewertungsmodell=${encodeURIComponent(bewertungsmodell)}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lv),
  }),
  starteAnalyse: (body: AnalyseJobAnfrage) => call<{ job_id: string }>("/api/lv/analyse/start", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  analyseStatus: (jobId: string) => call<AnalyseStatus>(`/api/lv/analyse/status/${encodeURIComponent(jobId)}`),
  keyState: () => call<KeyState>("/api/ai/key"),
  setKey: (body: { key: string; model?: string; persist?: boolean }) => call<KeyState>("/api/ai/key", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  clearKey: () => call<KeyState>("/api/ai/key", { method: "DELETE" }),
  testKey: () => call<KeyProbe>("/api/ai/key/test", { method: "POST" }),
  unlockDevOptions: (code: string) => call<{ ok: true }>("/api/ai/dev-options/unlock", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }),
  }),
  devOptions: () => call<DevOptionsState>("/api/ai/dev-options"),
  setDevProvider: (provider: DevProvider) => call<DevOptionsState>("/api/ai/dev-options", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }),
  }),
  aiEvaluation: (evidence: AiEvidence) => call<AiEvaluation>("/api/lv/ai-evaluation", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(evidence),
  }),
  margePdf: (datei: File) => {
    const form = new FormData();
    form.append("datei", datei);
    return call<MargePdfAntwort>("/api/marge/pdf", { method: "POST", body: form });
  },
  ask: (question: string) => call<Answer>("/api/ask", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
  }),
};
