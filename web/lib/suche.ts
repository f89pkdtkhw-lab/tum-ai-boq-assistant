import type { Finding, Position } from "./api";

export type FindingFilter = { suche: string; kategorie: Finding["kategorie"] | null; schwere: Finding["schwere"] | null };

/** Case-insensitive, composed form so "Ü" typed or pasted in either Unicode form matches. */
export function normalisiere(text: string): string {
  return text.normalize("NFC").toLocaleLowerCase("de").trim();
}

function enthaelt(text: string, begriff: string) {
  return normalisiere(text).includes(begriff);
}

/** OZ prefix, short text or long text. An empty search matches everything. */
export function positionTrifft(position: Position, suche: string): boolean {
  const begriff = normalisiere(suche);
  if (!begriff) return true;
  return normalisiere(position.oz).startsWith(begriff) || enthaelt(position.kurztext, begriff) || enthaelt(position.langtext, begriff);
}

/**
 * A finding matches by its OZ prefix, title or explanation, or because its item's text matches,
 * and also passes the category and severity filters (AND).
 */
export function filtereFindings(findings: Finding[], positionen: Position[], filter: FindingFilter): Finding[] {
  const begriff = normalisiere(filter.suche);
  const treffendeOz = new Set(positionen.filter((p) => positionTrifft(p, begriff)).map((p) => p.oz));
  return findings.filter((f) =>
    (filter.kategorie === null || f.kategorie === filter.kategorie)
    && (filter.schwere === null || f.schwere === filter.schwere)
    && (!begriff || normalisiere(f.oz).startsWith(begriff) || enthaelt(f.titel, begriff)
      || enthaelt(f.begruendung, begriff) || treffendeOz.has(f.oz)));
}
