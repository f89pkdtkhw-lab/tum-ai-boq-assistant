// Step-by-step review flow (upload → review → findings → price → margin → export).
// The current step lives in the URL (`?schritt=`), the report in the existing session stores.
import type { Finding, RechercheErgebnis } from "./api";

export const WIZARD_IDS = ["hochladen", "pruefen", "fehler", "preis", "marge", "export"] as const;
export type WizardSchritt = (typeof WIZARD_IDS)[number];

export const WIZARD_SCHRITTE: { id: WizardSchritt; href: string; label: string }[] = [
  { id: "hochladen", href: "/", label: "Upload BoQ" },
  { id: "pruefen", href: "/", label: "Review" },
  { id: "fehler", href: "/", label: "Resolve findings" },
  { id: "preis", href: "/", label: "Evaluate price" },
  { id: "marge", href: "/marge", label: "Set margin" },
  { id: "export", href: "/export", label: "Final price & export" },
];

export const LADE_STUFEN = [
  "Reading the PDF",
  "Items detected",
  "Review running",
  "Done",
] as const;

export const WIZARD_WEITER: Record<WizardSchritt, string> = {
  hochladen: "Continue to review",
  pruefen: "Continue to findings",
  fehler: "Evaluate price",
  preis: "Continue to margin",
  marge: "Continue to export",
  export: "Export offer",
};

const INDEX: Record<WizardSchritt, number> = Object.fromEntries(WIZARD_IDS.map((id, i) => [id, i])) as Record<WizardSchritt, number>;

export function schrittIndex(id: WizardSchritt): number {
  return INDEX[id];
}

export function istWizardSchritt(wert: string | null | undefined): wert is WizardSchritt {
  return !!wert && (WIZARD_IDS as readonly string[]).includes(wert);
}

/** Read `?schritt=` or infer from the path (`/marge`, `/export`). Unknown values fall back to the first step. */
export function leseSchritt(raw: string | null | undefined, pathname = "/"): WizardSchritt {
  if (istWizardSchritt(raw)) return raw;
  if (pathname === "/marge" || pathname.startsWith("/marge/")) return "marge";
  if (pathname === "/export" || pathname.startsWith("/export/")) return "export";
  return "hochladen";
}

export function wizardPfad(id: WizardSchritt): string {
  const s = WIZARD_SCHRITTE.find((x) => x.id === id)!;
  return `${s.href}?schritt=${id}`;
}

/**
 * Where the wizard sends the URL when the requested step is ahead of the review, or null for no redirect.
 * A link back to an evaluation (`eval` / `job`, lib/evaluation-session.ts) waits: the page first restores the
 * report or job and reports its status. Redirecting earlier dropped those params and showed the start page.
 */
export function wizardUmleitung(gewuenscht: WizardSchritt, schritt: WizardSchritt, search: { has(name: string): boolean }): string | null {
  if (gewuenscht === schritt) return null;
  if (search.has("eval") || search.has("job")) return null;
  return wizardPfad(schritt);
}


/** The progress bar is shown on the six flow pages; other menu pages stay as they are. */
export function wizardSichtbar(pathname: string): boolean {
  return pathname === "/" || pathname === "/marge" || pathname === "/export"
    || pathname.startsWith("/marge/") || pathname.startsWith("/export/");
}

export function maxSchritt(status: { hatBericht: boolean; laeuft: boolean }): WizardSchritt {
  if (status.hatBericht) return "export";
  if (status.laeuft) return "pruefen";
  return "hochladen";
}

/** Clamp a requested step so it is not ahead of what the current review has actually reached. */
export function effektiverSchritt(wunsch: WizardSchritt, status: { hatBericht: boolean; laeuft: boolean }, seite?: WizardSchritt): WizardSchritt {
  const max = schrittIndex(maxSchritt(status));
  const seiten = seite ? schrittIndex(seite) : 0;
  const oben = Math.max(max, seiten);
  return schrittIndex(wunsch) > oben ? WIZARD_IDS[oben] : wunsch;
}

/**
 * Step shown in the wizard. While an evaluation link (`eval` / `job`) is being restored, keep the requested
 * step even if the report is not in React state yet. Clamping to "hochladen" hid the error or progress view
 * and looked like a silent return to the start page.
 */
export function wizardAnzeigeSchritt(
  gewuenscht: WizardSchritt, status: { hatBericht: boolean; laeuft: boolean }, seite: WizardSchritt | undefined,
  search: { has(name: string): boolean },
): WizardSchritt {
  const geklemmt = effektiverSchritt(gewuenscht, status, seite);
  if (gewuenscht !== geklemmt && wizardUmleitung(gewuenscht, geklemmt, search) === null) return gewuenscht;
  return geklemmt;
}

/**
 * Map the import / analysis job to four plain-language stages.
 * Stage 1: the file is being read; 2: items are in; 3: the review job is running; 4: done.
 * Live job details (percent, "step 3 of 8", finished steps) are shown in Ladeanzeige when a stand is present.
 */
export function ladeStufe(input: {
  phase: "leer" | "laeuft" | "fertig" | "fehler";
  importFertig?: boolean;
  standStatus?: "laeuft" | "fertig" | "fehler" | null;
}): { stufe: 1 | 2 | 3 | 4; aktiv: boolean } {
  if (input.phase === "fertig") return { stufe: 4, aktiv: false };
  if (input.phase === "leer") return { stufe: 1, aktiv: false };
  const stand = input.standStatus ?? null;
  if (input.phase === "fehler") {
    if (stand) return { stufe: 3, aktiv: false };
    return { stufe: input.importFertig ? 2 : 1, aktiv: false };
  }
  if (stand === "laeuft" || stand === "fertig") return { stufe: 3, aktiv: stand === "laeuft" };
  if (input.importFertig) return { stufe: 2, aktiv: true };
  return { stufe: 1, aktiv: true };
}

/** Live job figures for the review progress box. Null until the analysis job has reported a step total. */
export function liveFortschritt(stand: { schritt?: number; schritte_gesamt?: number; prozent?: number } | null | undefined): {
  schritt: number; gesamt: number; prozent: number;
} | null {
  if (!stand || stand.schritte_gesamt == null || stand.schritte_gesamt < 1) return null;
  const gesamt = stand.schritte_gesamt;
  const schritt = Math.max(1, Math.min(Number(stand.schritt) || 1, gesamt));
  const roh = Number(stand.prozent);
  const prozent = Math.max(0, Math.min(100, Number.isFinite(roh) ? Math.round(roh) : 0));
  return { schritt, gesamt, prozent };
}


/**
 * Research rows for one finding: prefer an exact `finding_id` match, otherwise rows for the same OZ
 * (price research often has `oz` but no `finding_id`).
 */
export function rechercheZumBefund(ergebnisse: RechercheErgebnis[] | null | undefined, finding: Finding): RechercheErgebnis[] {
  const liste = ergebnisse ?? [];
  const direkt = liste.filter((r) => r.finding_id === finding.id);
  if (direkt.length > 0) return direkt;
  // Price research often has the OZ but no finding_id; skip rows already tied to another finding.
  return liste.filter((r) => r.oz === finding.oz && (r.finding_id == null || r.finding_id === finding.id));
}

export const MARGE_SPEICHER = "lv-marge-v1";

export type MargeStand = {
  angebot: number;
  gewinn: number;
  marge: number;
  median: number | null;
  monate: number;
  bieter: number;
  ausreisserAus: boolean;
};

export function speichereMargeStand(stand: MargeStand): void {
  try { window.sessionStorage.setItem(MARGE_SPEICHER, JSON.stringify(stand)); } catch { /* blocked or full */ }
}

export function ladeMargeStand(): MargeStand | null {
  try {
    const roh = JSON.parse(window.sessionStorage.getItem(MARGE_SPEICHER) ?? "null");
    if (!roh || typeof roh.angebot !== "number" || typeof roh.marge !== "number") return null;
    return roh as MargeStand;
  } catch {
    return null;
  }
}
