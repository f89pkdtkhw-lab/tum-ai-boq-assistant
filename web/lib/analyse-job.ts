// Background analysis with progress (#165): start the job, poll its status, return the finished report.
// The HTTP requests stay short; only the job on the server waits for long model calls or research.
import type { AnalyseJobAnfrage, AnalyseStatus, Pruefbericht } from "./api";

export type JobApi = {
  starteAnalyse: (body: AnalyseJobAnfrage) => Promise<{ job_id: string }>;
  analyseStatus: (jobId: string) => Promise<AnalyseStatus>;
};
export type JobOptionen = {
  /** Called with every new status, e.g. to draw the progress bar. */
  aufStand?: (stand: AnalyseStatus) => void;
  /** Called once the backend has accepted the job, so the id can be stored before the first poll. */
  aufStart?: (jobId: string) => void;
  /** Return false to stop polling (a newer run replaced this one); the promise then resolves with null. */
  aktiv?: () => boolean;
  intervallMs?: number;
  /** Status requests that may fail in a row (network blip) before the run counts as failed. */
  maxFehlversuche?: number;
  warte?: (ms: number) => Promise<void>;
};

/** Shown when the backend no longer has the job (restart, expired). */
export const JOB_VERLOREN_TEXT = "The analysis job was lost, probably because the backend restarted. Please try again.";
/** Running placeholder without a job id, or a link that cannot be restored from this session. */
export const JOB_NICHT_GESTARTET_TEXT = "The analysis had not started yet, or the job is no longer known to the backend. Please start a new evaluation.";

const schlafen = (ms: number) => new Promise<void>((fertig) => setTimeout(fertig, ms));

/** Readable error text of a failed job; the job's own messages first. */
export function jobFehlerText(stand: AnalyseStatus): string {
  return stand.fehler.length > 0 ? stand.fehler.join(" ") : stand.meldung || "The analysis failed.";
}

/**
 * Polls an already started analysis job until it finishes. Used when the user comes back to a
 * running evaluation. Same errors as `fuehreAnalyseAus`.
 */
export async function fuehreAnalyseWeiter(
  api: Pick<JobApi, "analyseStatus">, jobId: string, optionen: JobOptionen = {},
): Promise<{ bericht: Pruefbericht; stand: AnalyseStatus } | null> {
  const { aufStand, aktiv = () => true, intervallMs = 700, maxFehlversuche = 3, warte = schlafen } = optionen;
  let fehlversuche = 0;
  for (;;) {
    if (!aktiv()) return null;
    let stand: AnalyseStatus;
    try {
      stand = await api.analyseStatus(jobId);
      fehlversuche = 0;
    } catch (fehler) {
      if ((fehler as { status?: number }).status === 404) {
        throw new Error(JOB_VERLOREN_TEXT);
      }
      if (++fehlversuche >= maxFehlversuche) throw fehler;
      await warte(intervallMs);
      continue;
    }
    if (!aktiv()) return null;
    aufStand?.(stand);
    if (stand.status === "fertig" && stand.ergebnis) return { bericht: stand.ergebnis, stand };
    if (stand.status === "fehler") throw Object.assign(new Error(jobFehlerText(stand)), { stand });
    await warte(intervallMs);
  }
}

/**
 * Runs the analysis as a background job. Throws the start error unchanged (so a 404 of an older backend can
 * fall back to the synchronous route), a job failure as Error with its messages, and a lost job (backend
 * restarted) as Error. Resolves with the report and the last status.
 */
export async function fuehreAnalyseAus(
  api: JobApi, body: AnalyseJobAnfrage, optionen: JobOptionen = {},
): Promise<{ bericht: Pruefbericht; stand: AnalyseStatus } | null> {
  const { job_id } = await api.starteAnalyse(body);
  optionen.aufStart?.(job_id);
  return fuehreAnalyseWeiter(api, job_id, optionen);
}
