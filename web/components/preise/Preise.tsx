"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type PreisEintrag, type Preisliste } from "@/lib/api";
import { abfrage, filtere, preisFehler, speicherBody, vorschau } from "@/lib/preis-db";
import { useT } from "@/lib/einstellungen";
import { PREIS_LV_FORMATE, PREISLISTE_FORMATE, preislisteText } from "@/lib/preisliste";
import { beilageFehler } from "@/lib/regelwerk";
import { DateiWahl } from "../ui/DateiWahl";
import styles from "../history/history.module.css";
import eigene from "./preise.module.css";

const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });

/** Price database (issue #134): upload a priced bill once, keep its unit prices for later reviews. */
export function Preise() {
  const t = useT();
  const [preisDatei, setPreisDatei] = useState<File | null>(null);
  const [lvDatei, setLvDatei] = useState<File | null>(null);
  const lauf = useRef(0);
  const [liste, setListe] = useState<Preisliste | null>(null);
  const [meldung, setMeldung] = useState<{ art: "fehler" | "ok" | "laeuft"; text: string } | null>(null);
  const [db, setDb] = useState<PreisEintrag[] | null>(null);
  const [dbFehler, setDbFehler] = useState("");
  const [item, setItem] = useState("");
  const [unit, setUnit] = useState("");

  const laden = useCallback(async () => {
    try {
      setDb(await api.preise(abfrage("", "")));
      setDbFehler("");
    } catch (f) {
      setDb(null);
      setDbFehler(preisFehler("laden", f));
    }
  }, []);
  useEffect(() => { void laden(); }, [laden]);

  /** Reads the price file; a D84 offer gets its item texts from the matching tender bill (D83/X83), if chosen. */
  async function importiere(datei: File | null, lv: File | null) {
    const nummer = ++lauf.current;
    setListe(null);
    if (!datei) { setMeldung(null); return; }
    const lokal = beilageFehler(datei, PREISLISTE_FORMATE, "Price file") ?? (lv ? beilageFehler(lv, PREIS_LV_FORMATE, "Matching bill") : null);
    if (lokal) { setMeldung({ art: "fehler", text: lokal }); return; }
    setMeldung({ art: "laeuft", text: t("Reading {name} …", { name: lv ? `${datei.name} + ${lv.name}` : datei.name }) });
    try {
      const neu = await api.importierePreisliste(datei, lv);
      if (nummer !== lauf.current) return;
      setListe(neu);
      setMeldung({ art: "ok", text: preislisteText(neu) });
      void laden();
    } catch (f) {
      if (nummer !== lauf.current) return;
      setMeldung({ art: "fehler", text: preisFehler("import", f) });
    }
  }

  const zeilen = liste ? vorschau(liste) : [];
  const body = speicherBody(zeilen);

  async function speichern() {
    setMeldung({ art: "laeuft", text: t("Saving {n} prices …", { n: body.length }) });
    try {
      const gespeichert = await api.speicherePreise(body);
      setMeldung({ art: "ok", text: t("{n} prices saved to the price database.", { n: gespeichert.length }) });
      setListe(null);
      setPreisDatei(null);
      setLvDatei(null);
      void laden();
    } catch (f) {
      setMeldung({ art: "fehler", text: preisFehler("speichern", f) });
    }
  }

  const gezeigt = db ? filtere(db, item, unit) : [];
  return (
    <div className={styles.seite}>
      <section className={styles.einleitung}>
        <p className={styles.eyebrow}>{t("Price database")}</p>
        <h1>{t("Keep unit prices from priced bills for later reviews.")}</h1>
        <p className={styles.lead}>{t("Upload a priced bill or price list once. Its unit prices are used whenever a later review has no matching price.")}</p>
      </section>

      <section className={`${styles.glas} ${eigene.karte}`} aria-labelledby="preise-upload">
        <h2 id="preise-upload">{t("Add prices")}</h2>
        <div className={eigene.wahlen}>
          <DateiWahl
            id="preise-datei"
            label={t("Priced bill or price list")}
            hint={`${PREISLISTE_FORMATE.map((f) => f.slice(1).toUpperCase()).join(", ")} · max. 10 MiB`}
            accept={PREISLISTE_FORMATE.join(",")}
            file={preisDatei}
            disabled={meldung?.art === "laeuft"}
            invalid={meldung?.art === "fehler"}
            chooseLabel={t("Choose file")}
            onChange={(d) => { setPreisDatei(d); void importiere(d, lvDatei); }}
          />
          <DateiWahl
            id="preise-lv"
            label={t("Matching bill (optional)")}
            hint={t("{formats} · gives a D84 offer its item texts", { formats: PREIS_LV_FORMATE.map((f) => f.slice(1).toUpperCase()).join(", ") })}
            accept={PREIS_LV_FORMATE.join(",")}
            file={lvDatei}
            disabled={meldung?.art === "laeuft"}
            chooseLabel={t("Choose file")}
            onChange={(d) => { setLvDatei(d); if (preisDatei) void importiere(preisDatei, d); }}
          />
        </div>
        <div aria-live="polite">
          {meldung && <p className={meldung.art === "fehler" ? eigene.fehler : eigene.hinweis} role={meldung.art === "fehler" ? "alert" : undefined}>{meldung.text}</p>}
        </div>
        {liste && (
          <>
            {liste.warnungen.length > 0 && <ul className={eigene.warnungen}>{liste.warnungen.map((w, i) => <li key={i}>{w}</li>)}</ul>}
            <Tabelle zeilen={zeilen.map((z, i) => ({ schluessel: String(i), item: z.item, unit: z.unit, preis: z.price_per_unit, gueltig: z.gueltig }))} />
            <div>
              <button type="button" className={styles.knopf} disabled={body.length === 0} onClick={() => void speichern()}>
                {t(body.length === 1 ? "Save {n} price to price database" : "Save {n} prices to price database", { n: body.length })}
              </button>
              {body.length < zeilen.length && <p className={eigene.hinweis}>{t("{n} rows skipped (no item, no unit, invalid price or duplicate).", { n: zeilen.length - body.length })}</p>}
            </div>
          </>
        )}
      </section>

      <section className={`${styles.glas} ${eigene.karte}`} aria-labelledby="preise-db">
        <h2 id="preise-db">{t("Current prices")} {db && <span className={eigene.hinweis}>{t("{a} of {b}", { a: gezeigt.length, b: db.length })}</span>}</h2>
        {dbFehler ? (
          <p className={eigene.hinweis} role="note">{dbFehler}</p>
        ) : db === null ? (
          <p className={eigene.hinweis}>{t("Loading …")}</p>
        ) : (
          <>
            <div className={eigene.suche} role="search">
              <label>{t("Item")} <input type="search" value={item} onChange={(e) => setItem(e.target.value)} /></label>
              <label>{t("Unit")} <input type="search" value={unit} onChange={(e) => setUnit(e.target.value)} /></label>
            </div>
            {gezeigt.length === 0 ? <p className={eigene.hinweis}>{t(db.length === 0 ? "The price database is empty." : "No prices match.")}</p>
              : <Tabelle zeilen={gezeigt.map((e) => ({ schluessel: String(e.id), item: e.item, unit: e.unit, preis: e.price_per_unit, gueltig: true }))} />}
          </>
        )}
      </section>
    </div>
  );
}

function Tabelle({ zeilen }: { zeilen: { schluessel: string; item: string; unit: string; preis: number; gueltig: boolean }[] }) {
  const t = useT();
  return (
    <div className={eigene.rahmen}>
      <table className={eigene.tabelle}>
        <thead><tr><th scope="col">{t("Item")}</th><th scope="col">{t("Unit")}</th><th scope="col" className={eigene.rechts}>{t("Price per unit")}</th></tr></thead>
        <tbody>
          {zeilen.map((z) => (
            <tr key={z.schluessel} className={z.gueltig ? undefined : eigene.ungueltig}>
              <td>{z.item || <em>{t("no item")}</em>}{!z.gueltig && <span className={eigene.marke}>{t("not saved")}</span>}</td>
              <td>{z.unit || <em>{t("no unit")}</em>}</td>
              <td className={eigene.rechts}>{Number.isFinite(z.preis) ? euro.format(z.preis) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
