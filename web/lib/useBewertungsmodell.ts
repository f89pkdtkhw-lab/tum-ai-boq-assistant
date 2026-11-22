"use client";
import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_MODELL, beobachteBewertungsmodell, ladeBewertungsmodell, speichereBewertungsmodell,
  type Bewertungsmodell,
} from "./bewertungsmodell";

/** Shared scoring-model choice, persisted in localStorage and kept in sync across the page. */
export function useBewertungsmodell(): [Bewertungsmodell, (m: Bewertungsmodell) => void] {
  const [modell, setModell] = useState<Bewertungsmodell>(DEFAULT_MODELL);
  useEffect(() => {
    setModell(ladeBewertungsmodell());
    return beobachteBewertungsmodell(() => setModell(ladeBewertungsmodell()));
  }, []);
  const setze = useCallback((m: Bewertungsmodell) => {
    speichereBewertungsmodell(m);
    setModell(m);
  }, []);
  return [modell, setze];
}
