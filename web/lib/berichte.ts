// Detail view of the three reports, final report and what-if list (issue #104, epic #93 B5).
import type { Bericht, BerichtId, Finding, Pruefbericht, WasWenn } from "./api";

export type TabId = BerichtId | "endbericht";

export const TABS: { id: TabId; name: string }[] = [
  { id: "regelwerk", name: "Report 1 · Regulations" },
  { id: "vergleich", name: "Report 2 · Similar projects" },
  { id: "was_wenn", name: "Report 3 · What-if" },
  { id: "endbericht", name: "Final report" },
];

export type Abschnitt = {
  bericht: Bericht;
  findings: Finding[];
  /** Finding ids the report names that are not in `findings` (shown, never hidden). */
  fehlend: string[];
  /** Friendly empty or error text, or null when the report has content. */
  leer: string | null;
};

export function hatBerichte(bericht: Pick<Pruefbericht, "berichte">): boolean {
  return Array.isArray(bericht.berichte) && bericht.berichte.length > 0;
}

function leerText(b: Bericht, hatInhalt: boolean): string | null {
  // The backend message already explains the missing connection; the default covers an empty one.
  if (b.status === "nicht_verbunden") return b.meldung || "History database not connected.";
  if (b.status === "fehler") return `This report could not be created.${b.meldung ? ` ${b.meldung}` : ""}`;
  return hatInhalt ? null : b.meldung || "Nothing to report.";
}

/** One section per report in the backend's order, findings resolved from `finding_ids`. */
export function abschnitte(bericht: Pick<Pruefbericht, "berichte" | "findings">): Abschnitt[] {
  const nachId = new Map(bericht.findings.map((f) => [f.id, f]));
  return (bericht.berichte ?? []).map((b) => {
    const findings = b.finding_ids.flatMap((id) => nachId.get(id) ?? []);
    const fehlend = b.finding_ids.filter((id) => !nachId.has(id));
    const inhalt = findings.length + fehlend.length + b.notes.length + (b.naeherungen?.length ?? 0) + (b.probleme?.length ?? 0) + b.neue_tags.length > 0;
    return { bericht: b, findings, fehlend, leer: leerText(b, inhalt) };
  });
}

/** What-if list: high chance first, original order otherwise. */
export function wasWennListe(bericht: Pick<Pruefbericht, "was_wenn" | "berichte">): WasWenn[] {
  const liste = bericht.was_wenn ?? bericht.berichte?.find((b) => b.id === "was_wenn")?.probleme ?? [];
  return liste.map((w, i) => ({ w, i })).sort((a, b) => Number(a.w.chance !== "hoch") - Number(b.w.chance !== "hoch") || a.i - b.i).map(({ w }) => w);
}

export function chanceName(chance: WasWenn["chance"]): string {
  return chance === "hoch" ? "High chance" : "Low chance";
}

/** "+12 %" / "−8.5 %" with a real minus sign. */
export function prozentText(wert: number): string {
  const betrag = Math.round(Math.abs(wert) * 10) / 10;
  return `${wert > 0 ? "+" : wert < 0 ? "−" : "±"}${betrag} %`;
}
