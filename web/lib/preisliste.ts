// Optional price list next to the bill (issue #115, epic #93 D4/B6).
import type { Preisliste } from "./api";

export const PREISLISTE_FORMATE = [".csv", ".xlsx", ".x84", ".d84", ".json"];

export function preislisteText(p: Preisliste): string {
  const n = p.eintraege.length;
  const teile = [`${n} ${n === 1 ? "entry" : "entries"}`];
  if (p.warnungen.length > 0) teile.push(`${p.warnungen.length} ${p.warnungen.length === 1 ? "warning" : "warnings"}`);
  return `${p.dateiname}: ${teile.join(", ")}`;
}
