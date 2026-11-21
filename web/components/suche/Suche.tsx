"use client";

import { useEffect, useRef } from "react";
import styles from "./suche.module.css";
import { useT } from "@/lib/einstellungen";

function tipptGerade(ziel: EventTarget | null) {
  return ziel instanceof HTMLElement && (ziel.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(ziel.tagName));
}

/** Search field for the review report: Escape clears it, "/" focuses it unless another field is being typed in. */
export function Suche({ wert, onAendern, zaehler }: {
  wert: string; onAendern: (wert: string) => void; zaehler: string | null;
}) {
  const eingabe = useRef<HTMLInputElement>(null);
  const t = useT();

  useEffect(() => {
    function taste(event: KeyboardEvent) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || tipptGerade(event.target)) return;
      event.preventDefault();
      eingabe.current?.focus();
    }
    document.addEventListener("keydown", taste);
    return () => document.removeEventListener("keydown", taste);
  }, []);

  return (
    <div className={styles.suche} role="search">
      <label htmlFor="pruefbericht-suche" className={styles.label}>{t("Search")}</label>
      <div className={styles.feld}>
        <input
          ref={eingabe} id="pruefbericht-suche" type="search" className={styles.eingabe} value={wert}
          placeholder={t("OZ prefix or text, e.g. 01.02 – press / to focus")} autoComplete="off" spellCheck={false}
          aria-describedby={zaehler ? "pruefbericht-suche-zaehler" : undefined}
          onChange={(event) => onAendern(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onAendern(""); } }}
        />
        {wert && (
          <button type="button" className={styles.leeren} aria-label={t("Clear search")}
            onClick={() => { onAendern(""); eingabe.current?.focus(); }}>×</button>
        )}
      </div>
      {zaehler && <span id="pruefbericht-suche-zaehler" className={styles.zaehler} aria-live="polite">{zaehler}</span>}
    </div>
  );
}
