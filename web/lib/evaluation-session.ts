// Current and recent evaluations, kept in this tab's sessionStorage.
// A running analysis job continues on the backend; this store keeps the job id, step and
// last reports so the sidebar can send the user back after they open Vault or another page.
import type { Pruefbericht } from "./api";
import { istWizardSchritt, wizardPfad, type WizardSchritt } from "./wizard";

export const SITZUNG_SCHLUESSEL = "lv-eval-sitzung-v1";
export const AKTUELL_SCHLUESSEL = "lv-aktuell-v1";
export const BERICHT_PRAEFIX = "lv-eval-bericht-v1:";
export const MAX_HISTORIE = 8;

export type EvaluationStatus = "laeuft" | "fertig" | "fehler";

export type EvaluationEintrag = {
  id: string;
  jobId: string | null;
  titel: string;
  status: EvaluationStatus;
  schritt: WizardSchritt;
  prozent: number | null;
  meldung: string;
  updatedAt: number;
};

export type EvaluationSitzung = {
  aktuell: EvaluationEintrag | null;
  historie: EvaluationEintrag[];
};

export type GespeicherterBericht = { titel: string; beispielId: string | null; bericht: Pruefbericht };

const hoerer = new Set<() => void>();

export const leereSitzung = (): EvaluationSitzung => ({ aktuell: null, historie: [] });

function speicher(): Storage | null {
  if (typeof window === "undefined") return null;
  try { return window.sessionStorage; } catch { return null; }
}

function istEintrag(wert: unknown): wert is EvaluationEintrag {
  if (!wert || typeof wert !== "object") return false;
  const e = wert as EvaluationEintrag;
  return typeof e.id === "string" && e.id.length > 0
    && (e.jobId === null || typeof e.jobId === "string")
    && typeof e.titel === "string"
    && (e.status === "laeuft" || e.status === "fertig" || e.status === "fehler")
    && istWizardSchritt(e.schritt)
    && (e.prozent === null || typeof e.prozent === "number")
    && typeof e.meldung === "string"
    && typeof e.updatedAt === "number";
}

export function leseSitzung(roh: unknown): EvaluationSitzung {
  if (!roh || typeof roh !== "object") return leereSitzung();
  const d = roh as { aktuell?: unknown; historie?: unknown };
  const aktuell = istEintrag(d.aktuell) ? d.aktuell : null;
  const historie: EvaluationEintrag[] = [];
  if (Array.isArray(d.historie)) {
    for (const e of d.historie) {
      if (istEintrag(e) && !historie.some((x) => x.id === e.id) && e.id !== aktuell?.id) {
        historie.push(e);
        if (historie.length >= MAX_HISTORIE) break;
      }
    }
  }
  return { aktuell, historie };
}

export function ladeSitzung(): EvaluationSitzung {
  const s = speicher();
  if (!s) return leereSitzung();
  try { return leseSitzung(JSON.parse(s.getItem(SITZUNG_SCHLUESSEL) ?? "null")); } catch { return leereSitzung(); }
}

function schreiben(sitzung: EvaluationSitzung): void {
  const s = speicher();
  if (s) {
    try { s.setItem(SITZUNG_SCHLUESSEL, JSON.stringify(sitzung)); } catch { /* blocked or full: memory only */ }
  }
  hoerer.forEach((h) => h());
}

function inHistorie(historie: EvaluationEintrag[], eintrag: EvaluationEintrag): EvaluationEintrag[] {
  return [eintrag, ...historie.filter((x) => x.id !== eintrag.id)].slice(0, MAX_HISTORIE);
}

/**
 * Start or update the current evaluation. A previous current item with a different id goes to the history,
 * except `ersetzt`: the local placeholder of the same run that now has its backend job id.
 */
export function setzeAktuelleEvaluation(teil: Partial<EvaluationEintrag> & Pick<EvaluationEintrag, "id" | "titel" | "status">, ersetzt?: string): EvaluationEintrag {
  const sitzung = ladeSitzung();
  const vorher = sitzung.aktuell;
  const basis = vorher && vorher.id === teil.id ? vorher : {
    jobId: null as string | null,
    schritt: "pruefen" as WizardSchritt,
    prozent: null as number | null,
    meldung: "",
  };
  const aktuell: EvaluationEintrag = {
    id: teil.id,
    jobId: teil.jobId !== undefined ? teil.jobId : basis.jobId,
    titel: teil.titel,
    status: teil.status,
    schritt: teil.schritt ?? basis.schritt,
    prozent: teil.prozent !== undefined ? teil.prozent : basis.prozent,
    meldung: teil.meldung !== undefined ? teil.meldung : basis.meldung,
    updatedAt: teil.updatedAt ?? Date.now(),
  };
  let historie = sitzung.historie.filter((x) => x.id !== aktuell.id);
  if (vorher && vorher.id !== aktuell.id && vorher.id !== ersetzt) historie = inHistorie(historie, vorher);
  schreiben({ aktuell, historie });
  return aktuell;
}

/** Update an evaluation where it is (current or history) without making it current; unknown ids are ignored. */
export function aktualisiereEvaluation(id: string, teil: Partial<Pick<EvaluationEintrag, "status" | "prozent" | "meldung">>): void {
  const sitzung = ladeSitzung();
  const trifft = (e: EvaluationEintrag) => e.id === id || e.jobId === id;
  const neu = (e: EvaluationEintrag): EvaluationEintrag => ({ ...e, ...teil, updatedAt: Date.now() });
  if (sitzung.aktuell && trifft(sitzung.aktuell)) {
    schreiben({ ...sitzung, aktuell: neu(sitzung.aktuell) });
  } else if (sitzung.historie.some(trifft)) {
    schreiben({ ...sitzung, historie: sitzung.historie.map((e) => (trifft(e) ? neu(e) : e)) });
  }
}

/** Keep the wizard step of the current evaluation, so a later return lands on the same step. */
export function setzeEvaluationSchritt(schritt: WizardSchritt): void {
  const sitzung = ladeSitzung();
  if (!sitzung.aktuell || sitzung.aktuell.schritt === schritt) return;
  schreiben({ ...sitzung, aktuell: { ...sitzung.aktuell, schritt, updatedAt: Date.now() } });
}

/** After "Load another file": the current item stays in the history, the start screen can open. */
/** Make a history item the current one (e.g. after the user clicks it in the menu). */
export function aktiviereEvaluation(id: string): EvaluationEintrag | null {
  const sitzung = ladeSitzung();
  const treffer = sitzung.aktuell?.id === id ? sitzung.aktuell
    : sitzung.aktuell?.jobId === id ? sitzung.aktuell
    : sitzung.historie.find((e) => e.id === id || e.jobId === id) ?? null;
  if (!treffer) return null;
  if (sitzung.aktuell?.id !== treffer.id) setzeAktuelleEvaluation(treffer);
  return treffer;
}

export function archiviereAktuelleEvaluation(): void {
  const sitzung = ladeSitzung();
  if (!sitzung.aktuell) return;
  schreiben({ aktuell: null, historie: inHistorie(sitzung.historie, sitzung.aktuell) });
}

export function evaluationPfad(eintrag: Pick<EvaluationEintrag, "id" | "jobId" | "status" | "schritt">): string {
  const schritt = eintrag.status === "laeuft" || eintrag.schritt === "hochladen" ? "pruefen" : eintrag.schritt;
  const teile = [wizardPfad(schritt), `eval=${encodeURIComponent(eintrag.id)}`];
  if (eintrag.jobId) teile.push(`job=${encodeURIComponent(eintrag.jobId)}`);
  return teile.join("&");
}

/**
 * Job id to resume for a link back to an evaluation (`?eval=&job=`), or null. A finished evaluation whose report
 * is stored in this session is restored from it instead, so it still opens after the backend lost the job.
 */
export function fortzusetzenderJob(
  sitzung: EvaluationSitzung, jobId: string | null, evalId: string | null, berichtGespeichert: (id: string) => boolean,
): string | null {
  const eintrag = [sitzung.aktuell, ...sitzung.historie].find((e) => e && ((evalId && e.id === evalId) || (jobId && e.jobId === jobId)));
  if (eintrag && eintrag.status === "fertig" && berichtGespeichert(eintrag.id)) return null;
  return jobId || (sitzung.aktuell?.status === "laeuft" ? sitzung.aktuell.jobId : null);
}

/**
 * An evaluation the chip or this tab wanted to reopen, but there is no job to resume and no stored report
 * (backend lost the job, or the run never got a job id). The page must show this as an error, not the start screen.
 */
export function nichtWiederherstellbareEvaluation(
  sitzung: EvaluationSitzung, jobId: string | null, evalId: string | null, berichtGespeichert: (id: string) => boolean,
): EvaluationEintrag | null {
  if (fortzusetzenderJob(sitzung, jobId, evalId, berichtGespeichert)) return null;
  const eintrag = [sitzung.aktuell, ...sitzung.historie].find((e) =>
    e && ((evalId && e.id === evalId) || (jobId && (e.jobId === jobId || e.id === jobId)))
  ) ?? (!evalId && !jobId ? sitzung.aktuell : null);
  if (!eintrag) return null;
  if (berichtGespeichert(eintrag.id) || (eintrag.jobId && berichtGespeichert(eintrag.jobId))) return null;
  return eintrag;
}

export function istBerichtGespeichert(id: string): boolean {
  const s = speicher();
  if (!s || !id) return false;
  try { return s.getItem(BERICHT_PRAEFIX + id) != null; } catch { return false; }
}

export function istNeuerAuftrag(search: string | URLSearchParams): boolean {
  const q = typeof search === "string" ? new URLSearchParams(search.startsWith("?") ? search.slice(1) : search) : search;
  return q.get("neu") === "1";
}

export function ladeBericht(id?: string | null): GespeicherterBericht | null {
  const s = speicher();
  if (!s) return null;
  const keys = id ? [BERICHT_PRAEFIX + id, AKTUELL_SCHLUESSEL] : [AKTUELL_SCHLUESSEL];
  for (const key of keys) {
    try {
      const roh = JSON.parse(s.getItem(key) ?? "null");
      if (roh && typeof roh.titel === "string" && roh.bericht?.lv) return roh as GespeicherterBericht;
    } catch { /* try the next key */ }
  }
  return null;
}

export function speichereBericht(titel: string, beispielId: string | null, bericht: Pruefbericht, id?: string | null): void {
  const s = speicher();
  if (!s) return;
  const payload = JSON.stringify({ titel, beispielId, bericht });
  const keys = [AKTUELL_SCHLUESSEL, ...(id ? [BERICHT_PRAEFIX + id] : [])];
  for (const key of keys) {
    try { s.setItem(key, payload); } catch { raeumeBerichte(s); try { s.setItem(key, payload); } catch { /* quota */ } }
  }
}

export function loescheOffenenBericht(): void {
  const s = speicher();
  if (!s) return;
  try { s.removeItem(AKTUELL_SCHLUESSEL); } catch { /* nothing stored */ }
}

function raeumeBerichte(s: Storage): void {
  const sitzung = ladeSitzung();
  const behalten = new Set<string>();
  if (sitzung.aktuell) behalten.add(BERICHT_PRAEFIX + sitzung.aktuell.id);
  for (const e of sitzung.historie) behalten.add(BERICHT_PRAEFIX + e.id);
  try {
    for (let i = s.length - 1; i >= 0; i--) {
      const key = s.key(i);
      if (key && key.startsWith(BERICHT_PRAEFIX) && !behalten.has(key)) s.removeItem(key);
    }
  } catch { /* ignore */ }
}

export function beobachteSitzung(hoer: () => void): () => void {
  hoerer.add(hoer);
  return () => { hoerer.delete(hoer); };
}

/** Recent items for the menu: the current one first, then the history, de-duplicated. */
export function evaluationListe(sitzung: EvaluationSitzung = ladeSitzung()): EvaluationEintrag[] {
  const liste: EvaluationEintrag[] = [];
  if (sitzung.aktuell) liste.push(sitzung.aktuell);
  for (const e of sitzung.historie) if (!liste.some((x) => x.id === e.id)) liste.push(e);
  return liste;
}
