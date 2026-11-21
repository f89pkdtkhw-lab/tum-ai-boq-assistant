// Final report (schlussbericht, epic #93 B5; #167): rows for the UI table and the Excel sheet.
import type { Pruefbericht, SchlussPosition } from "./api";

/** A row with anything to say: a problem, a ± approximation, a change order, a warning or a recommendation. */
export const hatInhalt = (z: SchlussPosition) =>
  z.probleme.length > 0 || z.geschaetzt !== null || z.nachtrag.length > 0 || z.warnungen.length > 0 || z.empfehlungen.length > 0;

/** Rows to show: all, or only those with content (default; the full list stays in the export). */
export function schlussZeilen(bericht: Pick<Pruefbericht, "schlussbericht">, alle = false): SchlussPosition[] {
  const zeilen = bericht.schlussbericht?.positionen ?? [];
  return alle ? zeilen : zeilen.filter(hatInhalt);
}

const liste = (werte: string[]) => werte.join(" · ");

/** Excel sheet "Final report": project description, every item in LV order, general problems and warnings. */
export function schlussTabelle(bericht: Pick<Pruefbericht, "schlussbericht">): (string | number | null)[][] | null {
  const s = bericht.schlussbericht;
  if (!s) return null;
  return [
    ["Project", s.projektbeschreibung, null, "", null, null, null, "", "", "", "", ""],
    ["OZ", "Short description", "Quantity", "Unit", "Estimated", "±", "± (EUR)", "Why", "Need to add (Nachtrag)", "Problems", "Warnings", "Recommendations"],
    ...s.positionen.map((z) => [
      z.oz, z.kurztext, z.menge, z.einheit ?? "", z.geschaetzt, z.abweichung, z.abweichung_eur, z.warum, liste(z.nachtrag),
      liste(z.probleme.map((p) => `${p.titel} (${p.quelle === "modell" ? "model" : "rule"} ${p.regel_id})`)), liste(z.warnungen), liste(z.empfehlungen),
    ]),
    ...s.allgemein.map((p) => ["General", "", null, "", null, null, null, "", "", `${p.titel} (${p.quelle === "modell" ? "model" : "rule"} ${p.regel_id})`, "", ""]),
    ...s.warnungen.map((w) => ["Warning", "", null, "", null, null, null, "", "", "", w, ""]),
  ];
}
