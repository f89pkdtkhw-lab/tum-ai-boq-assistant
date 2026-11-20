import type { Position } from "./api";

export type Mengensumme = { schluessel: string; einheit: string; summe: number; positionen: number };
export type Titelsumme = { titel: string; summen: Record<string, number> };
export type Mengen = {
  einheiten: Mengensumme[];
  titel: Titelsumme[];
  ausserVertrag: number;
  ohneMenge: number;
};

export const OHNE_TITEL = "No section";

// Optional and alternative items are not part of the contract quantity.
const AUSSER_VERTRAG = new Set<Position["typ"]>(["bedarf", "alternativ"]);

/** Grouping key of a summed item, or null if the item is not summed. Units are never converted. */
export function mengenSchluessel(position: Position): string | null {
  if (AUSSER_VERTRAG.has(position.typ)) return null;
  const einheit = position.einheit?.trim();
  if (!einheit || position.menge === null || !Number.isFinite(position.menge)) return null;
  return einheit.toLowerCase();
}

/** Sum quantities per unit and per top-level title (titel_pfad[0]). */
export function mengenSummen(positionen: Position[]): Mengen {
  const einheiten = new Map<string, Mengensumme>();
  const titel = new Map<string, Titelsumme>();
  let ausserVertrag = 0;
  let ohneMenge = 0;

  for (const position of positionen) {
    if (AUSSER_VERTRAG.has(position.typ)) { ausserVertrag += 1; continue; }
    const schluessel = mengenSchluessel(position);
    if (schluessel === null) { ohneMenge += 1; continue; }
    const menge = position.menge as number;

    const summe = einheiten.get(schluessel)
      ?? { schluessel, einheit: (position.einheit as string).trim(), summe: 0, positionen: 0 };
    summe.summe += menge;
    summe.positionen += 1;
    einheiten.set(schluessel, summe);

    const name = position.titel_pfad[0]?.trim() || OHNE_TITEL;
    const zeile = titel.get(name) ?? { titel: name, summen: {} };
    zeile.summen[schluessel] = (zeile.summen[schluessel] ?? 0) + menge;
    titel.set(name, zeile);
  }

  return {
    einheiten: [...einheiten.values()].sort((a, b) => b.positionen - a.positionen),
    titel: [...titel.values()],
    ausserVertrag,
    ohneMenge,
  };
}
