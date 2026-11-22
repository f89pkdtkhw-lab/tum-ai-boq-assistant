"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef } from "react";
import { menueIndex } from "@/lib/menue";
import styles from "./AuswahlMenue.module.css";

export type MenueEintrag = { key: string; label: string; onClick: () => void };

/**
 * A button with a dropdown menu right under it (instead of a bottom sheet). `eintraege === null` means closed.
 * Closes on outside click, Escape, Tab and after a choice; arrow keys, Home and End move between the items.
 */
export function AuswahlMenue({ knopfKlasse, knopfInhalt, label, disabled, eintraege, leerText, ausrichtung = "links", onOeffnen, onSchliessen }: {
  knopfKlasse?: string;
  knopfInhalt: ReactNode;
  label: string;
  disabled?: boolean;
  eintraege: MenueEintrag[] | null;
  leerText: string;
  ausrichtung?: "links" | "mitte";
  onOeffnen: () => void;
  onSchliessen: () => void;
}) {
  const offen = eintraege !== null;
  const huelle = useRef<HTMLSpanElement>(null);
  const knopf = useRef<HTMLButtonElement>(null);
  const liste = useRef<HTMLDivElement>(null);
  const schliessen = useRef(onSchliessen);
  schliessen.current = onSchliessen;
  const id = useId();
  const punkte = () => [...(liste.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];

  useEffect(() => {
    if (!offen) return;
    // A button near the right edge (margin page): open the menu leftwards so it stays on screen.
    const menue = liste.current;
    if (menue && menue.getBoundingClientRect().right > window.innerWidth - 8) menue.classList.add(styles.rechts);
    punkte()[0]?.focus();
    const aussen = (e: PointerEvent) => { if (!huelle.current?.contains(e.target as Node)) schliessen.current(); };
    document.addEventListener("pointerdown", aussen);
    return () => document.removeEventListener("pointerdown", aussen);
  }, [offen]);

  function taste(e: KeyboardEvent) {
    if (!offen) return;
    if (e.key === "Escape") { e.preventDefault(); onSchliessen(); knopf.current?.focus(); return; }
    if (e.key === "Tab") { onSchliessen(); return; }
    const alle = punkte();
    const i = menueIndex(e.key, alle.indexOf(document.activeElement as HTMLButtonElement), alle.length);
    if (i !== null) { e.preventDefault(); alle[i].focus(); }
  }

  return (
    <span ref={huelle} className={styles.huelle} onKeyDown={taste}>
      <button ref={knopf} type="button" className={knopfKlasse} disabled={disabled}
        aria-haspopup="menu" aria-expanded={offen} aria-controls={offen ? id : undefined}
        onClick={() => (offen ? onSchliessen() : onOeffnen())}>
        {knopfInhalt}
      </button>
      {offen && (
        <div ref={liste} id={id} role="menu" aria-label={label} className={`${styles.menue} ${ausrichtung === "mitte" ? styles.mitte : ""}`}>
          {eintraege.length === 0 ? <p className={styles.leer}>{leerText}</p> : eintraege.map((x) => (
            <button key={x.key} type="button" role="menuitem" className={styles.eintrag} title={x.label}
              onClick={() => { onSchliessen(); knopf.current?.focus(); x.onClick(); }}>
              {x.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
