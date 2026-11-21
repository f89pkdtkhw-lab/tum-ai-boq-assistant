"use client";

import { useMemo, useState } from "react";
import type { AenderungsStatus, Pruefbericht } from "@/lib/api";
import { aenderung, filtereStatus, kalkulationsZeilen, kosten, mitVorzeichen, STATUS, statusInfo, zaehleStatus } from "@/lib/kalkulation";
import { aktuelleSeite, ausschnitt, seiteNachGroesse, seiteVon, STANDARD_SEITENGROESSE, type Blatt } from "@/lib/seiten";
import { Seiten } from "../seiten/Seiten";
import styles from "./kalkulation.module.css";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
const prozent = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

function Unbekannt() {
  return <span className={styles.unbekannt}>unknown</span>;
}

/**
 * "Priced bill": cost tiles and original → estimated table with colour-coded changes (issue #116).
 * Renders nothing without `kalkulation`/`geschaetztes_lv`, so the report stays unchanged.
 */
export function Kalkulation({ bericht, ozBekannt, onWaehle }: {
  bericht: Pruefbericht; ozBekannt: (oz: string) => boolean; onWaehle: (oz: string, findingId: string | null) => void;
}) {
  const { kalkulation, geschaetztes_lv } = bericht;
  const [status, setStatus] = useState<AenderungsStatus | null>(null);
  const [blatt, setBlatt] = useState<Blatt>({ schluessel: "", seite: 0 });
  const [groesse, setGroesse] = useState(STANDARD_SEITENGROESSE);
  const alle = useMemo(() => kalkulationsZeilen(bericht), [bericht]);
  if (!kalkulation && !geschaetztes_lv) return null;

  const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: kalkulation?.waehrung || "EUR" });
  const k = kosten(kalkulation, geschaetztes_lv, alle);
  const anzahl = zaehleStatus(alle);
  const zeilen = filtereStatus(alle, status);
  const schluessel = status ?? "alle";
  const seite = seiteVon(zeilen.length, aktuelleSeite(blatt, schluessel), groesse);
  const betrag = (n: number | null) => (n === null ? <Unbekannt /> : euro.format(n));
  const f = (n: number) => euro.format(n);

  return (
    <section className={styles.kalkulation} aria-labelledby="kalkulation-titel">
      <h3 id="kalkulation-titel" className={styles.titel}>Priced bill</h3>
      <dl className={styles.kacheln}>
        <div className={styles.kachel}><dt>Original net</dt><dd>{betrag(k.originalNetto)}</dd>
          <small>gross {betrag(k.bruttoOriginal)}</small></div>
        <div className={styles.kachel}><dt>Estimated net</dt><dd>{betrag(k.geschaetztNetto)}</dd>
          <small>{geschaetztes_lv ? <>gross {betrag(k.bruttoGeschaetzt)}</> : "no estimated bill yet"}</small></div>
        <div className={styles.kachel}><dt>Difference</dt>
          <dd>{k.differenz === null ? <Unbekannt /> : mitVorzeichen(k.differenz, f)}</dd>
          <small>{k.prozent === null ? "–" : `${k.prozent > 0 ? "+" : k.prozent < 0 ? "−" : ""}${prozent.format(Math.abs(k.prozent))} %`}</small></div>
        <div className={`${styles.kachel} ${k.ohnePreis > 0 ? styles.kachelWarnung : ""}`}><dt>Without price</dt>
          <dd>{zahl.format(k.ohnePreis)}</dd>
          <small>{k.ohnePreis > 0 ? "not in the net sum" : "every item priced"}</small></div>
      </dl>

      <div className={styles.chips} role="group" aria-label="Filter by change">
        <button type="button" className={`${styles.chip} ${status === null ? styles.chipAktiv : ""}`} aria-pressed={status === null}
          onClick={() => setStatus(null)}>All <span className={styles.anzahl}>{alle.length}</span></button>
        {STATUS.map((s) => (
          <button key={s.wert} type="button" className={`${styles.chip} ${status === s.wert ? styles.chipAktiv : ""}`}
            aria-pressed={status === s.wert} onClick={() => setStatus(s.wert)}>
            <span className={`${styles.marke} ${styles[s.wert]}`} aria-hidden="true">{s.marke}</span>
            {s.name} <span className={styles.anzahl}>{anzahl[s.wert]}</span>
          </button>
        ))}
      </div>

      <Seiten seite={seite} groesse={groesse} beschriftung="Priced bill pages"
        onSeite={(n) => setBlatt({ schluessel, seite: n })}
        onGroesse={(g) => { setGroesse(g); setBlatt({ schluessel, seite: seiteNachGroesse(seite, g) }); }} />

      {zeilen.length === 0 ? (
        <p className={styles.unbekannt}>No items with this change.</p>
      ) : (
        <div className={styles.rahmen}>
          <table className={styles.tabelle}>
            <thead>
              <tr>
                <th scope="col">Change</th><th scope="col">OZ</th><th scope="col">Short description</th><th scope="col">Unit</th>
                <th scope="col" className={styles.rechts}>Quantity</th><th scope="col" className={styles.rechts}>Unit price</th>
                <th scope="col" className={styles.rechts}>Total</th><th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {ausschnitt(zeilen, seite).map((z, i) => {
                const info = statusInfo(z.status);
                const verlinkt = z.findingId !== null || ozBekannt(z.oz);
                return (
                  <tr key={`${z.oz}-${seite.von + i}`} className={styles[z.status]}>
                    <td>
                      <span className={`${styles.marke} ${styles[z.status]}`}>{info.marke}</span>
                      {z.freigabe && <span className={styles.freigabe}>approval required</span>}
                    </td>
                    <td className={styles.oz}>{z.oz}</td>
                    <td className={styles.text}>{z.kurztext || <Unbekannt />}</td>
                    <td>{z.einheit || <Unbekannt />}</td>
                    <td className={styles.rechts}>{aenderung(z.mengeAlt, z.mengeNeu, z.status, zahl.format)}</td>
                    <td className={styles.rechts}>
                      {z.ohnePreis ? <span className={styles.ohnePreis}>no price</span> : z.ep === null ? <Unbekannt /> : euro.format(z.ep)}
                    </td>
                    <td className={styles.rechts}>{aenderung(z.gpAlt, z.gpNeu, z.status, f)}</td>
                    <td className={styles.text}>
                      {verlinkt ? (
                        <button type="button" className={styles.link} onClick={() => onWaehle(z.oz, z.findingId)}
                          aria-label={`Show details for item ${z.oz}`}>{z.grund || "Show item"}</button>
                      ) : (z.grund || "–")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
