"use client";

import type { Pruefbericht } from "@/lib/api";
import { abweichungText, punkteText, scoreText, uebersicht, type Gruppe } from "@/lib/zusammenfassung";
import styles from "./zusammenfassung.module.css";

const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });
const zahl = new Intl.NumberFormat("en-GB");

const ZAEHLER: { gruppe: Gruppe; name: string; feld: "grosseProbleme" | "warnungen"; hinweis: string }[] = [
  { gruppe: "gross", name: "Big problems", feld: "grosseProbleme", hinweis: "critical and high" },
  { gruppe: "warnung", name: "Warnings", feld: "warnungen", hinweis: "medium" },
];

/** First row after the analysis: score, estimate, big problems, warnings, recommendations (issue #103). */
export function Zusammenfassung({ bericht, aktiv, onWaehle }: {
  bericht: Pruefbericht; aktiv: Gruppe | null; onWaehle: (gruppe: Gruppe | null) => void;
}) {
  const u = uebersicht(bericht);
  return (
    <section className={styles.zusammenfassung} aria-label="Summary">
      <div className={`${styles.kachel} ${styles.score}`}>
        <span className={styles.name}>Score</span>
        <span className={styles.wert}>{scoreText(u.score)}</span>
        {u.score === null ? (
          <small>not computed by this backend</small>
        ) : u.abzuege.length === 0 ? (
          <small>no deductions</small>
        ) : (
          <details className={styles.abzuege}>
            <summary>{u.abzuege.length} {u.abzuege.length === 1 ? "deduction" : "deductions"}</summary>
            <ul>{u.abzuege.map((a, i) => <li key={i}><span className={styles.punkte}>{punkteText(a.punkte)}</span> {a.grund}</li>)}</ul>
          </details>
        )}
      </div>
      <div className={styles.kachel}>
        <span className={styles.name}>Estimate</span>
        <span className={`${styles.wert} ${u.abweichung === null ? styles.leer : ""}`}>{abweichungText(u.abweichung, euro.format)}</span>
        <small>{u.abweichung === null ? "history not connected" : "deviation from similar projects"}</small>
      </div>
      {ZAEHLER.map((z) => (
        <button key={z.gruppe} type="button" className={`${styles.kachel} ${styles.knopf} ${z.gruppe === "gross" && u[z.feld] > 0 ? styles.kritisch : ""} ${aktiv === z.gruppe ? styles.aktiv : ""}`}
          aria-pressed={aktiv === z.gruppe} onClick={() => onWaehle(aktiv === z.gruppe ? null : z.gruppe)}
          title={aktiv === z.gruppe ? "Show all findings" : `Show only ${z.name.toLowerCase()}`}>
          <span className={styles.name}>{z.name}</span>
          <span className={styles.wert}>{zahl.format(u[z.feld])}</span>
          <small>{aktiv === z.gruppe ? "filter on · click to clear" : z.hinweis}</small>
        </button>
      ))}
      <div className={styles.kachel}>
        <span className={styles.name}>Recommendations</span>
        <span className={`${styles.wert} ${u.empfehlungen === null ? styles.leer : ""}`}>{u.empfehlungen === null ? "–" : zahl.format(u.empfehlungen)}</span>
        <small>{u.empfehlungen === null ? "not computed by this backend" : `${zahl.format(u.hinweise)} notices besides`}</small>
      </div>
      {u.fallback && (
        <p className={styles.hinweis}>Counts computed in the browser: this backend sends no summary, so score and recommendations are unknown.</p>
      )}
    </section>
  );
}
