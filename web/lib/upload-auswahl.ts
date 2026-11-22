// Files picked on the start page before "Evaluate" (bill, regulation document, price list with their roles).
// File objects cannot go into sessionStorage, so they live in this module: it survives client-side navigation
// (Settings, Vault, back) but not a reload. Cleared when the evaluation starts or the user resets the list.
export type UploadRolle = "lv" | "regel" | "preise";
export type GemerkteDatei = { datei: File; rolle: UploadRolle };

let gemerkt: GemerkteDatei[] = [];

export function merkeAuswahl(liste: readonly GemerkteDatei[]): void {
  gemerkt = liste.map((d) => ({ ...d }));
}

export function ladeAuswahl(): GemerkteDatei[] {
  return gemerkt.map((d) => ({ ...d }));
}

export function leereAuswahl(): void {
  gemerkt = [];
}
