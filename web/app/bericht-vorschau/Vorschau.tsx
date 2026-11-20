"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Example, type Pruefbericht as PruefberichtDaten } from "@/lib/api";
import { Pruefbericht } from "@/components/Pruefbericht";
import styles from "./vorschau.module.css";

type Zustand =
  | { phase: "beispiele" }
  | { phase: "pruefen"; beispiel: Example }
  | { phase: "fertig"; beispiel: Example; bericht: PruefberichtDaten }
  | { phase: "fehler"; schritt: string; meldung: string };

// Darstellungstest des leeren Zustands: /bericht-vorschau?zustand=ohne-befunde
// blendet alle Einträge aus und sagt das auf der Seite deutlich.
function ohneBefunde(bericht: PruefberichtDaten): PruefberichtDaten {
  return { ...bericht, findings: [], kennzahlen: { ...bericht.kennzahlen, findings: 0, kritisch: 0 } };
}

function meldung(fehler: unknown) {
  if (fehler instanceof TypeError) return "Keine Verbindung zum Backend.";
  return fehler instanceof Error ? fehler.message : "Unbekannter Fehler.";
}

export function Vorschau() {
  const [zustand, setZustand] = useState<Zustand>({ phase: "beispiele" });
  const [beispiele, setBeispiele] = useState<Example[]>([]);
  const [leerTest, setLeerTest] = useState(false);

  const pruefe = useCallback(async (beispiel: Example) => {
    setZustand({ phase: "pruefen", beispiel });
    try {
      const bericht = await api.pruefen(beispiel.lv);
      setZustand({ phase: "fertig", beispiel, bericht });
    } catch (fehler) {
      setZustand({ phase: "fehler", schritt: "Prüfung des LV", meldung: meldung(fehler) });
    }
  }, []);

  const lade = useCallback(async () => {
    setZustand({ phase: "beispiele" });
    try {
      const items = await api.examples();
      setBeispiele(items);
      if (items.length === 0) {
        setZustand({ phase: "fehler", schritt: "Laden der Beispiele", meldung: "Das Backend liefert keine Beispiel-LVs." });
        return;
      }
      await pruefe(items[0]);
    } catch (fehler) {
      setZustand({ phase: "fehler", schritt: "Laden der Beispiele", meldung: meldung(fehler) });
    }
  }, [pruefe]);

  useEffect(() => {
    setLeerTest(new URLSearchParams(window.location.search).get("zustand") === "ohne-befunde");
    void lade();
  }, [lade]);

  const aktivesBeispiel = zustand.phase === "pruefen" || zustand.phase === "fertig" ? zustand.beispiel : null;

  return (
    <main className={styles.seite}>
      <header className={styles.kopf}>
        <div>
          <p className={styles.kicker}>Vorschau · synthetisches Beispiel</p>
          <h1 className={styles.titel}>Prüfbericht für ein Leistungsverzeichnis</h1>
          <p className={styles.lead}>
            Diese Seite schickt ein synthetisches Beispiel-LV (keine Partnerdaten) durch die Prüfpipeline und zeigt das Ergebnis.
            Der Datei-Upload folgt auf der Startseite.
          </p>
        </div>
        {beispiele.length > 1 && (
          <label className={styles.auswahl}>
            Beispiel
            <select
              value={aktivesBeispiel?.id ?? ""}
              disabled={zustand.phase === "beispiele" || zustand.phase === "pruefen"}
              onChange={(event) => {
                const beispiel = beispiele.find((b) => b.id === event.target.value);
                if (beispiel) void pruefe(beispiel);
              }}
            >
              {beispiele.map((b) => <option key={b.id} value={b.id}>{b.titel}</option>)}
            </select>
          </label>
        )}
      </header>

      {leerTest && (
        <p className={styles.testHinweis} role="note">
          <strong>Darstellungstest:</strong> Alle Einträge sind ausgeblendet, um den Zustand ohne Befunde zu zeigen. Das ist kein echtes Prüfergebnis.{" "}
          <a href="/bericht-vorschau">Echten Bericht anzeigen</a>
        </p>
      )}

      <div aria-live="polite" aria-busy={zustand.phase === "beispiele" || zustand.phase === "pruefen"}>
        {zustand.phase === "beispiele" && <Laden text="Beispiel-LV wird geladen …" />}
        {zustand.phase === "pruefen" && <Laden text={`„${zustand.beispiel.titel}“ wird geprüft …`} />}
        {zustand.phase === "fehler" && (
          <div className={styles.fehler} role="alert">
            <h2>Der Bericht konnte nicht erstellt werden</h2>
            <p>Schritt: {zustand.schritt}. {zustand.meldung}</p>
            <p className={styles.tipp}>
              Läuft das Backend? Lokal startet <code>python tools/dev.py</code> Oberfläche und Backend zusammen.
            </p>
            <button type="button" className={styles.knopf} onClick={() => void lade()}>Erneut versuchen</button>
          </div>
        )}
      </div>

      {zustand.phase === "fertig" && (
        <Pruefbericht
          key={`${zustand.beispiel.id}-${leerTest}`}
          bericht={leerTest ? ohneBefunde(zustand.bericht) : zustand.bericht}
        />
      )}
    </main>
  );
}

function Laden({ text }: { text: string }) {
  return (
    <div className={styles.laden}>
      <span className={styles.kreisel} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
