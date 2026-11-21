"use client";

import { useDok } from "@/components/dok/useDok";
import { Fragment, useEffect, useMemo, useState } from "react";
import type { Position } from "@/lib/api";
import { historyApi, type HistoryCase } from "@/lib/history-api";
import { MIN_GRUPPE, preisspiegel, type PreisGruppe, type Stufe } from "@/lib/preise";
import { useT } from "@/lib/einstellungen";
import { Ring } from "../ring/Ring";
import { Info } from "../info/Info";
import styles from "./preisspiegel.module.css";

const FARBE: Record<Stufe, string> = { gruen: "var(--sev-ok)", gelb: "var(--sev-mittel)", rot: "var(--sev-kritisch)" };
const TEXT: Record<Stufe, string> = { ...FARBE, gelb: "var(--sev-mittel-text)" };
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const prozent = (x: number) => `${x > 0 ? "+" : ""}${Math.round(x * 100)} %`;

/** Min–max line, IQR box, median tick, coloured outlier dots and the past-project median (◆), on a log scale. */
function Streifen({ g }: { g: PreisGruppe }) {
  const werte = [g.min, g.max, ...(g.historie ? [g.historie.median] : [])];
  const lo = Math.log(Math.min(...werte) * .9), hi = Math.log(Math.max(...werte) * 1.1);
  const x = (v: number) => `${((Math.log(v) - lo) / (hi - lo || 1)) * 100}%`;
  return (
    <span className={styles.streifen} aria-hidden="true">
      <span className={styles.linie} style={{ left: x(g.min), right: `calc(100% - ${x(g.max)})` }} />
      <span className={styles.box} style={{ left: x(g.q1), width: `calc(${x(g.q3)} - ${x(g.q1)})` }} />
      <span className={styles.median} style={{ left: x(g.median) }} />
      {g.positionen.filter((p) => p.stufe !== "gruen").map((p) => (
        <span key={p.oz} className={styles.punkt} style={{ left: x(p.ep), background: FARBE[p.stufe] }} />
      ))}
      {g.historie && <span className={styles.raute} style={{ left: x(g.historie.median) }} />}
    </span>
  );
}

/** Price comparison tab: is every unit price in line with the same work in this BoQ and in past projects? */
export function Preisspiegel({ positionen, onWaehle }: { positionen: Position[]; onWaehle: (oz: string) => void }) {
  const d = useDok();
  const t = useT();
  const [faelle, setFaelle] = useState<HistoryCase[] | null>(null);
  const [nurAuffaellig, setNurAuffaellig] = useState(true);
  const [offen, setOffen] = useState<string | null>(null);
  useEffect(() => { historyApi.list(null, 100).then(setFaelle).catch(() => setFaelle([])); }, []);
  const s = useMemo(() => preisspiegel(positionen, faelle), [positionen, faelle]);
  const auffaellig = s.zaehler.gelb + s.zaehler.rot;
  const gezeigt = nurAuffaellig ? s.gruppen.filter((g) => g.auffaellig > 0 || (g.historie && g.historie.stufe !== "gruen")) : s.gruppen;

  return (
    <section className={styles.preise} aria-labelledby="preise-titel">
      <div className={styles.kopf}>
        <Ring teile={(["rot", "gelb", "gruen"] as Stufe[]).map((k) => ({ wert: s.zaehler[k], farbe: FARBE[k] }))}
          mitte={String(auffaellig)} unter={t("unusual")} farbe={auffaellig ? TEXT[s.zaehler.rot ? "rot" : "gelb"] : TEXT.gruen} beschriftung={t("Unit price check")} />
        <div className={styles.zusammenfassung}>
          <h3 id="preise-titel" className={styles.titel}>{t("Unit price check")} <Info text={`${t("Same short text and unit are compared. Unusual means outside 1.5 × the middle spread (IQR) and 20 % off the median; outlier means outside 3 ×. ◆ marks the median unit price of past projects of the same trade.")}${s.zuWenig || s.ohnePreis ? " " + t("{a} items have fewer than {m} comparable prices, {b} have no unit price.", { a: s.zuWenig, m: MIN_GRUPPE, b: s.ohnePreis }) : ""}`} /></h3>
          <p className={styles.satz}>
            {auffaellig === 0
              ? t("All compared unit prices are in line with the same work in this BoQ.")
              : t("{n} unit prices differ strongly from the same work elsewhere in this BoQ. Check them before pricing.", { n: auffaellig })}
          </p>
          <ul className={styles.legende}>
            <li><span style={{ background: FARBE.rot }} />{t("Outlier")} <strong>{s.zaehler.rot}</strong></li>
            <li><span style={{ background: FARBE.gelb }} />{t("Unusual")} <strong>{s.zaehler.gelb}</strong></li>
            <li><span style={{ background: FARBE.gruen }} />{t("In line")} <strong>{s.zaehler.gruen}</strong></li>
          </ul>
        </div>
      </div>

      <label className={styles.schalter}>
        <input type="checkbox" checked={nurAuffaellig} onChange={(e) => setNurAuffaellig(e.target.checked)} />
        {t("Only work with unusual prices")} ({gezeigt.length} / {s.gruppen.length})
      </label>

      {gezeigt.length === 0 ? <p className={styles.hinweis}>{t("Nothing unusual to show.")}</p> : (
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead>
              <tr>
                <th>{t("Work")}</th><th className={styles.rechts}>{t("Items")}</th><th className={styles.spalteStreifen}>{t("Unit price range")}</th>
                <th className={styles.rechts}>{t("Median")}</th><th className={styles.rechts}>{t("vs. past projects")}</th><th className={styles.rechts}>{t("Unusual")}</th>
              </tr>
            </thead>
            <tbody>
              {gezeigt.map((g) => (
                <Fragment key={g.schluessel}>
                  <tr className={styles.zeile} onClick={() => setOffen(offen === g.schluessel ? null : g.schluessel)} aria-expanded={offen === g.schluessel}>
                    <td><button type="button" className={styles.aufklapp}>{offen === g.schluessel ? "▾" : "▸"}</button> {d(g.kurztext)} <span className={styles.einheit}>{g.einheit}</span></td>
                    <td className={styles.rechts}>{g.positionen.length}</td>
                    <td className={styles.spalteStreifen}><Streifen g={g} /></td>
                    <td className={styles.rechts}>{euro.format(g.median)}</td>
                    <td className={styles.rechts} style={g.historie ? { color: TEXT[g.historie.stufe], fontWeight: 600 } : undefined}
                      title={g.historie ? t("Median of {n} past projects: {p}", { n: g.historie.projekte, p: euro.format(g.historie.median) }) : undefined}>
                      {g.historie ? prozent(g.historie.abweichung) : "–"}
                    </td>
                    <td className={styles.rechts}>{g.auffaellig > 0 ? <strong style={{ color: TEXT[g.positionen.some((p) => p.stufe === "rot") ? "rot" : "gelb"] }}>{g.auffaellig}</strong> : "0"}</td>
                  </tr>
                  {offen === g.schluessel && (
                    <tr className={styles.unter}>
                      <td colSpan={6}>
                        <ul className={styles.liste}>
                          {g.positionen.filter((p) => p.stufe !== "gruen" || g.auffaellig === 0).slice(0, 20).map((p) => (
                            <li key={p.oz}>
                              <span className={styles.ampel} style={{ background: FARBE[p.stufe] }} />
                              <button type="button" className={styles.oz} onClick={() => onWaehle(p.oz)}>OZ {p.oz}</button>
                              <span>{euro.format(p.ep)} / {g.einheit}</span>
                              <span style={{ color: TEXT[p.stufe], fontWeight: 600 }}>{prozent(p.abweichung)} {t("vs. median")}</span>
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
