import type { Finding, Position } from "./api";

const SCHWERE_RANG: Record<Finding["schwere"], number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };

export type TopPosition = {
  oz: string;
  /** Short text of the first item with this OZ; null if the OZ is not in the BoQ. */
  kurztext: string | null;
  schwere: Finding["schwere"];
  anzahl: number;
  /** Sum of the known euro_wirkung of rule findings; null if none is known (never 0 for unknown). */
  euro: number | null;
  /** True if every finding on this OZ comes from the model. */
  nurModell: boolean;
  /** Most severe finding, opened when the row is clicked. */
  findingId: string;
};

/** Positions with findings: severity, then known € (unknown last), then finding count, then OZ. */
export function topPositionen(findings: Finding[], positionen: Position[], limit: number): TopPosition[] {
  const gruppen = new Map<string, Finding[]>();
  for (const f of findings) gruppen.set(f.oz, [...(gruppen.get(f.oz) ?? []), f]);
  const kurztexte = new Map<string, string>();
  for (const p of positionen) if (!kurztexte.has(p.oz)) kurztexte.set(p.oz, p.kurztext);

  const zeilen = [...gruppen].map(([oz, liste]): TopPosition => {
    const schwerste = liste.reduce((a, b) => (SCHWERE_RANG[b.schwere] < SCHWERE_RANG[a.schwere] ? b : a));
    const bekannt = liste.filter((f) => f.quelle === "regel" && f.euro_wirkung !== null);
    return {
      oz,
      kurztext: kurztexte.get(oz) ?? null,
      schwere: schwerste.schwere,
      anzahl: liste.length,
      euro: bekannt.length > 0 ? bekannt.reduce((s, f) => s + (f.euro_wirkung ?? 0), 0) : null,
      nurModell: liste.every((f) => f.quelle === "modell"),
      findingId: schwerste.id,
    };
  });
  return zeilen
    .sort((a, b) =>
      SCHWERE_RANG[a.schwere] - SCHWERE_RANG[b.schwere]
      || (a.euro === null ? 1 : 0) - (b.euro === null ? 1 : 0)
      || (b.euro ?? 0) - (a.euro ?? 0)
      || b.anzahl - a.anzahl
      || a.oz.localeCompare(b.oz, "de", { numeric: true }))
    .slice(0, limit);
}
