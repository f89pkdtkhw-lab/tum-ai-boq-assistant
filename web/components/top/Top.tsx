"use client";

import { useMemo, useState } from "react";
import type { Finding, Position } from "@/lib/api";
import { topPositionen } from "@/lib/top";
import styles from "./top.module.css";

const SCHWERE_NAME: Record<Finding["schwere"], string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
const GROESSEN = [10, 25, 100];
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });

/** "Look at these first": positions with findings, ranked; a click opens the existing detail. */
export function Top({ findings, positionen, onWaehle }: {
  findings: Finding[]; positionen: Position[]; onWaehle: (oz: string, findingId: string) => void;
}) {
  const [groesse, setGroesse] = useState(10);
  const alle = useMemo(() => topPositionen(findings, positionen, Infinity), [findings, positionen]);
  const zeilen = alle.slice(0, groesse);

  return (
    <section className={styles.top} aria-labelledby="top-titel">
      <div className={styles.kopf}>
        <h3 id="top-titel" className={styles.titel}>
          Look at these first <span className={styles.anzahl}>{zeilen.length} of {alle.length} items</span>
        </h3>
        {alle.length > 0 && (
          <div className={styles.umschalter} role="group" aria-label="Number of items shown">
            {GROESSEN.map((g) => (
              <button key={g} type="button" className={`${styles.chip} ${groesse === g ? styles.chipAktiv : ""}`}
                aria-pressed={groesse === g} onClick={() => setGroesse(g)}>Top {g}</button>
            ))}
          </div>
        )}
      </div>
      <p className={styles.hinweis}>Ordered by severity, then known € effect, then number of findings; no prices are estimated.</p>
      {alle.length === 0 ? (
        <p className={styles.hinweis}>No item has a finding.</p>
      ) : (
        <ol className={styles.liste}>
          {zeilen.map((z, i) => (
            <li key={z.oz}>
              <button type="button" className={`${styles.zeile} ${z.nurModell ? styles.mock : ""}`}
                onClick={() => onWaehle(z.oz, z.findingId)} aria-label={`Show item ${z.oz}`}>
                <span className={styles.rang}>{i + 1}</span>
                <span className={styles.oz}>{z.oz}</span>
                <span className={styles.text}>{z.kurztext || <em className={styles.unbekannt}>{z.kurztext === null ? "not in BoQ" : "short text unknown"}</em>}</span>
                <span className={styles.merkmale}>
                  <span className={styles.marke}>{SCHWERE_NAME[z.schwere]}</span>
                  <span className={styles.marke}>{z.anzahl} {z.anzahl === 1 ? "finding" : "findings"}</span>
                  <span className={styles.euro}>{z.euro === null ? <em className={styles.unbekannt}>unknown</em> : euro.format(z.euro)}</span>
                  {z.nurModell && <span className={styles.markeMock}>Mock</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
