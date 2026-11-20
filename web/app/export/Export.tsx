"use client";

import { type ChangeEvent, useEffect, useState } from "react";
import type { Pruefbericht } from "@/lib/api";
import { PRUEFBERICHT_SPEICHER_SCHLUESSEL } from "@/components/Pruefbericht";
import { dateiname, istMock, leseBericht, xlsx } from "@/lib/export";
import styles from "./export.module.css";

const zahl = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3 });
const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const KATEGORIE: Record<string, string> = { fehler: "Fehler", risiko: "Risiko", nachtrag: "Nachtrag" };

type Zustand = { phase: "laedt" } | { phase: "leer"; fehler: string } | { phase: "bereit"; bericht: Pruefbericht; quelle: string };

export function Export() {
  const [zustand, setZustand] = useState<Zustand>({ phase: "laedt" });

  useEffect(() => {
    let text: string | null = null;
    try { text = window.sessionStorage.getItem(PRUEFBERICHT_SPEICHER_SCHLUESSEL); } catch { /* storage blocked */ }
    const bericht = leseBericht(text);
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: "aus der aktuellen Prüfung" }
      : { phase: "leer", fehler: text ? "Der gespeicherte Bericht ist ungültig." : "" });
  }, []);

  async function dateiLaden(e: ChangeEvent<HTMLInputElement>) {
    const datei = e.target.files?.[0];
    if (!datei) return;
    const bericht = leseBericht(await datei.text());
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: `aus ${datei.name}` }
      : { phase: "leer", fehler: `„${datei.name}“ ist kein Prüfbericht. Bitte die JSON-Datei aus „JSON herunterladen“ verwenden.` });
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
          <h1 id="leer-titel">Kein Prüfbericht zum Exportieren</h1>
          {zustand.fehler && <p className={styles.fehler} role="alert">{zustand.fehler}</p>}
          <p>Starte eine Prüfung und wähle dort „Zum Export“, oder lade einen gespeicherten Bericht (JSON).</p>
          <div className={styles.aktionen}>
            <a className={styles.knopf} href="/">Zur Prüfung</a>
            <label className={styles.knopfZweit}>
              JSON-Bericht laden
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
        <a className={styles.zurueck} href="/">‹ Prüfung</a>
        <div className={styles.aktionen}>
          <button type="button" className={styles.knopfZweit} onClick={() => window.print()}>Als PDF drucken</button>
          <button type="button" className={styles.knopf} onClick={() => excel(bericht)}>Excel herunterladen</button>
        </div>
      </nav>

      <article className={styles.blatt}>
        <header className={styles.kopf}>
          <p className={styles.eyebrow}>Prüfbericht · {zustand.quelle}</p>
          <h1>{lv.name}</h1>
          <p className={styles.quelle}>Quelle: {lv.quelle}</p>
        </header>

        {mock && (
          <p className={styles.hinweis}>
            Demonstrationsmodus: Die Modellprüfung lief als Offline-Mock. Mit „Demonstration“ markierte Einträge sind keine fachlichen Befunde.
          </p>
        )}

        <dl className={styles.zahlen}>
          <div><dt>Positionen</dt><dd>{zahl.format(lv.positionen.length)}</dd></div>
          <div><dt>Einträge</dt><dd>{zahl.format(findings.length)}</dd></div>
          <div><dt>Kritisch</dt><dd>{zahl.format(kennzahlen.kritisch)}</dd></div>
        </dl>

        <h2>Befunde</h2>
        {findings.length === 0 ? <p className={styles.quelle}>Keine Befunde.</p> : (
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr><th>OZ</th><th>Kategorie</th><th>Schwere</th><th>Befund</th><th>Vorschlag</th><th>Quelle</th><th>Euro-Wirkung</th></tr></thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.id}>
                    <td className={styles.oz}>{f.oz}</td>
                    <td>{KATEGORIE[f.kategorie] ?? f.kategorie}</td>
                    <td>{f.schwere}</td>
                    <td><b>{f.titel}</b><br />{f.begruendung}{istMock(f) && <span className={styles.mock}> Demonstration</span>}</td>
                    <td>{f.vorschlag}</td>
                    <td className={styles.regel}>{f.quelle === "regel" ? "Regel" : "Modell"}<br />{f.regel_id.replaceAll("_", "_\u200b")}</td>
                    <td className={styles.rechts}>{f.euro_wirkung === null ? "unbekannt" : euro.format(f.euro_wirkung)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h2>Positionen</h2>
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead><tr><th>OZ</th><th>Kurztext</th><th className={styles.rechts}>Menge</th><th>Einheit</th><th className={styles.rechts}>EP</th><th className={styles.rechts}>GP</th></tr></thead>
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
