"use client";

// Margin slider: competitor bids from an Excel file → markup histogram with a range slider, the competitor median
// as benchmark and our price just below it (never under our own costs). Logic in lib/marge.ts.
import { useMemo, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { auswerten, bieterListe, histogramm, leseGebote, leseXlsx, punkte, type Bieter, type Gebot } from "@/lib/marge";
import { Icon } from "../icon/Icon";
import { Info } from "../info/Info";
import styles from "./marge.module.css";

const FAECHER = 24;
type Spalte = "name" | "aufschlag" | "angebot";

export function Marge() {
  const { e, t } = useEinstellungen();
  const [gebote, setGebote] = useState<Gebot[]>([]);
  const [datei, setDatei] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [wahl, setWahl] = useState<[number, number] | null>(null);
  const [abstand, setAbstand] = useState(-1);
  const [sortierung, setSortierung] = useState<{ spalte: Spalte; auf: boolean }>({ spalte: "aufschlag", auf: true });
  const loc = e.sprache === "de" ? "de-DE" : "en-GB";
  const euro = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  const ep = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR" });
  const pz = (x: number) => `${x.toLocaleString(loc, { maximumFractionDigits: 1 })} %`;

  const werte = useMemo(() => bieterListe(punkte(gebote)).map((x) => x.aufschlag), [gebote]);
  const lo = werte.length ? Math.floor(Math.min(...werte)) : 0, hi = werte.length ? Math.ceil(Math.max(...werte)) : 0;
  const b: [number, number] = wahl ?? [lo, hi];
  const r = auswerten(gebote, b, abstand);
  const balken = useMemo(() => histogramm(werte, lo, hi, FAECHER), [werte, lo, hi]);
  const spitze = Math.max(1, ...balken);
  const f = (x: number) => (hi > lo ? (x - lo) / (hi - lo) : 0);

  async function laden(file: File | undefined) {
    if (!file) return;
    setFehler(null);
    try {
      setGebote(leseGebote(await leseXlsx(await file.arrayBuffer()))); setDatei(file.name); setWahl(null); setAbstand(-1);
    } catch (err) {
      setFehler(`${t("Could not read the document")}: ${(err as Error).message}`);
    }
  }

  const { summe, auswahl } = r;
  const diff = summe.uns - summe.konk;
  const farbe = (d: number) => (d < 0 ? "var(--good)" : d > 0 ? "var(--bad)" : undefined);
  const vz = (d: number) => (d > 0 ? "+" : "");
  const { spalte, auf } = sortierung;
  const zeilen = [...r.bieter].sort((x: Bieter, y: Bieter) => (auf ? 1 : -1) * (spalte === "name" ? x.name.localeCompare(y.name, loc) : x[spalte] - y[spalte]));
  const kopf = (s: Spalte, label: string) => (
    <th className={s === "name" ? undefined : styles.rechts} aria-sort={spalte === s ? (auf ? "ascending" : "descending") : undefined}>
      <button type="button" className={styles.sortieren} onClick={() => setSortierung({ spalte: s, auf: spalte === s ? !auf : true })}>
        {t(label)}{spalte === s ? (auf ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );

  return (
    <main className={styles.seite}>
      <h1 className={styles.titel}>{t("Margin")}</h1>
      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("Load competitor bids")}
          <Info text={t("Excel (.xlsx), one row per bid: Provider, Item, Unit, Quantity, Unit price, Current offer, and if known Direct cost, Operating cost %, Profit margin %. A row with provider \"Our company\" per item holds our quantity, direct cost and operating cost %; its profit margin % is our minimum margin.")} /></h2>
        <label className={styles.ablage}>
          <input type="file" accept=".xlsx" onChange={(ev) => { void laden(ev.target.files?.[0]); ev.target.value = ""; }} />
          <Icon name="upload" />{datei ?? t("Choose Excel file")} <small>.xlsx</small>
        </label>
        {fehler && <p className={styles.fehler}>{fehler}</p>}
      </section>

      {werte.length > 0 && (
        <section className={styles.karte}>
          <h2 className={styles.abschnitt}>{t("Competitor markup")}
            <Info text={t("Markup = operating cost % + margin %; without that split it is back-calculated from unit price and direct cost. One value per bidder, weighted by direct cost; the table shows it as profit margin. Drag the handles to narrow the bidders that count.")} /></h2>
          <div className={styles.regler}>
            <p className={styles.spanne}>{pz(b[0])} – {pz(b[1])}</p>
            <svg className={styles.balken} viewBox={`0 0 ${FAECHER * 10} 80`} preserveAspectRatio="none" aria-hidden="true">
              {balken.map((n, i) => {
                const mitte = lo + ((i + 0.5) / FAECHER) * (hi - lo), h = (n / spitze) * 78;
                return n > 0 && <rect key={i} x={i * 10 + 1} y={80 - h} width={8} height={h} data-aus={mitte < b[0] || mitte > b[1] || undefined} />;
              })}
            </svg>
            <div className={styles.schiene}>
              <span className={styles.spur} style={{ left: `calc(11px + (100% - 22px) * ${f(b[0])})`, right: `calc(11px + (100% - 22px) * ${1 - f(b[1])})` }} />
              <input type="range" min={lo} max={hi} step={0.5} value={b[0]} aria-label={t("Lowest markup")} style={{ zIndex: f(b[0]) > 0.5 ? 2 : 1 }}
                onChange={(ev) => setWahl([Math.min(Number(ev.target.value), b[1]), b[1]])} />
              <input type="range" min={lo} max={hi} step={0.5} value={b[1]} aria-label={t("Highest markup")}
                onChange={(ev) => setWahl([b[0], Math.max(Number(ev.target.value), b[0])])} />
            </div>
          </div>
          <div className={styles.kacheln}>
            <div><span>{t("Bidders in range")}</span><strong>{t("{n} of {m}", { n: auswahl.bieter, m: auswahl.vonBietern })}</strong></div>
            <div><span>{t("Average")}</span><strong>{auswahl.mittel == null ? "–" : pz(auswahl.mittel)}</strong></div>
            <div><span>{t("Median")}</span><strong>{auswahl.median == null ? "–" : pz(auswahl.median)}</strong></div>
          </div>
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr>{kopf("name", "Provider")}{kopf("aufschlag", "Profit margin (%)")}{kopf("angebot", "Current offer (EUR)")}</tr></thead>
              <tbody>
                {zeilen.map((x) => <tr key={x.name}><td>{x.name}</td><td className={styles.rechts}>{pz(x.aufschlag)}</td><td className={styles.rechts}>{euro.format(x.angebot)}</td></tr>)}
                {zeilen.length === 0 && <tr><td colSpan={3} className={styles.leise}>{t("No bidder in this range.")}</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {r.posten.length > 0 && (
        <section className={styles.karte}>
          <h2 className={styles.abschnitt}>{t("Our price")}
            <Info text={t("Per item our markup = competitor median + offset, never below our operating costs plus the minimum margin. The competitor median price uses our direct cost with their median markup.")} /></h2>
          <label className={styles.versatz}>
            <span>{t("Offset to the competitor median")}: <b>{vz(abstand)}{abstand.toLocaleString(loc, { minimumFractionDigits: 1 })} {t("points")}</b></span>
            <input type="range" min={-10} max={10} step={0.5} value={abstand} onChange={(ev) => setAbstand(Number(ev.target.value))} />
          </label>
          <div className={styles.kacheln}>
            <div><span>{t("Our bid total")}</span><strong>{euro.format(summe.uns)}</strong><small>{t("Competitor median")}: {euro.format(summe.konk)}</small></div>
            <div><span>{t("Difference")}</span><strong style={{ color: farbe(diff) }}>{vz(diff)}{euro.format(diff)}</strong>
              <small style={{ color: farbe(diff) }}>{summe.konk ? `${vz(diff)}${pz((diff / summe.konk) * 100)}` : "–"} · {t(diff <= 0 ? "cheaper" : "more expensive")}</small></div>
            <div><span>{t("Our profit")}</span><strong>{euro.format(summe.gewinn)}</strong><small>{t("at the median")}: {euro.format(summe.gewinnKonk)} ({vz(summe.gewinn - summe.gewinnKonk)}{euro.format(summe.gewinn - summe.gewinnKonk)})</small></div>
          </div>
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr><th>{t("Item")}</th><th className={styles.rechts}>{t("Data points")}</th><th className={styles.rechts}>{t("Median (mean)")}</th><th className={styles.rechts}>{t("Our markup")}</th>
                <th className={styles.rechts}>{t("Our unit price")}</th><th className={styles.rechts}>{t("Median price")}</th><th className={styles.rechts}>{t("Difference")}</th></tr></thead>
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
