"use client";
// User settings (language, theme, density), kept in this browser and applied to <html> as data attributes.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { uebersetze, type Sprache } from "./i18n";

export type Thema = "auto" | "light" | "dark";
export type Dichte = "normal" | "kompakt";
export type StartReiter = "uebersicht" | "findings" | "positionen";
export type Einstellungen = { sprache: Sprache; thema: Thema; dichte: Dichte; seitengroesse: 50 | 100 | 250; startReiter: StartReiter; mockAusblenden: boolean };

export const STANDARD: Einstellungen = { sprache: "en", thema: "auto", dichte: "normal", seitengroesse: 100, startReiter: "uebersicht", mockAusblenden: false };
export const EINSTELLUNGEN_SCHLUESSEL = "lv-einstellungen-v1";

/** Dark from 19:00 to 07:00 local time when the theme is "auto". */
export const nachts = (stunde: number) => stunde >= 19 || stunde < 7;

export function lies(roh: string | null): Einstellungen {
  try {
    const wert = JSON.parse(roh ?? "{}");
    return {
      sprache: wert.sprache === "de" ? "de" : "en",
      thema: ["light", "dark"].includes(wert.thema) ? wert.thema : "auto",
      dichte: wert.dichte === "kompakt" ? "kompakt" : "normal",
      seitengroesse: [50, 100, 250].includes(wert.seitengroesse) ? wert.seitengroesse : 100,
      startReiter: ["findings", "positionen"].includes(wert.startReiter) ? wert.startReiter : "uebersicht",
      mockAusblenden: wert.mockAusblenden === true,
    };
  } catch {
    return STANDARD;
  }
}

type Kontext = { e: Einstellungen; setze: (a: Partial<Einstellungen>) => void; t: (text: string, werte?: Record<string, string | number>) => string };
const EinstellungenKontext = createContext<Kontext>({ e: STANDARD, setze: () => {}, t: (text, werte) => uebersetze("en", text, werte) });

function anwenden(e: Einstellungen) {
  const html = document.documentElement;
  html.lang = e.sprache;
  html.dataset.dichte = e.dichte;
  html.dataset.theme = e.thema === "auto" ? (nachts(new Date().getHours()) ? "dark" : "light") : e.thema;
}

export function EinstellungenProvider({ children }: { children: React.ReactNode }) {
  const [e, setE] = useState<Einstellungen>(STANDARD);

  useEffect(() => {
    let geladen = STANDARD;
    try { geladen = lies(window.localStorage.getItem(EINSTELLUNGEN_SCHLUESSEL)); } catch { /* storage blocked: defaults */ }
    setE(geladen);
  }, []);

  useEffect(() => {
    anwenden(e);
    if (e.thema !== "auto") return;
    const uhr = window.setInterval(() => anwenden(e), 60_000);
    return () => window.clearInterval(uhr);
  }, [e]);

  const setze = useCallback((a: Partial<Einstellungen>) => {
    setE((alt) => {
      const neu = { ...alt, ...a };
      try { window.localStorage.setItem(EINSTELLUNGEN_SCHLUESSEL, JSON.stringify(neu)); } catch { /* kept until reload */ }
      return neu;
    });
  }, []);

  const t = useCallback((text: string, werte?: Record<string, string | number>) => uebersetze(e.sprache, text, werte), [e.sprache]);
  return <EinstellungenKontext.Provider value={{ e, setze, t }}>{children}</EinstellungenKontext.Provider>;
}

export const useEinstellungen = () => useContext(EinstellungenKontext);
/** Settings read synchronously, for initial state that must not flash the defaults first. */
export function liesJetzt(): Einstellungen {
  try { return lies(window.localStorage.getItem(EINSTELLUNGEN_SCHLUESSEL)); } catch { return STANDARD; }
}

/** Translator for the current language: t("{n} items", { n: 3 }). */
export const useT = () => useContext(EinstellungenKontext).t;
