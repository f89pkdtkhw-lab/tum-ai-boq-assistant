import type { Finding } from "./api";

/**
 * Norm check N4-UI (#83): pure helpers for the standards filter, the norm badge and the assumption marker.
 * Contract (api/app/pruefung/normen*.py): every norm-check rule ID starts with `NORM_`.
 */
export const NORM_PRAEFIX = "NORM_";
/** Prefix of an approval-required assumption note (ANNAHME_PRAEFIX in api/app/pruefung/normen.py, N3 #82). */
export const ANNAHME_PRAEFIX = "Assumption – approval required";

export function istNormFinding(f: Pick<Finding, "regel_id">): boolean {
  return typeof f.regel_id === "string" && f.regel_id.startsWith(NORM_PRAEFIX);
}

/** Findings for the "Standards" chip: all when `aktiv` is false, otherwise only NORM_* (AND with the other filters). */
export function filtereNormen<T extends Pick<Finding, "regel_id">>(findings: T[], aktiv: boolean): T[] {
  return aktiv ? findings.filter(istNormFinding) : findings;
}

const URL_MUSTER = /https?:\/\/[^\s<>"')\]]+/g;

/** Every http(s) URL in a text, trailing punctuation removed, without duplicates. */
export function quellenUrls(text: string | null | undefined): string[] {
  if (!text) return [];
  const treffer = (text.match(URL_MUSTER) ?? []).map((u) => u.replace(/[.,;:!?]+$/, ""));
  return [...new Set(treffer)];
}

/** An approval-required assumption: flagged by the backend or written with the N3 prefix (also in German). */
export function istAnnahme(note: { text?: string | null; approval_required?: boolean | null }): boolean {
  const text = (note.text ?? "").trimStart();
  return note.approval_required === true || text.startsWith(ANNAHME_PRAEFIX) || text.startsWith("Annahme – Freigabe");
}
