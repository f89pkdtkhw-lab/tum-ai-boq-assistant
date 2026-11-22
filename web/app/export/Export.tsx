"use client";

import { useDok } from "@/components/dok/useDok";
import { type ChangeEvent, useEffect, useState } from "react";
import { ladeMargeStand } from "@/lib/wizard";
import wStyles from "@/components/wizard/wizard.module.css";
import type { Pruefbericht } from "@/lib/api";
import { PRUEFBERICHT_SPEICHER_SCHLUESSEL } from "@/components/Pruefbericht";
import { dateiname, istMock, leseBericht, tabellen, xlsx, type Tabelle } from "@/lib/export";
import { bewertungVon, ladeBewertungen, statusName, type Bewertungen } from "@/lib/bewertung";
import styles from "./export.module.css";
import { useEinstellungen, useT } from "@/lib/einstellungen";
import { befundAnzeige } from "@/lib/befundtext";
import { berichtPdf } from "@/lib/berichtpdf";
import { Icon } from "@/components/icon/Icon";
import { deviationByTrade, historyApi, type TradeStat } from "@/lib/history-api";
import { ladePreisliste, type Preis } from "@/lib/preisliste";
import { preisbericht, QUELLE_NAME, type Preisbericht } from "@/lib/preisbericht";
import { berichtMitAnpassungen, evalIdFuerPreise, ladePreisAnpassungen } from "@/lib/preis-anpassung";
import { GAEB_PHASEN, gaebXml, type GaebPhase } from "@/lib/gaeb";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });
const KATEGORIE: Record<string, string> = { fehler: "Error", risiko: "Risk", nachtrag: "Change order" };

const SEVERITY_LABELS: Record<string, string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };

/** Renders an export sheet (header row + rows) so print and XLSX show the same columns. */
function Blatt({ zeilen, leer, stile = [] }: { zeilen: (string | number | null)[][]; leer: string; stile?: Tabelle["stile"] }) {
  const [kopf, ...rest] = zeilen;
  if (rest.length === 0) return <p className={styles.quelle}>{leer}</p>;
  const zahlen = kopf.map((_, c) => rest.some((z) => typeof z[c] === "number"));
  return (
    <div className={styles.rahmen}>
      <table className={styles.tabelle}>
        <thead><tr>{kopf.map((k, c) => <th key={c} className={zahlen[c] ? styles.rechts : undefined}>{k}</th>)}</tr></thead>
        <tbody>
          {rest.map((z, r) => (
            <tr key={r} className={stile[r + 1] ? styles[`zeile_${stile[r + 1]}`] : undefined}>{z.map((w, c) => <td key={c} className={zahlen[c] ? styles.rechts : c === 0 && kopf[0] === "OZ" ? styles.oz : undefined}>{typeof w === "number" ? zahl.format(w) : w}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Zustand = { phase: "laedt" } | { phase: "leer"; fehler: string } | { phase: "bereit"; bericht: Pruefbericht; quelle: string; bewertungen: Bewertungen };

export function Export() {
  const d = useDok();
  const t = useT();
  const sprache = useEinstellungen().e.sprache;
  const [zustand, setZustand] = useState<Zustand>({ phase: "laedt" });
  const [phase, setPhase] = useState<GaebPhase>("84");
  // Inputs of the estimated price report: past projects per trade and the browser price list (same as the report, level 3).
  const [gewerke, setGewerke] = useState<TradeStat[] | null>(null);
  const [preisliste, setPreisliste] = useState<Preis[]>([]);
  const [marge, setMarge] = useState<ReturnType<typeof ladeMargeStand>>(null);
  useEffect(() => {
    setPreisliste(ladePreisliste());
    setMarge(ladeMargeStand());
    historyApi.list(null, 100).then((c) => setGewerke(deviationByTrade(c))).catch(() => setGewerke([]));
  }, []);

  useEffect(() => {
    let text: string | null = null;
    try {
      text = window.sessionStorage.getItem(PRUEFBERICHT_SPEICHER_SCHLUESSEL);
      // Opened from the menu: fall back to the report that is open on "New evaluation" (LvUpload, lv-aktuell-v1).
      if (!text) { const offen = JSON.parse(window.sessionStorage.getItem("lv-aktuell-v1") ?? "null"); if (offen?.bericht) text = JSON.stringify(offen.bericht); }
    } catch { /* storage blocked or unreadable */ }
    const bericht = leseBericht(text);
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: "from the current review", bewertungen: ladeBewertungen(bericht.lv.name, bericht.findings) }
      : { phase: "leer", fehler: text ? "The stored report is invalid." : "" });
  }, []);

  async function dateiLaden(e: ChangeEvent<HTMLInputElement>) {
    const datei = e.target.files?.[0];
    if (!datei) return;
    const bericht = leseBericht(await datei.text());
    setZustand(bericht
      ? { phase: "bereit", bericht, quelle: `from ${datei.name}`, bewertungen: ladeBewertungen(bericht.lv.name, bericht.findings) }
      : { phase: "leer", fehler: `“${datei.name}” is not a review report. Please use the JSON file from “Download JSON”.` });
  }

  function gaeb(b: Pruefbericht, dp: GaebPhase, preis?: Preisbericht) {
    const xml = gaebXml(b.lv, dp, { preis, name: preis ? `${b.lv.name} – ${t("Final estimated price")}` : b.lv.name });
    const url = URL.createObjectURL(new Blob([xml], { type: "application/xml" }));
    const name = dateiname(b.lv.name, `x${dp}`).replace("pruefbericht-", preis ? "lv-geschaetzt-" : "lv-");
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    a.click(); URL.revokeObjectURL(url);
  }
  function excel(bericht: Pruefbericht, bewertungen: Bewertungen, preis?: Preisbericht) {
    const blob = new Blob([xlsx(bericht, bewertungen, preis) as BlobPart], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
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
          <h1 id="leer-titel">{t("No review report to export")}</h1>
          {zustand.fehler && <p className={styles.fehler} role="alert">{zustand.fehler}</p>}
          <p>Start a review and select “Export report”, or load a saved report (JSON).</p>
          <div className={styles.aktionen}>
            <a className={styles.knopf} href="/">{t("Back to review")}</a>
            <label className={styles.knopfZweit}>
              {t("Load JSON report")}
              <input type="file" accept=".json,application/json" className={styles.versteckt} onChange={dateiLaden} />
            </label>
          </div>
        </section>
      </main>
    );
  }

  const { bericht, bewertungen } = zustand;
  function pdfSpeichern(b: Pruefbericht, bw: Bewertungen, preis: Preisbericht) {
    const bytes = berichtPdf(b, { t, sprache, preis, status: (f) => { const s = bewertungVon(bw, f.id).status; return s === "offen" ? "" : t(statusName(s)); } });
    const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = dateiname(b.lv.name, "pdf");
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  const { lv, kennzahlen } = bericht;
  const anpassungen = ladePreisAnpassungen(evalIdFuerPreise());
  const berichtExport = berichtMitAnpassungen(bericht, anpassungen);
  const preis = preisbericht(lv.positionen, gewerke, preisliste, berichtExport.kalkulation?.positionen ?? null, anpassungen);
  // Same reader texts as the report: German when chosen, technical ranking tail removed.
  const findings = bericht.findings.filter((f) => !istMock(f)).map((f) => befundAnzeige(f, sprache));
  const alleBlaetter = tabellen(berichtExport, bewertungen, preis);
  const blaetter = Object.fromEntries(alleBlaetter.map((b) => [b.name, b.zeilen]));
  // Priced / estimated bill from the backend price database (#117, #158); only when the report has them.
  const preisBlaetter = alleBlaetter.filter((b) => b.name === "Priced bill" || b.name === "Estimated bill");
  const euroGanz = new Intl.NumberFormat(sprache === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  const geaendert = preis.zeilen.filter((r) => r.war && r.diff && Math.abs(r.diff) / Math.abs(r.war) >= .02).sort((a, b) => Math.abs(b.diff ?? 0) - Math.abs(a.diff ?? 0));

  function csvPreis() {
    const kopf = ["OZ", t("Item"), t("Quantity"), t("Unit"), t("Was"), t("Unit price"), t("Estimated"), t("Range from"), t("Range to"), "±", t("Source"), t("Why"), t("References")];
    const zelle = (w: string | number | null) => {
      const s = w == null ? "" : String(w);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const zeilen = [kopf, ...preis.zeilen.map((r) => [r.oz, r.kurztext, r.menge, r.einheit, r.war, r.epGeschaetzt, r.geschaetzt, r.von, r.bis, r.diff, t(QUELLE_NAME[r.quelle]), t(r.grund, r.werte), (r.verweise ?? []).map((v) => v.url ? `${v.titel} ${v.url}` : v.titel).join(" | ")])];
    const blob = new Blob(["\uFEFF" + zeilen.map((z) => z.map(zelle).join(";")).join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: dateiname(bericht.lv.name, "csv") });
    a.click(); URL.revokeObjectURL(url);
  }

  const angebot = marge?.angebot ?? preis.geschaetzt;
  const unter = marge?.median != null ? angebot - marge.median : null;

  return (
    <main className={styles.seite}>
      <div className={wStyles.zusammenfassung}>
        <div className={wStyles.hero}>
          <div className={wStyles.heroLabel}>{t("Final offer")}</div>
          <div className={wStyles.heroPreis}>{euroGanz.format(angebot)}</div>
          {unter != null && (
            <div className={wStyles.heroDelta} style={{ color: unter <= 0 ? "var(--good)" : "var(--bad)" }}>
              {euroGanz.format(Math.abs(unter))} {unter <= 0 ? t("under the competitor median") : t("above the competitor median")}
            </div>
          )}
          <ul className={wStyles.zeilen}>
            <li><span className={wStyles.muted}>{t("Direct costs (evaluated)")}</span><span>{euroGanz.format(preis.geschaetzt)}</span></li>
            {marge && <li><span className={wStyles.muted}>{t("Our margin")}</span><span>{marge.marge.toLocaleString(sprache === "de" ? "de-DE" : "en-GB", { maximumFractionDigits: 1 })} %</span></li>}
            {marge && <li><span className={wStyles.muted}>{t("Our profit")}</span><span>{euroGanz.format(marge.gewinn)}</span></li>}
            {marge && <li><span className={wStyles.muted}>{t("Project duration")}</span><span>{t("{n} of 12 months", { n: marge.monate })}</span></li>}
            <li><span>{t("Final offer")}</span><span>{euroGanz.format(angebot)}</span></li>
          </ul>
        </div>
      </div>

      <nav className={`${styles.glas} ${styles.leiste}`} aria-label={t("Export")}>
        <a className={styles.zurueck} href="/">{t("‹ Review")}</a>
        <div className={styles.aktionen}>
          {/* Print opens the printer dialog; Save PDF downloads a real file without any dialog (lib/berichtpdf.ts). */}
          <button type="button" className={styles.knopfZweit} onClick={() => window.print()}><Icon name="report" /> {t("Print")}</button>
          <button type="button" className={styles.knopf} onClick={() => pdfSpeichern(berichtExport, bewertungen, preis)}><Icon name="download" /> {t("Save PDF")}</button>
          <button type="button" className={styles.knopf} onClick={() => excel(berichtExport, bewertungen, preis)}><Icon name="download" /> {t("Download Excel")}</button>
          <button type="button" className={styles.knopf} onClick={() => csvPreis()}><Icon name="download" /> {t("Price list as CSV")}</button>
        </div>
        {/* GAEB DA XML (lib/gaeb.ts): the bill in the chosen phase, and the estimated bill as an offer (X84). */}
        <div className={styles.aktionen} role="group" aria-label="GAEB">
          <select className={styles.knopfZweit} value={phase} onChange={(e) => setPhase(e.target.value as GaebPhase)} aria-label={t("GAEB phase")}>
            {GAEB_PHASEN.map((p) => <option key={p.dp} value={p.dp}>{t(p.name)}</option>)}
          </select>
          <button type="button" className={styles.knopf} onClick={() => gaeb(bericht, phase)}><Icon name="download" /> {t("GAEB · bill")}</button>
          <button type="button" className={styles.knopf} onClick={() => gaeb(bericht, "84", preis)}><Icon name="download" /> {t("GAEB X84 · estimated bill")}</button>
        </div>
      </nav>

      <article className={styles.blatt}>
        <header className={styles.kopf}>
          <p className={styles.eyebrow}>Review report · {zustand.quelle}</p>
          <h1>{lv.name}</h1>
          <p className={styles.quelle}>Source: {lv.quelle}</p>
        </header>

        <dl className={styles.zahlen}>
          <div><dt>{t("Items")}</dt><dd>{zahl.format(lv.positionen.length)}</dd></div>
          <div><dt>{t("Entries")}</dt><dd>{zahl.format(findings.length)}</dd></div>
          <div><dt>{t("Critical")}</dt><dd>{zahl.format(kennzahlen.kritisch)}</dd></div>
        </dl>

        {/* Final estimated price (team spec): was vs estimated, then the changed items. */}
        <dl className={styles.zahlen}>
          <div><dt>{t("Was")}</dt><dd>{euroGanz.format(preis.war)}</dd></div>
          <div className={styles.geschaetzt}><dt>{t("Final estimated price")}</dt><dd>{euroGanz.format(preis.geschaetzt)}</dd></div>
          <div><dt>{t("Difference")}</dt><dd style={{ color: preis.diff > 0 ? "var(--sev-kritisch)" : "var(--sev-ok)" }}>{preis.diff > 0 ? "+" : ""}{euroGanz.format(preis.diff)}</dd></div>
        </dl>
        {geaendert.length > 0 && (
          <>
            <h2>{t("Estimated price report")} <small className={styles.quelle}>{t("{a} of {b}", { a: Math.min(100, geaendert.length), b: geaendert.length })} {t("changed items")}</small></h2>
            <div className={styles.rahmen}>
              <table className={styles.tabelle}>
                <thead><tr><th>OZ</th><th>{t("Item")}</th><th className={styles.rechts}>{t("Was")}</th><th className={styles.rechts}>{t("Estimated")}</th><th className={styles.rechts}>±</th><th>{t("Why")}</th></tr></thead>
                <tbody>
                  {geaendert.slice(0, 100).map((r, i) => (
                    <tr key={`${r.oz}-${i}`}>
                      <td className={styles.oz}>{r.oz}</td><td>{d(r.kurztext)}</td>
                      <td className={styles.rechts}>{euroGanz.format(r.war ?? 0)}</td><td className={styles.rechts}>{euroGanz.format(r.geschaetzt ?? 0)}</td>
                      <td className={styles.rechts} style={{ color: (r.diff ?? 0) > 0 ? "var(--sev-kritisch)" : "var(--sev-ok)" }}>{(r.diff ?? 0) > 0 ? "+" : ""}{euroGanz.format(r.diff ?? 0)}</td>
                      <td className={styles.quelle}>{t(r.grund, r.werte)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <h2>{t("Findings")}</h2>
        {findings.length === 0 ? <p className={styles.quelle}>{t("No findings.")}</p> : (
          <div className={styles.rahmen}>
            <table className={`${styles.tabelle} ${styles.befunde}`}>
              <thead><tr><th>{t("OZ")}</th><th>{t("Category")}</th><th>{t("Severity")}</th><th className={styles.spFinding}>{t("Finding")}</th><th className={styles.spVorschlag}>{t("Suggestion")}</th><th>{t("Source")}</th><th className={styles.rechts}>{t("Euro impact")}</th><th>{t("Review status")}</th><th className={styles.spKommentar}>{t("Comment")}</th></tr></thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.id} style={{ "--sev": `var(--sev-${f.schwere})` } as React.CSSProperties}>
                    <td className={styles.oz}>{f.oz}</td>
                    <td>{t(KATEGORIE[f.kategorie] ?? f.kategorie)}</td>
                    <td><span className={styles.schwere}>{t(SEVERITY_LABELS[f.schwere] ?? f.schwere)}</span></td>
                    <td className={styles.spFinding}><b>{f.titel}</b><span className={styles.begruendung}>{f.begruendung}</span></td>
                    <td className={styles.spVorschlag}>{f.vorschlag}</td>
                    <td className={styles.regel}>{t(f.quelle === "regel" ? "Rule" : "Model")}<br />{f.regel_id.replaceAll("_", "_\u200b")}</td>
                    <td className={styles.rechts}>{f.euro_wirkung === null ? t("unknown") : euro.format(f.euro_wirkung)}</td>
                    <td>{t(statusName(bewertungVon(bewertungen, f.id).status))}</td>
                    <td className={styles.spKommentar}>{bewertungVon(bewertungen, f.id).kommentar}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {preisBlaetter.map((b) => (
          <section key={b.name}>
            <h2>{t(b.name)}</h2>
            {b.name === "Estimated bill" && (
              <p className={styles.quelle}>Green “+ new” = added · red, struck through “− removed” = removed · yellow “old → new” = updated.</p>
            )}
            <Blatt zeilen={b.zeilen} stile={b.stile} leer="No items." />
          </section>
        ))}

        <h2>{t("Quantity totals")}</h2>
        <Blatt zeilen={blaetter["Quantities"]} leer="No quantities to total." />

        <h2>{t("Bidder questions")}</h2>
        <Blatt zeilen={blaetter["Bidder questions"]} leer="No bidder questions." />

        <h2>{t("Items")}</h2>
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead><tr><th>{t("OZ")}</th><th>{t("Short description")}</th><th className={styles.rechts}>{t("Quantity")}</th><th>{t("Unit")}</th><th className={styles.rechts}>{t("Unit price")}</th><th className={styles.rechts}>{t("Total price")}</th></tr></thead>
            <tbody>
              {lv.positionen.map((p, i) => (
                <tr key={`${p.oz}-${i}`}>
                  <td className={styles.oz}>{p.oz}</td>
                  <td>{d(p.kurztext)}</td>
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
