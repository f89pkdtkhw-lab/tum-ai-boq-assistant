"use client";

import { type ChangeEvent, useEffect, useState } from "react";
import type { Pruefbericht } from "@/lib/api";
import { PRUEFBERICHT_SPEICHER_SCHLUESSEL } from "@/components/Pruefbericht";
import { dateiname, istMock, leseBericht, xlsx } from "@/lib/export";
import styles from "./export.module.css";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });
const KATEGORIE: Record<string, string> = { fehler: "Error", risiko: "Risk", nachtrag: "Change order" };

const SEVERITY_LABELS: Record<string, string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };

type Zustand = { phase: "laedt" } | { phase: "leer"; fehler: string } | { phase: "bereit"; bericht: Pruefbericht; quelle: string };

export function Export() {
  const [zustand, setZustand] = useState<Zustand>({ phase: "laedt" });

  useEffect(() => {
    let text: string | null = null;
    try { text = window.sessionStorage.getItem(PRUEFBERICHT_SPEICHER_SCHLUESSEL); } catch { /* storage blocked */ }
    const bericht = leseBericht(text);
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: "from the current review" }
      : { phase: "leer", fehler: text ? "The stored report is invalid." : "" });
  }, []);

  async function dateiLaden(e: ChangeEvent<HTMLInputElement>) {
    const datei = e.target.files?.[0];
    if (!datei) return;
    const bericht = leseBericht(await datei.text());
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: `from ${datei.name}` }
      : { phase: "leer", fehler: `“${datei.name}” is not a review report. Please use the JSON file from “Download JSON”.` });
  }

  function excel(bericht: Pruefbericht) {
    const blob = new Blob([xlsx(bericht) as BlobPart], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: dateiname(bericht.lv.name, "xlsx") });
    a.click();
    URL.revokeObjectURL(url);
  }

  if (zustand.phase === "laedt") return <main className={styles.seite} aria-busy="true" />;

  if (zustand.phase === "leer") {
    return (
      <main className={styles.seite}>
        <section className={`${styles.glas} ${styles.leer}`} aria-labelledby="leer-titel">
          <h1 id="leer-titel">No review report to export</h1>
          {zustand.fehler && <p className={styles.fehler} role="alert">{zustand.fehler}</p>}
          <p>Start a review and select “Export report”, or load a saved report (JSON).</p>
          <div className={styles.aktionen}>
            <a className={styles.knopf} href="/">Back to review</a>
            <label className={styles.knopfZweit}>
              Load JSON report
              <input type="file" accept=".json,application/json" className={styles.versteckt} onChange={dateiLaden} />
            </label>
          </div>
        </section>
      </main>
    );
  }

  const { bericht } = zustand;
  const { lv, findings, kennzahlen } = bericht;
  const mock = kennzahlen.modell_mock || findings.some(istMock);

  return (
    <main className={styles.seite}>
      <nav className={`${styles.glas} ${styles.leiste}`} aria-label="Export">
        <a className={styles.zurueck} href="/">‹ Review</a>
        <div className={styles.aktionen}>
          <button type="button" className={styles.knopfZweit} onClick={() => window.print()}>Print as PDF</button>
          <button type="button" className={styles.knopf} onClick={() => excel(bericht)}>Download Excel</button>
        </div>
      </nav>

      <article className={styles.blatt}>
        <header className={styles.kopf}>
          <p className={styles.eyebrow}>Review report · {zustand.quelle}</p>
          <h1>{lv.name}</h1>
          <p className={styles.quelle}>Source: {lv.quelle}</p>
        </header>

        {mock && (
          <p className={styles.hinweis}>
            Demo mode: The model review ran as an offline mock. Entries marked “Demonstration” are not domain findings.
          </p>
        )}

        <dl className={styles.zahlen}>
          <div><dt>Items</dt><dd>{zahl.format(lv.positionen.length)}</dd></div>
          <div><dt>Entries</dt><dd>{zahl.format(findings.length)}</dd></div>
          <div><dt>Critical</dt><dd>{zahl.format(kennzahlen.kritisch)}</dd></div>
        </dl>

        <h2>Findings</h2>
        {findings.length === 0 ? <p className={styles.quelle}>No findings.</p> : (
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr><th>OZ</th><th>Category</th><th>Severity</th><th>Finding</th><th>Suggestion</th><th>Source</th><th>Euro impact</th></tr></thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.id}>
                    <td className={styles.oz}>{f.oz}</td>
                    <td>{KATEGORIE[f.kategorie] ?? f.kategorie}</td>
                    <td>{SEVERITY_LABELS[f.schwere] ?? f.schwere}</td>
                    <td><b>{f.titel}</b><br />{f.begruendung}{istMock(f) && <span className={styles.mock}> Demonstration</span>}</td>
                    <td>{f.vorschlag}</td>
                    <td className={styles.regel}>{f.quelle === "regel" ? "Rule" : "Model"}<br />{f.regel_id.replaceAll("_", "_\u200b")}</td>
                    <td className={styles.rechts}>{f.euro_wirkung === null ? "unknown" : euro.format(f.euro_wirkung)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h2>Items</h2>
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead><tr><th>OZ</th><th>Short description</th><th className={styles.rechts}>Quantity</th><th>Unit</th><th className={styles.rechts}>Unit price</th><th className={styles.rechts}>Total price</th></tr></thead>
            <tbody>
              {lv.positionen.map((p, i) => (
                <tr key={`${p.oz}-${i}`}>
                  <td className={styles.oz}>{p.oz}</td>
                  <td>{p.kurztext}</td>
                  <td className={styles.rechts}>{p.menge === null ? "" : zahl.format(p.menge)}</td>
                  <td>{p.einheit ?? ""}</td>
                  <td className={styles.rechts}>{p.ep === null ? "" : euro.format(p.ep)}</td>
                  <td className={styles.rechts}>{p.gp === null ? "" : euro.format(p.gp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </main>
  );
}
