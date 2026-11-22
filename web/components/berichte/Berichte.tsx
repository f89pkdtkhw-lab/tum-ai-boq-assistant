"use client";

import { useState } from "react";
import type { Finding, Pruefbericht } from "@/lib/api";
import { abschnitte, chanceName, hatBerichte, prozentText, TABS, wasWennListe, type Abschnitt, type TabId } from "@/lib/berichte";
import { schlussZeilen } from "@/lib/schlussbericht";
import { useT } from "@/lib/einstellungen";
import { istAnnahme } from "@/lib/normen"; // #83: assumption marker
import styles from "./berichte.module.css";

const SCHWERE: Record<Finding["schwere"], string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });

/**
 * Report 1–3 and the final report as tabs (issue #104). Findings open the existing detail panel via `onWaehle`.
 * Renders nothing without `berichte`, so older backends keep today's view.
 */
export function Berichte({ bericht, onWaehle }: { bericht: Pruefbericht; onWaehle: (oz: string, findingId: string | null) => void }) {
  const [tab, setTab] = useState<TabId>("regelwerk");
  if (!hatBerichte(bericht)) return null;
  const liste = abschnitte(bericht);
  const wasWenn = wasWennListe(bericht);
  const aktiv = liste.find((a) => a.bericht.id === tab);

  return (
    <section className={styles.berichte} aria-labelledby="berichte-titel">
      <h3 id="berichte-titel" className={styles.titel}>Reports</h3>
      <div className={styles.tabs} role="tablist" aria-label="Reports">
        {TABS.map((t) => {
          const a = liste.find((x) => x.bericht.id === t.id);
          return (
            <button key={t.id} id={`bericht-tab-${t.id}`} type="button" role="tab" aria-selected={tab === t.id}
              aria-controls="bericht-panel" className={`${styles.tab} ${tab === t.id ? styles.tabAktiv : ""}`} onClick={() => setTab(t.id)}>
              {t.name}
              {a && a.bericht.status !== "ok" && <span className={styles.status}>{a.bericht.status === "nicht_verbunden" ? "not connected" : "failed"}</span>}
            </button>
          );
        })}
      </div>
      <div id="bericht-panel" role="tabpanel" aria-labelledby={`bericht-tab-${tab}`} className={styles.panel}>
        {tab === "endbericht" ? (
          <Endbericht bericht={bericht} liste={liste} wasWenn={wasWenn} onWaehle={onWaehle} />
        ) : aktiv ? (
          <BerichtInhalt a={aktiv} onWaehle={onWaehle} />
        ) : (
          <p className={styles.leer}>The backend sent no data for this report.</p>
        )}
      </div>
    </section>
  );
}

function FindingListe({ findings, fehlend, onWaehle }: { findings: Finding[]; fehlend: string[]; onWaehle: (oz: string, id: string) => void }) {
  if (findings.length === 0 && fehlend.length === 0) return null;
  return (
    <ul className={styles.liste}>
      {findings.map((f) => (
        <li key={f.id}>
          <button type="button" className={styles.zeile} onClick={() => onWaehle(f.oz, f.id)}>
            <span className={styles.marke}>{SCHWERE[f.schwere]}</span>
            <span className={styles.text}>{f.titel}</span>
            <span className={styles.oz}>OZ {f.oz}</span>
          </button>
        </li>
      ))}
      {fehlend.map((id) => <li key={id} className={styles.leer}>Finding {id} is named by the report but missing from the response.</li>)}
    </ul>
  );
}

function WasWennListe({ liste }: { liste: ReturnType<typeof wasWennListe> }) {
  if (liste.length === 0) return null;
  return (
    <>
      <p className={styles.hinweis}>No penalty, for awareness: problems seen in past projects and their chance here.</p>
      <ul className={styles.liste}>
        {liste.map((w, i) => (
          <li key={i} className={styles.karte}>
            <span className={`${styles.marke} ${w.chance === "hoch" ? styles.hoch : ""}`}>{chanceName(w.chance)}</span>
            {w.oz && <span className={styles.oz}>OZ {w.oz}</span>}
            <p className={styles.text}><strong>{w.problem}</strong></p>
            {w.empfehlung && <p className={styles.text}>Recommendation: {w.empfehlung}</p>}
            {w.begruendung && <p className={styles.hinweis}>{w.begruendung}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}

function BerichtInhalt({ a, onWaehle }: { a: Abschnitt; onWaehle: (oz: string, id: string | null) => void }) {
  const t = useT();
  const b = a.bericht;
  if (b.status !== "ok") return <p className={styles.leer} role="note">{a.leer}</p>;
  return (
    <div className={styles.inhalt}>
      {b.meldung && <p className={styles.hinweis}>{b.meldung}</p>}
      {a.leer && <p className={styles.leer}>{a.leer}</p>}
      <FindingListe findings={a.findings} fehlend={a.fehlend} onWaehle={onWaehle} />
      {b.id === "vergleich" && (b.tags?.length ?? 0) > 0 && <p className={styles.hinweis}>Comparable tags: {b.tags!.join(", ")}</p>}
      {b.neue_tags.length > 0 && (
        <p className={styles.hinweis}>No comparable tag found. Proposed new tags: {b.neue_tags.map((t) => <span key={t} className={styles.marke}>{t}</span>)}</p>
      )}
      {(b.naeherungen?.length ?? 0) > 0 && (
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead><tr><th scope="col">OZ</th><th scope="col">Short description</th><th scope="col" className={styles.rechts}>Quantity</th>
              <th scope="col" className={styles.rechts}>Estimated</th><th scope="col" className={styles.rechts}>±</th><th scope="col">Why</th></tr></thead>
            <tbody>
              {b.naeherungen!.map((n) => (
                <tr key={n.note_id || n.oz} className={n.zu_gross ? styles.zuGross : undefined}>
                  <td><button type="button" className={styles.link} onClick={() => onWaehle(n.oz, null)}>{n.oz}</button></td>
                  <td>{n.kurztext}{n.zu_gross && <span className={`${styles.marke} ${styles.hoch}`}>approximation too big</span>}</td>
                  <td className={styles.rechts}>{zahl.format(n.menge)} {n.einheit}</td>
                  <td className={styles.rechts}>{zahl.format(n.geschaetzt)} {n.einheit}</td>
                  <td className={styles.rechts}>{prozentText(n.abweichung_prozent)}{n.abweichung_eur !== null && <> · {euro.format(n.abweichung_eur)}</>}</td>
                  <td>{n.warum}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {b.id !== "was_wenn" && (b.probleme?.length ?? 0) > 0 && (
        <><p className={styles.hinweis}>Problems noted in similar projects:</p><WasWennListe liste={b.probleme!} /></>
      )}
      {b.id === "was_wenn" && <WasWennListe liste={wasWennListe({ berichte: [b] })} />}
      {b.notes.length > 0 && b.id !== "vergleich" && (
        <ul className={styles.liste}>
          {b.notes.map((n, i) => <li key={n.id ?? i} className={styles.karte}>{istAnnahme(n) && <span className={`${styles.marke} ${styles.hoch}`}>{t("Assumption")} · {t("Approval required")}</span>} {n.oz && <span className={styles.oz}>OZ {n.oz}</span>} {n.text}</li>)}
        </ul>
      )}
    </div>
  );
}

function Endbericht({ bericht, liste, wasWenn, onWaehle }: {
  bericht: Pruefbericht; liste: Abschnitt[]; wasWenn: ReturnType<typeof wasWennListe>; onWaehle: (oz: string, id: string | null) => void;
}) {
  const z = bericht.zusammenfassung;
  return (
    <div className={styles.inhalt}>
      <p className={styles.endScore}>Score {z ? `${z.score.toFixed(1)} / 10` : "–"}</p>
      {z && z.score_abzuege.length > 0 && (
        <ul className={styles.abzuege}>{z.score_abzuege.map((s, i) => <li key={i}>{s.punkte.toFixed(1).replace("-", "−")} · {s.grund}</li>)}</ul>
      )}
      <ul className={styles.liste}>
        {liste.map((a) => (
          <li key={a.bericht.id} className={styles.karte}>
            <strong>{a.bericht.titel}</strong>{" "}
            {a.bericht.status === "ok"
              ? `${a.findings.length} findings${a.bericht.zaehler ? ` · ${a.bericht.zaehler.grosse_probleme} big problems · ${a.bericht.zaehler.warnungen} warnings` : ""}`
              : <span className={styles.leer}>{a.leer}</span>}
          </li>
        ))}
      </ul>
      <h4 className={styles.unter}>What-if list</h4>
      {wasWenn.length === 0 ? <p className={styles.leer}>No what-if items.</p> : <WasWennListe liste={wasWenn} />}
      <Schlussbericht bericht={bericht} onWaehle={onWaehle} />
    </div>
  );
}

const SEITE = 100;

/** Final report (#167): one row per bill item with problems, ± approximation, need to add and recommendations. */
function Schlussbericht({ bericht, onWaehle }: { bericht: Pruefbericht; onWaehle: (oz: string, id: string | null) => void }) {
  const [alle, setAlle] = useState(false);
  const [anzahl, setAnzahl] = useState(SEITE);
  const s = bericht.schlussbericht;
  if (!s) return null;
  const zeilen = schlussZeilen(bericht, alle);
  const fehlgeschlagen = bericht.kennzahlen.modell_batches_fehlgeschlagen ?? 0;
  return (
    <>
      <h4 className={styles.unter}>Final report</h4>
      <p className={styles.hinweis}>{s.projektbeschreibung}</p>
      {fehlgeschlagen > 0 && (
        <p className={styles.hinweis} role="note">
          <span className={`${styles.marke} ${styles.hoch}`}>model</span>
          {fehlgeschlagen} of {bericht.kennzahlen.modell_batches} model batches failed; their items were checked by the rules only.
        </p>
      )}
      {s.warnungen.length > 0 && <ul className={styles.abzuege}>{s.warnungen.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      {s.allgemein.length > 0 && (
        <p className={styles.hinweis}>General: {s.allgemein.map((p) => <span key={p.finding_id} className={styles.marke}>{p.titel}</span>)}</p>
      )}
      <div className={styles.werkzeug}>
        <span className={styles.hinweis}>{zeilen.length} of {s.positionen.length} items{alle ? "" : " with something to note"}</span>
        <button type="button" className={styles.tab} aria-pressed={alle} onClick={() => { setAlle(!alle); setAnzahl(SEITE); }}>
          {alle ? "Only items with notes" : "Show all items"}
        </button>
      </div>
      {zeilen.length === 0 ? <p className={styles.leer}>No item needs attention.</p> : (
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead><tr><th scope="col">OZ</th><th scope="col">Short description</th><th scope="col" className={styles.rechts}>Quantity</th>
              <th scope="col" className={styles.rechts}>Estimated · ±</th><th scope="col">Need to add</th><th scope="col">Problems</th>
              <th scope="col">Warnings · recommendations</th></tr></thead>
            <tbody>
              {zeilen.slice(0, anzahl).map((z, i) => (
                <tr key={`${z.oz}-${i}`} className={z.warnungen.length > 0 ? styles.zuGross : undefined}>
                  <td><button type="button" className={styles.link} onClick={() => onWaehle(z.oz, null)}>{z.oz}</button></td>
                  <td>{z.kurztext}</td>
                  <td className={styles.rechts}>{z.menge === null ? "–" : `${zahl.format(z.menge)} ${z.einheit ?? ""}`}</td>
                  <td className={styles.rechts} title={z.warum || undefined}>
                    {z.geschaetzt === null ? "–" : <>{zahl.format(z.geschaetzt)} · {z.abweichung !== null && z.abweichung > 0 ? "+" : ""}{zahl.format(z.abweichung ?? 0)}</>}
                    {z.abweichung_eur !== null && <> · {euro.format(z.abweichung_eur)}</>}
                  </td>
                  <td>{z.nachtrag.length > 0 && <ul className={styles.zellListe}>{z.nachtrag.map((n, j) => <li key={j}>{n}</li>)}</ul>}</td>
                  <td>
                    {z.probleme.length > 0 && (
                      <ul className={styles.zellListe}>
                        {z.probleme.map((p) => (
                          <li key={p.finding_id}>
                            <button type="button" className={styles.zellKnopf} onClick={() => onWaehle(z.oz, p.finding_id)}>
                              <span className={`${styles.marke} ${p.schwere === "kritisch" || p.schwere === "hoch" ? styles.hoch : ""}`}>{SCHWERE[p.schwere]}</span>
                              {p.titel} <span className={styles.oz}>{p.quelle === "modell" ? "model" : "rule"}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    {(z.warnungen.length > 0 || z.empfehlungen.length > 0) && (
                      <ul className={styles.zellListe}>
                        {z.warnungen.map((w, j) => <li key={`w${j}`}>{w}</li>)}
                        {z.empfehlungen.map((e, j) => <li key={`e${j}`}>{e}</li>)}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {zeilen.length > anzahl && (
        <button type="button" className={styles.tab} onClick={() => setAnzahl(anzahl + SEITE)}>Show {Math.min(SEITE, zeilen.length - anzahl)} more</button>
      )}
    </>
  );
}
