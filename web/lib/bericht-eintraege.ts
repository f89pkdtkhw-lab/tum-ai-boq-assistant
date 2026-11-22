// Same grouping as the summary tiles in components/bericht (Issues / Warnings / Recommendations):
// issues = critical+high findings and red price outliers; warnings = medium+low findings and
// yellow outliers; recommendations = assessment and AI advice (not a finding severity).
import type { Finding } from "./api";

export const EINTRAG_TYPEN = ["issue", "warning", "rec"] as const;
export type EintragTyp = (typeof EINTRAG_TYPEN)[number];

export const TYP_NAME: Record<EintragTyp, string> = {
  issue: "Issues",
  warning: "Warnings",
  rec: "Recommendations",
};

/** Findings: kritisch/hoch → issue, mittel/niedrig → warning. Recommendations are never a severity. */
export function typFuerSchwere(schwere: Finding["schwere"]): Exclude<EintragTyp, "rec"> {
  return schwere === "kritisch" || schwere === "hoch" ? "issue" : "warning";
}

/** Price outliers counted in the tiles: red → issue, yellow → warning, green is omitted. */
export function typFuerPreisstufe(stufe: "rot" | "gelb" | "gruen"): EintragTyp | null {
  if (stufe === "gruen") return null;
  return stufe === "rot" ? "issue" : "warning";
}

export function eintraegeInTyp<T extends { typ: EintragTyp }>(liste: T[], typ: EintragTyp | null): T[] {
  return typ === null ? liste : liste.filter((x) => x.typ === typ);
}
