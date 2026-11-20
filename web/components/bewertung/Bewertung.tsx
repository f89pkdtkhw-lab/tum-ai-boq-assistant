"use client";

import { useState } from "react";
import { STATUS, type Bewertung as BewertungDaten, type Status } from "@/lib/bewertung";
import styles from "./bewertung.module.css";

/** A findings list row with a compact status select beside it (a select cannot sit inside the row's button). */
export function MitStatus({ status, titel, onAendern, children }: {
  status: Status; titel: string; onAendern: (s: Status) => void; children: React.ReactNode;
}) {
  return (
    <div className={styles.zeile}>
      {children}
      <select className={`${styles.wahl} ${styles[status]}`} value={status} aria-label={`Review status: ${titel}`}
        onChange={(e) => onAendern(e.target.value as Status)}>
        {STATUS.map((s) => <option key={s.wert} value={s.wert}>{s.name}</option>)}
      </select>
    </div>
  );
}

/** Status buttons and comment in the finding detail. The comment is saved when the field loses focus. */
export function Bewertung({ bewertung, onAendern, speicherFehler }: {
  bewertung: BewertungDaten; onAendern: (a: Partial<BewertungDaten>) => void; speicherFehler: boolean;
}) {
  const [entwurf, setEntwurf] = useState(bewertung.kommentar);
  return (
    <div className={styles.bewertung}>
      <fieldset className={styles.gruppe}>
        <legend>Your review</legend>
        {STATUS.map((s) => (
          <button key={s.wert} type="button" aria-pressed={bewertung.status === s.wert}
            className={`${styles.knopf} ${bewertung.status === s.wert ? `${styles.aktiv} ${styles[s.wert]}` : ""}`}
            onClick={() => onAendern({ status: s.wert })}>
            {s.name}
          </button>
        ))}
      </fieldset>
      <label className={styles.label}>
        Comment (optional)
        <textarea className={styles.kommentar} rows={2} value={entwurf} placeholder="e.g. why you dismissed it"
          onChange={(e) => setEntwurf(e.target.value)}
          onBlur={() => { if (entwurf.trim() !== bewertung.kommentar) onAendern({ kommentar: entwurf }); }} />
      </label>
      <p className={styles.hinweis}>
        {speicherFehler
          ? "Browser storage is blocked: your review is kept only until you reload."
          : "Your decision, saved only in this browser. Findings are never reviewed automatically."}
      </p>
    </div>
  );
}
