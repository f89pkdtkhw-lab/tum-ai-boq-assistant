"use client";

import { useState } from "react";
import { OHNE_TITEL_NAME, type Titelknoten } from "@/lib/titelbaum";
import styles from "./titelbaum.module.css";
import { useT } from "@/lib/einstellungen";

const SCHWERE_NAME = { kritisch: "critical", hoch: "high", mittel: "medium", niedrig: "low" } as const;

function gleich(a: string[] | null, b: string[]) {
  return a !== null && a.length === b.length && a.every((t, i) => t === b[i]);
}

/** Collapsible title outline; clicking a title filters the report to that subtree. */
export function Titelbaum({ baum, aktiv, onWaehle }: {
  baum: Titelknoten[]; aktiv: string[] | null; onWaehle: (pfad: string[] | null) => void;
}) {
  const [offen, setOffen] = useState<Set<string>>(new Set());
  const t = useT();
  if (baum.length === 0) return null;

  function umschalten(schluessel: string) {
    setOffen((alt) => {
      const neu = new Set(alt);
      if (!neu.delete(schluessel)) neu.add(schluessel);
      return neu;
    });
  }

  function zweig(knoten: Titelknoten[]) {
    return (
      <ul className={styles.zweig}>
        {knoten.map((k) => {
          const istOffen = offen.has(k.schluessel);
          const gewaehlt = gleich(aktiv, k.pfad);
          return (
            <li key={k.schluessel}>
              <div className={styles.zeile}>
                {k.kinder.length > 0 ? (
                  <button type="button" className={styles.pfeil} aria-expanded={istOffen}
                    aria-label={`${t(istOffen ? "Collapse" : "Expand")} ${k.titel}`} onClick={() => umschalten(k.schluessel)}>
                    {istOffen ? "▾" : "▸"}
                  </button>
                ) : <span className={styles.pfeil} aria-hidden="true" />}
                <button type="button" className={`${styles.knoten} ${gewaehlt ? styles.knotenAktiv : ""}`}
                  aria-pressed={gewaehlt} onClick={() => onWaehle(gewaehlt ? null : k.pfad)}>
                  <span className={k.schluessel === "" ? styles.ohneTitel : styles.name} title={k.titel}>{k.titel}</span>
                  <span className={styles.zahlen}>
                    {k.positionen} {t(k.positionen === 1 ? "item" : "items")}
                    {k.findings > 0 && k.maxSchwere && (
                      <span className={styles.befunde} title={`Highest severity: ${SCHWERE_NAME[k.maxSchwere]}`}>
                        <span className={`${styles.punkt} ${styles[`schwere_${k.maxSchwere}`]}`} aria-hidden="true" />
                        {k.findings} {t(k.findings === 1 ? "finding" : "findings")}
                        <span className={styles.sr}>, highest severity {SCHWERE_NAME[k.maxSchwere]}</span>
                      </span>
                    )}
                  </span>
                </button>
              </div>
              {istOffen && k.kinder.length > 0 && zweig(k.kinder)}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <details className={styles.titelbaum}>
      <summary className={styles.titel}>{t("Title structure")}</summary>
      {aktiv !== null && (
        <nav className={styles.brotkrumen} aria-label="Active title filter">
          <span className={styles.klein}>{t("Filtered to")}</span>
          <span className={styles.pfad} title={aktiv.join(" › ")}>{aktiv.length === 0 ? OHNE_TITEL_NAME : aktiv.join(" › ")}</span>
          <button type="button" className={styles.leeren} onClick={() => onWaehle(null)}>{t("Clear")}</button>
        </nav>
      )}
      <div className={styles.rahmen}>{zweig(baum)}</div>
    </details>
  );
}
