// D (#168): which AI steps failed or fell back to the offline mock, for the visible notice in the report.
import type { AiEvaluation, KiSchritt, Pruefbericht } from "./api";

export type KiHinweis = KiSchritt & { status: "mock" | "fehler" };

const TITEL: Record<string, string> = {
  positionspruefung: "AI position review", normrecherche: "AI norm research", evaluation: "AI evaluation",
  vergleich: "AI check 2 (similar projects)", was_wenn: "AI check 3 (what-if)",
};

/**
 * Steps that did not run as configured, in report order. Sources: `ki_schritte` (backend #168), else the older
 * `kennzahlen.modell_reason` (#147); failed Reports 2/3; and the browser-side AI evaluation (answer or error).
 * A mock chosen by configuration (no key) is not listed: the demo-mode notice covers it.
 */
export function kiHinweise(bericht: Pruefbericht, ki?: { daten: AiEvaluation | null; fehler: string }): KiHinweis[] {
  const liste: KiHinweis[] = (bericht.ki_schritte ?? []).filter((s): s is KiHinweis => s.status === "mock" || s.status === "fehler");
  const hat = (id: string) => (bericht.ki_schritte ?? []).some((s) => s.schritt === id) || liste.some((s) => s.schritt === id);
  const dazu = (schritt: string, status: KiHinweis["status"], grund: string | null | undefined) => {
    if (!hat(schritt)) liste.push({ schritt, titel: TITEL[schritt] ?? schritt, status, grund: grund || null });
  };
  if (bericht.kennzahlen.modell_mock && bericht.kennzahlen.modell_reason) dazu("positionspruefung", "mock", bericht.kennzahlen.modell_reason);
  for (const b of bericht.berichte ?? []) if (b.id !== "regelwerk" && b.status === "fehler") dazu(b.id, "fehler", b.meldung);
  if (ki?.fehler) dazu("evaluation", "fehler", ki.fehler);
  else if (ki?.daten?.reason) dazu("evaluation", "mock", ki.daten.reason);
  return liste;
}
