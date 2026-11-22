"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { eintragHinzu, lesePreisliste, ladePreisliste, preislisteCsv, speicherePreisliste, type Preis } from "@/lib/preisliste";
import { useT } from "@/lib/einstellungen";
import { vaultApi } from "@/lib/vault";
import { Icon } from "../icon/Icon";
import { Info } from "../info/Info";
import { ProjektAbschluss } from "../history/ProjektAbschluss";
import styles from "./einreichen.module.css";

const SATZ = "lv-stundensatz-v1";
type Reiter = "preise" | "schluss";
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });

/** Menu "Submit" (team sketch): a price list for the price database, and a finished project's final bill. */
/** One page for everything the user submits: the unit price list and a project's real final bill. */
export function Einreichen() {
  const t = useT();
  const router = useRouter();
  const [liste, setListe] = useState<Preis[]>([]);
  const [meldung, setMeldung] = useState<{ ok: boolean; text: string } | null>(null);
  const [reiter, setReiter] = useState<Reiter>("preise");
  const [stundensatz, setStundensatz] = useState(60);
  useEffect(() => {
    setListe(ladePreisliste());
    if (window.location.hash === "#schluss") setReiter("schluss");
    try { const v = Number(window.localStorage.getItem(SATZ)); if (v > 0) setStundensatz(v); } catch { /* default rate */ }
  }, []);

  async function laden(datei: File | undefined) {
    if (!datei) return;
    try {
      const neu = lesePreisliste(await datei.text());
      if (neu.length === 0) throw new Error(t("No prices found in this file."));
      speicherePreisliste(neu);
      setListe(neu);
      setMeldung({ ok: true, text: t("{n} prices saved from {name}.", { n: neu.length, name: datei.name }) });
      void vaultApi.hochladen(datei, "preisliste").catch(() => {});
    } catch (e) {
      setMeldung({ ok: false, text: e instanceof Error ? e.message : t("Unknown error.") });
    }
  }



  function speichern(neu: Preis[]) { speicherePreisliste(neu); setListe(neu); }
  function hinzufuegen(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget);
    const n = (k: string) => Number(String(f.get(k) ?? "").replace(",", ".")) || 0;
    const item = String(f.get("item") ?? "").trim();
    if (!item) return;
    const satz = n("stundensatz");
    try { window.localStorage.setItem(SATZ, String(satz)); } catch { /* default next time */ }
    setStundensatz(satz);
    speichern(eintragHinzu(liste, { item, unit: String(f.get("unit") ?? ""), material: n("material"), stunden: n("stunden"), stundensatz: satz }));
    setMeldung({ ok: true, text: t("{item} saved.", { item }) });
    (ev.currentTarget.elements.namedItem("item") as HTMLInputElement | null)?.focus();
    ev.currentTarget.reset();
  }
  function herunterladen() {
    const url = URL.createObjectURL(new Blob([preislisteCsv(liste)], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "preisliste.csv" });
    a.click(); URL.revokeObjectURL(url);
  }
  const zeigeReiter = (r: Reiter) => { setReiter(r); history.replaceState(null, "", `#${r}`); };

  return (
    <main className={styles.seite}>
      <h1 className={styles.titel}>{t("Submit")}</h1>
      <div className={styles.reiter} role="tablist" aria-label={t("Submit")}>
        {([["preise", "Unit prices", "price"], ["schluss", "Closed project", "report"]] as const).map(([r, name, icon]) => (
          <button key={r} type="button" role="tab" id={`tab-${r}`} aria-selected={reiter === r} aria-controls={r} onClick={() => zeigeReiter(r)}>
            <Icon name={icon} size={16} />{t(name)}
          </button>
        ))}
      </div>

      {reiter === "preise" && <section id="preise" role="tabpanel" aria-labelledby="tab-preise" className={styles.karte}>
        <h2 className={styles.abschnitt}><Icon name="price" size={18} />{t("Bill price per unit")}
          <Info text={t("Upload a price list (CSV or JSON with item, unit and price), or build your own: material per unit plus labour hours × hourly rate. It is kept in this browser as the price database and used in the full price report until the shared price database is connected.")} /></h2>
        <div className={styles.knoepfe}>
          <label className={styles.ablage}>
            <input type="file" accept=".csv,.txt,.json" onChange={(e) => void laden(e.target.files?.[0])} />
            <Icon name="upload" size={20} /> {t("Choose price list")} <small>CSV · JSON</small>
          </label>
        </div>

        <form className={styles.formular} onSubmit={hinzufuegen}>
          <h3>{t("Add your own price")}</h3>
          <label className={styles.breit}>{t("Item")}<input name="item" required placeholder={t("e.g. Mauerarbeiten KS-Mauerwerk 24 cm")} /></label>
          <label>{t("Unit")}<input name="unit" required placeholder="m²" list="einheiten" /></label>
          <datalist id="einheiten">{["m²", "m³", "m", "St", "t", "kg", "psch", "h"].map((u) => <option key={u} value={u} />)}</datalist>
          <label>{t("Material €/unit")}<input name="material" inputMode="decimal" placeholder="0" /></label>
          <label>{t("Labour hours/unit")}<input name="stunden" inputMode="decimal" placeholder="0" /></label>
          <label>{t("Hourly rate €/h")}<input name="stundensatz" inputMode="decimal" defaultValue={stundensatz} key={stundensatz} /></label>
          <button type="submit" className={styles.primaer}>+ {t("Add")}</button>
        </form>

        {meldung && <p className={meldung.ok ? styles.ok : styles.fehler} role="status">{meldung.text}</p>}
        {liste.length > 0 && (
          <>
            <div className={styles.rahmen}>
              <table className={styles.tabelle}>
                <thead><tr><th>{t("Item")}</th><th>{t("Unit")}</th><th className={styles.rechts}>{t("Material")}</th><th className={styles.rechts}>{t("Labour")}</th>
                  <th className={styles.rechts}>{t("Price per unit")}</th><th aria-label={t("Remove")} /></tr></thead>
                <tbody>
                  {liste.slice(0, 300).map((p, i) => (
                    <tr key={`${p.item}-${p.unit}-${i}`}><td>{p.item}</td><td>{p.unit}</td>
                      <td className={styles.rechts}>{p.material === undefined ? "–" : euro.format(p.material)}</td>
                      <td className={styles.rechts}>{p.lohn === undefined ? "–" : <>{euro.format(p.lohn)}{p.stunden !== undefined && <small className={styles.klein}> · {p.stunden} h</small>}</>}</td>
                      <td className={styles.rechts}><b>{euro.format(p.preis)}</b></td>
                      <td><button type="button" className={styles.weg} aria-label={`${t("Remove")} ${p.item}`} onClick={() => speichern(liste.filter((_, j) => j !== i))}>×</button></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={styles.zeile}>
              <span className={styles.klein}>{t("{n} prices in the price database", { n: liste.length })}{liste.length > 300 && ` · ${t("first 300 shown")}`}</span>
              <span className={styles.knoepfe}>
                <button type="button" className={styles.leise} onClick={herunterladen}><Icon name="download" size={14} /> {t("Download CSV")}</button>
                <button type="button" className={styles.leise} onClick={() => { speichern([]); setMeldung(null); }}>{t("Remove all")}</button>
              </span>
            </div>
          </>
        )}
      </section>}

      {reiter === "schluss" && <section id="schluss" role="tabpanel" aria-labelledby="tab-schluss" className={styles.abschnittBlock}>
        <ProjektAbschluss offen onFertig={(fall) => router.push(`/vault?tab=historie&fall=${encodeURIComponent(fall.case_id)}`)} />
      </section>}
    </main>
  );
}
