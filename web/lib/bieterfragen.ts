import type { Finding, Position } from "./api";

export type Bieterfrage = {
  id: string; oz: string; kurztext: string | null; titel: string; frage: string;
  schwere: Finding["schwere"]; kategorie: Finding["kategorie"];
};

const SCHWERE_RANG: Record<Finding["schwere"], number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const oz = new Intl.Collator("en", { numeric: true });

/** Risk and change-order findings as bidder questions, ordered by severity then OZ. Offline-model placeholders
 *  (rule IDs MOCK_*, contract in api/app/pruefung/llm_pruefung.py) are never real questions and are left out. */
export function bieterfragen(findings: Finding[], positionen: Position[]): Bieterfrage[] {
  const kurztexte = new Map<string, string>();
  for (const p of positionen) if (!kurztexte.has(p.oz) && p.kurztext) kurztexte.set(p.oz, p.kurztext);
  return findings
    .filter((f) => (f.kategorie === "risiko" || f.kategorie === "nachtrag") && !f.regel_id.startsWith("MOCK_"))
    .sort((a, b) => SCHWERE_RANG[a.schwere] - SCHWERE_RANG[b.schwere] || oz.compare(a.oz, b.oz))
    .map((f) => ({
      id: f.id, oz: f.oz, kurztext: kurztexte.get(f.oz) ?? null, titel: f.titel,
      frage: f.vorschlag.trim() || f.titel, schwere: f.schwere, kategorie: f.kategorie,
    }));
}

/** Plain-text list for the clipboard: one "OZ – question" per line. */
export function alsText(fragen: Bieterfrage[]): string {
  return fragen.map((f) => `${f.oz} – ${f.frage}`).join("\n");
}
