"use client";

import { useState } from "react";
import { useEinstellungen, type Einstellungen } from "@/lib/einstellungen";
import { KeySettings } from "@/components/schluessel/KeySettings";
import { Entwickleroptionen } from "./Entwickleroptionen";
import styles from "./einstellungen.module.css";

type Option<K extends keyof Einstellungen> = { wert: Einstellungen[K]; name: string; hinweis?: string };
const SPRACHEN: Option<"sprache">[] = [{ wert: "en", name: "English" }, { wert: "de", name: "Deutsch" }];
const THEMEN: Option<"thema">[] = [
  { wert: "auto", name: "Auto", hinweis: "Light by day, dark from 19:00 to 07:00" },
  { wert: "light", name: "Light" }, { wert: "dark", name: "Dark" },
];
const SEITEN: Option<"seitengroesse">[] = [{ wert: 50, name: "50" }, { wert: 100, name: "100" }, { wert: 250, name: "250" }];
const START: Option<"startReiter">[] = [{ wert: "uebersicht", name: "Overview" }, { wert: "findings", name: "Findings" }, { wert: "positionen", name: "Items" }];
const DICHTEN: Option<"dichte">[] = [
  { wert: "normal", name: "Comfortable" }, { wert: "kompakt", name: "Compact", hinweis: "Smaller text and spacing, more rows on screen" },
];

function Wahl<K extends keyof Einstellungen>({ feld, titel, optionen }: { feld: K; titel: string; optionen: Option<K>[] }) {
  const { e, setze, t } = useEinstellungen();
  return (
    <fieldset className={styles.gruppe}>
      <legend>{t(titel)}</legend>
      <div className={styles.segmente}>
        {optionen.map((o) => (
          <button key={String(o.wert)} type="button" aria-pressed={e[feld] === o.wert}
            className={`${styles.segment} ${e[feld] === o.wert ? styles.aktiv : ""}`}
            onClick={() => setze({ [feld]: o.wert } as Partial<Einstellungen>)}>
            {["English", "Deutsch", "50", "100", "250"].includes(o.name) ? o.name : t(o.name)}
          </button>
        ))}
      </div>
      {optionen.find((o) => o.wert === e[feld])?.hinweis && <p className={styles.hinweis}>{t(optionen.find((o) => o.wert === e[feld])!.hinweis!)}</p>}
    </fieldset>
  );
}

/** Removes every key this app keeps in the browser for one purpose. Returns how many were removed. */
function entferne(praefix: string): number {
  try {
    const schluessel = Object.keys(window.localStorage).filter((k) => k.startsWith(praefix));
    schluessel.forEach((k) => window.localStorage.removeItem(k));
    return schluessel.length;
  } catch {
    return 0;
  }
}

export function EinstellungenSeite() {
  const { t } = useEinstellungen();
  const [meldung, setMeldung] = useState("");
  return (
    <main className={styles.seite}>
      <header>
        <p className={styles.kicker}>{t("Settings")}</p>
        <h1 className={styles.titel}>{t("Make the assistant work your way")}</h1>
      </header>
      <section className={styles.karte}>
        <Wahl feld="sprache" titel="Language" optionen={SPRACHEN} />
        <Wahl feld="thema" titel="Theme" optionen={THEMEN} />
        <Wahl feld="dichte" titel="Density" optionen={DICHTEN} />
      </section>
      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("Review report")}</h2>
        <Wahl feld="startReiter" titel="Report opens on" optionen={START} />
        <Wahl feld="seitengroesse" titel="Rows per page" optionen={SEITEN} />
      </section>
      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("API token")}</h2>
        <p className={styles.hinweis}>{t("Enter your Claude API key here. It is sent to the backend once, never shown again, and never logged.")}</p>
        <KeySettings embedded />
      </section>
      <Entwickleroptionen />
      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("Data in this browser")}</h2>
        <p className={styles.hinweis}>{t("Nothing here is sent anywhere. Clearing cannot be undone.")}</p>
        <div className={styles.knoepfe}>
          <button type="button" className={styles.knopf} onClick={() => setMeldung(t("{n} saved reviews cleared.", { n: entferne("lv-bewertung") }))}>
            {t("Clear review statuses and comments")}
          </button>
        </div>
        {meldung && <p className={styles.meldung} role="status">{meldung}</p>}
      </section>
    </main>
  );
}
