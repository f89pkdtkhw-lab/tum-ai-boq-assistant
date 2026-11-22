// Keyboard focus in a dropdown menu (components/ui/AuswahlMenue.tsx).

/** Index to focus after `taste` in a menu of `anzahl` items (wraps around), or null for keys the menu ignores. */
export function menueIndex(taste: string, aktuell: number, anzahl: number): number | null {
  if (anzahl <= 0) return null;
  switch (taste) {
    case "ArrowDown": return aktuell < 0 ? 0 : (aktuell + 1) % anzahl;
    case "ArrowUp": return aktuell < 0 ? anzahl - 1 : (aktuell - 1 + anzahl) % anzahl;
    case "Home": return 0;
    case "End": return anzahl - 1;
    default: return null;
  }
}
