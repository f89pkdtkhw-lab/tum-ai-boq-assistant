"use client";

import { useMemo } from "react";
import type { Position } from "@/lib/api";
import { mengenSummen } from "@/lib/mengen";
import styles from "./mengen.module.css";
import { useT } from "@/lib/einstellungen";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });

/** Quantity totals per unit (tiles, clickable as filter) and per top-level title. */
export function Mengen({ positionen, aktiv, onWaehle }: {
  positionen: Position[]; aktiv: string | null; onWaehle: (schluessel: string | null) => void;
}) {
  const mengen = useMemo(() => mengenSummen(positionen), [positionen]);
  const { einheiten, titel, ausserVertrag, ohneMenge } = mengen;
  const t = useT();

  return (
    <section className={styles.mengen} aria-labelledby="mengen-titel">
      <h3 id="mengen-titel" className={styles.titel}>{t("Quantity totals per unit")}</h3>
      {einheiten.length === 0 ? (
        <p className={styles.leer}>{t("No item has both a quantity and a unit, so nothing can be summed.")}</p>
      ) : (
        <ul className={styles.kacheln}>
          {einheiten.map((e) => (
            <li key={e.schluessel}>
              <button type="button" className={`${styles.kachel} ${aktiv === e.schluessel ? styles.kachelAktiv : ""}`}
                aria-pressed={aktiv === e.schluessel}
                onClick={() => onWaehle(aktiv === e.schluessel ? null : e.schluessel)}>
                <span className={styles.wert}>{zahl.format(e.summe)} <span className={styles.einheit}>{e.einheit}</span></span>
                <span className={styles.klein}>{e.positionen} {t(e.positionen === 1 ? "item" : "items")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className={styles.hinweis}>
        {t("Contract quantities only; units are never converted.")}
        {ausserVertrag > 0 && <> {t("{n} optional/alternative items not in contract quantity.", { n: ausserVertrag })}</>}
        {ohneMenge > 0 && <> {t("{n} items without quantity/unit.", { n: ohneMenge })}</>}
        {einheiten.length > 0 && <> {t("Click a unit to filter the item table.")}</>}
      </p>

      {titel.length > 0 && (
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <caption className={styles.titel}>{t("Per top-level title")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("Title")}</th>
                {einheiten.map((e) => <th key={e.schluessel} scope="col" className={styles.rechts}>{e.einheit}</th>)}
              </tr>
            </thead>
            <tbody>
              {titel.map((t) => (
                <tr key={t.titel}>
                  <th scope="row">{t.titel}</th>
                  {einheiten.map((e) => (
                    <td key={e.schluessel} className={styles.rechts}>
                      {t.summen[e.schluessel] === undefined ? <span className={styles.klein}>–</span> : zahl.format(t.summen[e.schluessel])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
