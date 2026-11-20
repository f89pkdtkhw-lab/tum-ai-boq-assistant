"use client";

import { useId } from "react";
import { SEITENGROESSEN, zeilenText, type Seite } from "@/lib/seiten";
import styles from "./seiten.module.css";

const zahl = new Intl.NumberFormat("en-GB");

/**
 * Page controls for a report table: First/Previous/Next/Last, "rows X–Y of Z" and a page size selector.
 * Renders nothing while every row fits on the smallest page. `eingerueckt` pads it inside a bordered box.
 */
export function Seiten({ seite, groesse, beschriftung, onSeite, onGroesse, eingerueckt = false }: {
  seite: Seite; groesse: number; beschriftung: string; eingerueckt?: boolean;
  onSeite: (seite: number) => void; onGroesse: (groesse: number) => void;
}) {
  const id = useId();
  if (seite.gesamt <= SEITENGROESSEN[0]) return null;
  const erste = seite.seite === 0;
  const letzte = seite.seite >= seite.seiten - 1;

  return (
    <nav className={`${styles.seiten} ${eingerueckt ? styles.eingerueckt : ""}`} aria-label={beschriftung}>
      <div className={styles.knoepfe}>
        <button type="button" className={styles.knopf} disabled={erste} onClick={() => onSeite(0)}>First</button>
        <button type="button" className={styles.knopf} disabled={erste} onClick={() => onSeite(seite.seite - 1)}>Previous</button>
        <span className={styles.stand} aria-live="polite">
          Page {zahl.format(seite.seite + 1)} of {zahl.format(seite.seiten)} · {zeilenText(seite, zahl.format)}
        </span>
        <button type="button" className={styles.knopf} disabled={letzte} onClick={() => onSeite(seite.seite + 1)}>Next</button>
        <button type="button" className={styles.knopf} disabled={letzte} onClick={() => onSeite(seite.seiten - 1)}>Last</button>
      </div>
      <label className={styles.groesse} htmlFor={id}>
        Rows per page
        <select id={id} value={groesse} onChange={(e) => onGroesse(Number(e.target.value))}>
          {SEITENGROESSEN.map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      </label>
    </nav>
  );
}
