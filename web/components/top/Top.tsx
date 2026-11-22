"use client";

import { useDok } from "@/components/dok/useDok";
import { useMemo, useState } from "react";
import type { Finding, Position } from "@/lib/api";
import { topPositionen } from "@/lib/top";
import styles from "./top.module.css";
import { useT } from "@/lib/einstellungen";

const SCHWERE_NAME: Record<Finding["schwere"], string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
// Page sizes; Previous/Next walk through every item with a finding in steps of the chosen size.
const GROESSEN = [10, 25, 100];
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });

/** "Look at these first": positions with findings, ranked; a click opens the existing detail. */
export function Top({ findings, positionen, onWaehle }: {
  findings: Finding[]; positionen: Position[]; onWaehle: (oz: string, findingId: string) => void;
}) {
  const d = useDok();
  const [groesse, setGroesse] = useState(10);
  const [start, setStart] = useState(0);
  const t = useT();
  const alle = useMemo(() => topPositionen(findings, positionen, Infinity), [findings, positionen]);
  const zeilen = alle.slice(start, start + groesse);
  const bis = start + zeilen.length;
  const steuerung = alle.length > groesse && (
    <div className={styles.blaettern} role="group" aria-label={t("Item pages")}>
      <button type="button" className={styles.chip} disabled={start === 0} onClick={() => setStart(Math.max(0, start - groesse))}>
        ‹ {t("Previous {n}", { n: groesse })}
      </button>
      <span className={styles.stand}>{t("{a}–{b} of {n}", { a: start + 1, b: bis, n: alle.length })}</span>
      <button type="button" className={styles.chip} disabled={bis >= alle.length} onClick={() => setStart(start + groesse)}>
        {t("Next {n}", { n: Math.min(groesse, alle.length - bis) || groesse })} ›
      </button>
    </div>
  );

  return (
    <section className={styles.top} aria-labelledby="top-titel">
      <div className={styles.kopf}>
        <h3 id="top-titel" className={styles.titel}>
          {t("Look at these first")} <span className={styles.anzahl}>{t("{a}–{b} of {n}", { a: alle.length ? start + 1 : 0, b: bis, n: alle.length })}</span>
        </h3>
        {alle.length > 0 && (
          <div className={styles.umschalter} role="group" aria-label={t("Number of items shown")}>
            <span className={styles.stand}>{t("Show")}</span>
            {GROESSEN.map((g) => (
              <button key={g} type="button" className={`${styles.chip} ${groesse === g ? styles.chipAktiv : ""}`}
                aria-pressed={groesse === g} onClick={() => { setGroesse(g); setStart(Math.floor(start / g) * g); }}>{g}</button>
            ))}
          </div>
        )}
      </div>
      <p className={styles.hinweis}>{t("Ordered by severity, then known € effect, then number of findings; no prices are estimated.")}</p>
      {alle.length === 0 ? (
        <p className={styles.hinweis}>{t("No item has a finding.")}</p>
      ) : (
        <>
        {steuerung}
        <ol className={styles.liste} start={start + 1}>
          {zeilen.map((z, i) => (
            <li key={z.oz}>
              <button type="button" className={`${styles.zeile} ${z.nurModell ? styles.mock : ""}`}
                onClick={() => onWaehle(z.oz, z.findingId)} aria-label={t("Show item {oz}", { oz: z.oz })}
                style={{ "--sev": `var(--sev-${z.schwere})` } as React.CSSProperties}>
                <span className={styles.rang}>{start + i + 1}</span>
                <span className={styles.oz}>{z.oz}</span>
                <span className={styles.text}>{d(z.kurztext) || <em className={styles.unbekannt}>{t(z.kurztext === null ? "not in BoQ" : "short text unknown")}</em>}</span>
                <span className={styles.merkmale}>
                  <span className={`${styles.marke} ${styles.schwere}`}>{t(SCHWERE_NAME[z.schwere])}</span>
                  <span className={styles.marke}>{z.anzahl} {t(z.anzahl === 1 ? "finding" : "findings")}</span>
                  <span className={styles.euro}>{z.euro === null ? <em className={styles.unbekannt}>{t("unknown")}</em> : euro.format(z.euro)}</span>
                  {z.nurModell && <span className={styles.markeMock}>{t("AI only")}</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
        {zeilen.length > 15 && steuerung}
        </>
      )}
    </section>
  );
}
