"use client";

import { useDok } from "@/components/dok/useDok";
import { useMemo, useState } from "react";
import type { Finding, Position } from "@/lib/api";
import { alsText, bieterfragen } from "@/lib/bieterfragen";
import styles from "./bieterfragen.module.css";
import { useT } from "@/lib/einstellungen";

const SCHWERE_NAME: Record<Finding["schwere"], string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
const KATEGORIE_NAME: Record<Finding["kategorie"], string> = { fehler: "Error", risiko: "Risk", nachtrag: "Change order" };

/** Risk and change-order findings phrased as questions to send before bidding. */
export function Bieterfragen({ findings, positionen }: { findings: Finding[]; positionen: Position[] }) {
  const d = useDok();
  const fragen = useMemo(() => bieterfragen(findings, positionen), [findings, positionen]);
  const [meldung, setMeldung] = useState("");
  const t = useT();

  async function kopieren() {
    try {
      await navigator.clipboard.writeText(alsText(fragen));
      setMeldung(t("Copied {n} questions.", { n: fragen.length }));
    } catch {
      setMeldung(t("Could not copy to the clipboard (browser blocked it). Please select the list and copy it manually."));
    }
  }

  return (
    <section className={styles.fragen} aria-labelledby="bieterfragen-titel">
      <div className={styles.kopf}>
        <h3 id="bieterfragen-titel" className={styles.titel}>{t("Bidder questions")} <span className={styles.anzahl}>{fragen.length}</span></h3>
        {fragen.length > 0 && <button type="button" className={styles.knopf} onClick={kopieren}>{t("Copy all")}</button>}
      </div>
      {meldung && <p className={styles.hinweis} role="status">{meldung}</p>}
      {fragen.length === 0 ? (
        <p className={styles.hinweis}>{t("No risk or change-order findings, so there are no questions to ask the client.")}</p>
      ) : (
        <ol className={styles.liste}>
          {fragen.map((f) => (
            <li key={f.id} className={styles.eintrag}>
              <p className={styles.merkmale}>
                <span className={styles.oz}>OZ {f.oz}</span>
                <span>{f.kurztext ? d(f.kurztext) : <em>{t("short text unknown")}</em>}</span>
                <span className={styles.marke}>{t(SCHWERE_NAME[f.schwere])} · {t(KATEGORIE_NAME[f.kategorie])}</span>
              </p>
              <p className={styles.finding}>{f.titel}</p>
              <p className={styles.frage}>{f.frage}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
