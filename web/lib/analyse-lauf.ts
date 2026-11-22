// One background poller per analysis job, independent of the mounted page. The start page used to poll
// inside its own component, so leaving it (Settings, Vault) stopped the polling: the menu chip froze at the
// last percent and the finished report was never saved. Pages now subscribe to the job here instead.
import type { AnalyseStatus, Pruefbericht } from "./api";
import { fuehreAnalyseWeiter, type JobApi, type JobOptionen } from "./analyse-job";

export type JobErgebnis = { bericht: Pruefbericht; stand: AnalyseStatus };
/** Session side effects of a job (progress, saved report); they run once per job, whichever page is open. */
export type JobHaken = {
  aufStand?: (stand: AnalyseStatus) => void;
  aufFertig?: (ergebnis: JobErgebnis) => void;
  aufFehler?: (fehler: unknown) => void;
};

type Lauf = { ergebnis: Promise<JobErgebnis>; letzter: AnalyseStatus | null; hoerer: Set<(stand: AnalyseStatus) => void> };
const laeufe = new Map<string, Lauf>();

/**
 * Starts polling `jobId` in the background, or joins the poller that already runs for it. The hooks of the
 * first call apply; the promise resolves with the report or rejects with the job error (see analyse-job.ts).
 */
export function verfolgeJob(
  api: Pick<JobApi, "analyseStatus">, jobId: string, haken: JobHaken = {},
  optionen: Pick<JobOptionen, "intervallMs" | "maxFehlversuche" | "warte"> = {},
): Promise<JobErgebnis> {
  const laufend = laeufe.get(jobId);
  if (laufend) return laufend.ergebnis;
  const lauf: Lauf = { ergebnis: Promise.resolve(null as unknown as JobErgebnis), letzter: null, hoerer: new Set() };
  lauf.ergebnis = fuehreAnalyseWeiter(api, jobId, {
    ...optionen,
    aufStand: (stand) => {
      lauf.letzter = stand;
      haken.aufStand?.(stand);
      lauf.hoerer.forEach((h) => h(stand));
    },
  }).then((ende) => {
    const ergebnis = ende as JobErgebnis; // never null: polling has no stop condition here
    haken.aufFertig?.(ergebnis);
    return ergebnis;
  }, (fehler) => {
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
