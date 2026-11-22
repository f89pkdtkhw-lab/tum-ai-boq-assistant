"use client";

// Margin page (variant A): pick competitors with checkboxes, set our margin on an iOS-style
// slider (red at the cost floor → green at/above the competitor median). Logic in lib/marge.ts.
import { useEffect, useMemo, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { auswerten, leseGebote, leseXlsx, type Bieter, type Gebot } from "@/lib/marge";
import { speichereMargeStand } from "@/lib/wizard";
import { Icon } from "../icon/Icon";
import { Info } from "../info/Info";
import styles from "./marge.module.css";

type Spalte = "name" | "aufschlag" | "angebot";

const kuerzel = (name: string) => {
  const teile = name.replace(/&/g, " ").split(/\s+/).filter((w) => !/^(gmbh|kg|ag|ltd|inc|und|and|the|of)$/i.test(w));
  return ((teile[0]?.[0] ?? "") + (teile[1]?.[0] ?? teile[0]?.[1] ?? "")).toUpperCase();
};
const avFarbe = (name: string) => {
  let h = 0;
  for (const c of name) h = (h * 33 + c.charCodeAt(0)) >>> 0;
  return `hsl(${h % 360} 42% 42%)`;
};

export function Marge() {
  const { e, t } = useEinstellungen();
  const [gebote, setGebote] = useState<Gebot[]>([]);
  const [datei, setDatei] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [wahl, setWahl] = useState<Set<string> | null>(null);
  const [suche, setSuche] = useState("");
  const [ausreisser, setAusreisser] = useState(true);
  const [monate, setMonate] = useState(12);
  const [marge, setMarge] = useState<number | null>(null);
  const [sortierung, setSortierung] = useState<{ spalte: Spalte; auf: boolean }>({ spalte: "aufschlag", auf: true });
  const loc = e.sprache === "de" ? "de-DE" : "en-GB";
  const euro = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  const ep = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR" });
  const pz = (x: number) => `${x.toLocaleString(loc, { maximumFractionDigits: 1 })} %`;

  const namen = useMemo(() => wahl ?? (gebote.length ? undefined : []), [wahl, gebote]);
  const r = useMemo(() => auswerten(gebote, { namen, ausreisser, marge, monate }), [gebote, namen, ausreisser, marge, monate]);
  const { summe, auswahl } = r;
  const diff = summe.uns - summe.konk;
  const farbe = (d: number) => (d < 0 ? "var(--good)" : d > 0 ? "var(--bad)" : undefined);
  const vz = (d: number) => (d > 0 ? "+" : "");
  const { spalte, auf } = sortierung;
  const q = suche.trim().toLowerCase();
  const zeilen = [...r.liste]
    .filter((x) => !q || x.name.toLowerCase().includes(q))
    .sort((x: Bieter, y: Bieter) => (auf ? 1 : -1) * (spalte === "name" ? x.name.localeCompare(y.name, loc) : x[spalte] - y[spalte]));
  const kopf = (s: Spalte, label: string) => (
    <th className={s === "name" ? undefined : styles.rechts} aria-sort={spalte === s ? (auf ? "ascending" : "descending") : undefined}>
      <button type="button" className={styles.sortieren} onClick={() => setSortierung({ spalte: s, auf: spalte === s ? !auf : true })}>
        {t(label)}{spalte === s ? (auf ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );

  async function laden(file: File | undefined) {
    if (!file) return;
    setFehler(null);
    try {
      const g = leseGebote(await leseXlsx(await file.arrayBuffer()));
      setGebote(g); setDatei(file.name); setWahl(null); setMarge(null); setSuche(""); setAusreisser(true); setMonate(12);
    } catch (err) {
      setFehler(`${t("Could not read the document")}: ${(err as Error).message}`);
    }
  }

  function toggle(name: string, an: boolean) {
    const alle = new Set(wahl ?? r.liste.map((x) => x.name));
    if (an) alle.add(name); else alle.delete(name);
    setWahl(alle);
  }
  function alle(an: boolean) {
    const sichtbar = new Set(zeilen.map((x) => x.name));
    const basis = new Set(wahl ?? r.liste.map((x) => x.name));
    for (const n of sichtbar) { if (an) basis.add(n); else basis.delete(n); }
    setWahl(basis);
  }

  const spanne = Math.max(0.1, r.hiMarge - r.boden);
  const pct = (x: number) => `${((Math.min(r.hiMarge, Math.max(r.boden, x)) - r.boden) / spanne) * 100}%`;
  const abweichung = r.medianMarge == null ? null : r.marge - r.medianMarge;
  const monateZahl = Number.isFinite(monate) && monate > 0 ? monate : 12;
  useEffect(() => {
    if (!r.liste.length) return;
    speichereMargeStand({
      angebot: summe.uns, gewinn: summe.gewinn, marge: r.marge, median: summe.konk,
      monate: monateZahl, bieter: auswahl.bieter, ausreisserAus: ausreisser,
    });
  }, [r.liste.length, summe.uns, summe.gewinn, r.marge, summe.konk, monateZahl, auswahl.bieter, ausreisser]);

  return (
    <main className={styles.seite}>
      <div className={styles.kopf}>
        <h1 className={styles.titel}>{t("Margin")}</h1>
        {datei && <span className={styles.datei}>{datei} <small>· {t("Test or project file")}</small></span>}
      </div>

      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("Load competitor bids")}
          <Info text={t("Excel (.xlsx), one row per bid: Provider, Item, Unit, Quantity, Unit price, Current offer, and if known Direct cost, Operating cost %, Profit margin %. A row with provider \"Our company\" per item holds our quantity, direct cost and operating cost %; its profit margin % is our minimum margin.")} /></h2>
        <label className={styles.ablage}>
          <input type="file" accept=".xlsx" onChange={(ev) => { void laden(ev.target.files?.[0]); ev.target.value = ""; }} />
          <Icon name="upload" />{datei ?? t("Choose Excel file")} <small>.xlsx</small>
        </label>
        {fehler && <p className={styles.fehler}>{fehler}</p>}
      </section>

      {r.liste.length > 0 && (
        <div className={styles.layout}>
          <section className={styles.karte}>
            <div className={styles.zeile}>
              <h2 className={styles.abschnitt}>{t("Competitor list")}
                <Info text={t("Mean and median are taken only from the checked bidders. Operating cost % and margin % are shown where the split is disclosed; otherwise markup is back-calculated from unit price and our direct cost.")} /></h2>
              <span className={styles.hint}>{t("{n} of {m} selected", { n: auswahl.bieter, m: auswahl.vonBietern })}</span>
            </div>
            <div className={styles.zeile}>
              <label className={styles.suche}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
                <input type="search" value={suche} onChange={(ev) => setSuche(ev.target.value)} placeholder={t("Search competitors")} />
              </label>
              <div>
                <button type="button" className={styles.linkbtn} onClick={() => alle(true)}>{t("All")}</button>
                {" "}
                <button type="button" className={styles.linkbtn} onClick={() => alle(false)}>{t("None")}</button>
              </div>
            </div>
            <div className={styles.rahmen}>
              <table className={styles.tabelle}>
                <thead>
                  <tr>
                    <th style={{ width: 36 }} />
                    {kopf("name", "Provider")}
                    {kopf("angebot", "Current offer (EUR)")}
                    <th className={styles.rechts}>{t("Operating cost %")}</th>
                    <th className={styles.rechts}>{t("Margin %")}</th>
                    {kopf("aufschlag", "Markup")}
                  </tr>
                </thead>
                <tbody>
                  {zeilen.map((x) => {
                    const gesperrt = ausreisser && x.ausreisser;
                    const an = !gesperrt && (wahl == null || wahl.has(x.name));
                    return (
                      <tr key={x.name} className={gesperrt ? styles.aus : undefined}>
                        <td>
                          <input className={styles.chk} type="checkbox" checked={an} disabled={gesperrt}
                            aria-label={x.name} onChange={(ev) => toggle(x.name, ev.target.checked)} />
                        </td>
                        <td>
                          <span className={styles.bieter}>
                            <span className={styles.av} style={{ background: avFarbe(x.name) }}>{kuerzel(x.name)}</span>
                            {x.name}
                          </span>
                        </td>
                        <td className={styles.rechts}>{euro.format(x.angebot)}</td>
                        <td className={styles.rechts}>{x.bgk == null ? "–" : x.bgk.toLocaleString(loc, { maximumFractionDigits: 1 })}</td>
                        <td className={styles.rechts}>{x.marge == null ? "–" : x.marge.toLocaleString(loc, { maximumFractionDigits: 1 })}</td>
                        <td className={styles.rechts}>{pz(x.aufschlag)}{x.ausreisser && <span className={styles.marke}>{t("outlier")}</span>}</td>
                      </tr>
                    );
                  })}
                  {zeilen.length === 0 && <tr><td colSpan={6} className={styles.leise}>{t("No matching competitor.")}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <section className={styles.karte}>
            <div className={styles.preisKicker}>{t("Our bid")}</div>
            <p className={styles.preis}>{euro.format(summe.uns)}</p>
            <p className={styles.delta} style={{ color: farbe(diff) }}>
              {vz(diff)}{euro.format(diff)}{summe.konk ? ` (${vz(diff)}${pz((diff / summe.konk) * 100)})` : ""}{" "}
              <span>{t(diff <= 0 ? "under the competitor median" : "above the competitor median")}</span>
            </p>

            <div className={styles.kacheln}>
              <div><span>{t("Average markup")}</span><strong>{auswahl.mittel == null ? "–" : pz(auswahl.mittel)}</strong></div>
              <div><span>{t("Median markup")}</span><strong>{auswahl.median == null ? "–" : pz(auswahl.median)}</strong></div>
              <div><span>{t("Our profit")}</span><strong>{euro.format(summe.gewinn)}</strong></div>
            </div>

            <div className={styles.slider} style={{ ["--slider-hue" as string]: String(r.hue) }}>
              <h3>{t("Our margin")}</h3>
              <div className={styles.live}>
                <div className={styles.wert}>{pz(r.marge)}</div>
                <div className={styles.sub}>
                  {t("Bid")} {euro.format(summe.uns)}
                  {abweichung != null && ` · ${vz(abweichung)}${Math.abs(abweichung).toLocaleString(loc, { maximumFractionDigits: 1 })} ${t("points")} ${t("from the median")}`}
                </div>
              </div>
              {r.medianMarge != null && (
                <div className={styles.marks}>
                  <div className={`${styles.mark} ${styles.markMedian}`} style={{ left: pct(r.medianMarge) }}><b>{t("Median")} {pz(r.medianMarge)}</b></div>
                  {r.mittelMarge != null && <div className={`${styles.mark} ${styles.markMittel}`} style={{ left: pct(r.mittelMarge) }}><b>{t("Mean")} {pz(r.mittelMarge)}</b></div>}
                </div>
              )}
              <div className={styles.trackWrap}>
                <div className={styles.track}>
                  <div className={styles.fill} style={{ width: pct(r.marge) }} />
                  {r.medianMarge != null && <div className={`${styles.tick} ${styles.tickMedian}`} style={{ left: pct(r.medianMarge) }} />}
                  {r.mittelMarge != null && <div className={styles.tick} style={{ left: pct(r.mittelMarge) }} />}
                </div>
                <div className={styles.schiene}>
                  <input type="range" min={r.boden} max={r.hiMarge} step={0.1} value={r.marge}
                    aria-label={t("Our margin")}
                    onChange={(ev) => setMarge(Number(ev.target.value))} />
                </div>
              </div>
              <div className={styles.ends}>
                <span>{t("Cost floor {pct}", { pct: pz(r.boden) })}</span>
                <span>{pz(r.hiMarge)}</span>
              </div>
              <p className={styles.hintFloor}>{t("The margin cannot go below our pro-rated operating costs plus the {pct} minimum margin.", { pct: pz(r.boden) })}</p>
            </div>

            <div className={styles.settings}>
              <label className={styles.srow}>
                <span className={styles.lbl}>
                  <b>{t("Exclude outliers")}</b>
                  <small>{r.liste.some((x) => x.ausreisser)
                    ? t("{names} ({pct} markup) by IQR", {
                        names: r.liste.filter((x) => x.ausreisser).map((x) => x.name).join(", "),
                        pct: pz(r.liste.find((x) => x.ausreisser)!.aufschlag),
                      })
                    : t("No outliers in this selection.")}</small>
                </span>
                <span className={styles.sw}>
                  <input type="checkbox" checked={ausreisser} onChange={(ev) => setAusreisser(ev.target.checked)} />
                  <i />
                </span>
              </label>
              <label className={styles.srow}>
                <span className={styles.lbl}>
                  <b>{t("Project duration")}</b>
                  <small>{t("Operating costs pro-rated {n}/12 of the annual figures", { n: String(monateZahl) })}</small>
                </span>
                <span className={styles.dauer}>
                  <input type="number" min={0.5} max={36} step={0.5} value={monate}
                    onChange={(ev) => setMonate(Number(ev.target.value))} />
                  {t("months")}
                </span>
              </label>
            </div>
          </section>
        </div>
      )}

      {r.posten.length > 0 && (
        <section className={`${styles.karte} ${styles.posten}`}>
          <div className={styles.zeile}>
            <h2 className={styles.abschnitt}>{t("Our price per item")}
              <Info text={t("Our markup = pro-rated operating costs + the margin from the slider, never below the cost floor. The median price uses the competitor median markup of the selection.")} /></h2>
          </div>
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead>
                <tr>
                  <th>{t("Position")}</th>
                  <th className={styles.rechts}>{t("Data points")}</th>
                  <th className={styles.rechts}>{t("Median (mean)")}</th>
                  <th className={styles.rechts}>{t("Our markup")}</th>
                  <th className={styles.rechts}>{t("Our unit price")}</th>
                  <th className={styles.rechts}>{t("Median price")}</th>
                  <th className={styles.rechts}>{t("Difference")}</th>
                </tr>
              </thead>
              <tbody>
                {r.posten.map((p) => {
                  const d = p.preisKonk == null ? null : p.preis - p.preisKonk;
                  return (
                    <tr key={p.item}>
                      <td>{p.item} <small className={styles.leise}>{p.menge.toLocaleString(loc)} {p.einheit}</small></td>
                      <td className={styles.rechts}>{p.n}{p.raus > 0 && <small className={styles.leise}> · {t(p.raus === 1 ? "1 outlier" : "{n} outliers", { n: p.raus })}</small>}
                        {p.wenig && <span className={styles.marke}>{t("low confidence")}</span>}</td>
                      <td className={styles.rechts}>{p.median == null ? "–" : pz(p.median)}{p.mittel != null && <small className={styles.leise}> ({pz(p.mittel)})</small>}
                        {p.schief && <span className={styles.warn} title={t("Mean and median differ by more than 3 points: skewed data.")}><Icon name="warning" size={14} /></span>}</td>
                      <td className={styles.rechts}>{pz(p.aufschlag)}{p.amBoden && <span className={styles.marke}>{t("floor")}</span>}</td>
                      <td className={styles.rechts}>{ep.format(p.preis)}</td>
                      <td className={styles.rechts}>{p.preisKonk == null ? "–" : ep.format(p.preisKonk)}</td>
                      <td className={styles.rechts} style={{ color: d == null ? undefined : farbe(d) }}>{d == null ? "–" : `${vz(d)}${ep.format(d)} (${vz(d)}${pz((d / p.preisKonk!) * 100)})`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
