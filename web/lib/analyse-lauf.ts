// One background poller per analysis job, independent of the mounted page. The start page used to poll
// inside its own component, so leaving it (Settings, Vault) stopped the polling: the menu chip froze at the
// last percent and the finished report was never saved. Pages now subscribe to the job here instead.
// After a tab reload the in-memory poller is gone; verfolgeSitzungsJobs restarts it from lv-eval-sitzung-v1
// so the chip keeps advancing on any page, including Settings.
import type { AnalyseStatus, Pruefbericht } from "./api";
import { fuehreAnalyseWeiter, type JobApi, type JobOptionen } from "./analyse-job";
import { aktualisiereEvaluation, evaluationListe, ladeSitzung, speichereBericht } from "./evaluation-session";

export type JobErgebnis = { bericht: Pruefbericht; stand: AnalyseStatus };
/** Session side effects of a job (progress, saved report); they run once per job, whichever page is open. */
export type JobHaken = {
  aufStand?: (stand: AnalyseStatus) => void;
  aufFertig?: (ergebnis: JobErgebnis) => void;
  aufFehler?: (fehler: unknown) => void;
};

type Lauf = { ergebnis: Promise<JobErgebnis>; letzter: AnalyseStatus | null; hoerer: Set<(stand: AnalyseStatus) => void> };
const laeufe = new Map<string, Lauf>();

function eintragFuerJob(jobId: string) {
  const sitzung = ladeSitzung();
  return [sitzung.aktuell, ...sitzung.historie].find((e) => e && (e.jobId === jobId || e.id === jobId)) ?? null;
}

function sitzungsHaken(jobId: string): JobHaken {
  const idFuer = () => eintragFuerJob(jobId)?.id ?? jobId;
  return {
    aufStand: (stand) => aktualisiereEvaluation(idFuer(), { status: "laeuft", prozent: stand.prozent, meldung: stand.meldung }),
    aufFertig: ({ bericht }) => {
      const e = eintragFuerJob(jobId);
      speichereBericht(e?.titel ?? "Evaluation", null, bericht, e?.id ?? jobId);
      aktualisiereEvaluation(e?.id ?? jobId, { status: "fertig", prozent: 100, meldung: "" });
    },
    aufFehler: (fehler) => aktualisiereEvaluation(
      idFuer(),
      { status: "fehler", meldung: fehler instanceof Error && fehler.message ? fehler.message : "Unknown error." },
    ),
  };
}

/**
 * Starts polling `jobId` in the background, or joins the poller that already runs for it. The hooks of the
 * first call apply; the promise resolves with the report or rejects with the job error (see analyse-job.ts).
 * Progress, the finished report and failures are always written to the evaluation session, so the menu chip
 * keeps moving after a reload even when no page hook was registered yet.
 */
export function verfolgeJob(
  api: Pick<JobApi, "analyseStatus">, jobId: string, haken: JobHaken = {},
  optionen: Pick<JobOptionen, "intervallMs" | "maxFehlversuche" | "warte"> = {},
): Promise<JobErgebnis> {
  const laufend = laeufe.get(jobId);
  if (laufend) return laufend.ergebnis;
  const session = sitzungsHaken(jobId);
  const lauf: Lauf = { ergebnis: Promise.resolve(null as unknown as JobErgebnis), letzter: null, hoerer: new Set() };
  lauf.ergebnis = fuehreAnalyseWeiter(api, jobId, {
    ...optionen,
    aufStand: (stand) => {
      lauf.letzter = stand;
      session.aufStand?.(stand);
      haken.aufStand?.(stand);
      lauf.hoerer.forEach((h) => h(stand));
    },
  }).then((ende) => {
    const ergebnis = ende as JobErgebnis; // never null: polling has no stop condition here
    session.aufFertig?.(ergebnis);
    haken.aufFertig?.(ergebnis);
    return ergebnis;
  }, (fehler) => {
    session.aufFehler?.(fehler);
    haken.aufFehler?.(fehler);
    throw fehler;
  }).finally(() => { laeufe.delete(jobId); });
  lauf.ergebnis.catch(() => { /* handled by the hooks and by whoever awaits it */ });
  laeufe.set(jobId, lauf);
  return lauf.ergebnis;
}

/** Live status of a tracked job for the page that shows it; the last known status is sent at once. */
export function beobachteJob(jobId: string, hoer: (stand: AnalyseStatus) => void): () => void {
  const lauf = laeufe.get(jobId);
  if (!lauf) return () => {};
  lauf.hoerer.add(hoer);
  if (lauf.letzter) hoer(lauf.letzter);
  return () => { lauf.hoerer.delete(hoer); };
}

export function wirdVerfolgt(jobId: string): boolean {
  return laeufe.has(jobId);
}

/**
 * After a tab reload the in-memory pollers are gone. Restart every running session job so the chip
 * keeps advancing on Settings and the finished report is saved without going back to the start page.
 */
export function verfolgeSitzungsJobs(
  api: Pick<JobApi, "analyseStatus">,
  optionen: Pick<JobOptionen, "intervallMs" | "maxFehlversuche" | "warte"> = {},
): string[] {
  const ids: string[] = [];
  for (const e of evaluationListe()) {
    if (e.status === "laeuft" && e.jobId && !wirdVerfolgt(e.jobId)) {
      verfolgeJob(api, e.jobId, {}, optionen);
      ids.push(e.jobId);
    }
  }
  return ids;
}
