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

// Empty-state display test: /bericht-vorschau?zustand=ohne-befunde
// hides all entries and clearly states this on the page.
function ohneBefunde(bericht: PruefberichtDaten): PruefberichtDaten {
  return { ...bericht, findings: [], kennzahlen: { ...bericht.kennzahlen, findings: 0, kritisch: 0 } };
}

function meldung(fehler: unknown) {
  if (fehler instanceof TypeError) return "Cannot connect to the backend.";
  return fehler instanceof Error ? fehler.message : "Unknown error.";
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
      setZustand({ phase: "fehler", schritt: "Reviewing the BoQ", meldung: meldung(fehler) });
    }
  }, []);

  const lade = useCallback(async () => {
    setZustand({ phase: "beispiele" });
    try {
      const items = await api.examples();
      setBeispiele(items);
      if (items.length === 0) {
        setZustand({ phase: "fehler", schritt: "Loading examples", meldung: "The backend returned no example BoQs." });
        return;
      }
      await pruefe(items[0]);
    } catch (fehler) {
      setZustand({ phase: "fehler", schritt: "Loading examples", meldung: meldung(fehler) });
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
          <p className={styles.kicker}>Preview · synthetic example</p>
          <h1 className={styles.titel}>Review report for a bill of quantities</h1>
          <p className={styles.lead}>
            This page sends a synthetic example BoQ (no partner data) through the review pipeline and shows the result.
            File upload is available on the home page.
          </p>
        </div>
        {beispiele.length > 1 && (
          <label className={styles.auswahl}>
            Example
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
          <strong>Display test:</strong> All entries are hidden to show the empty state. This is not an actual review result.{" "}
          <a href="/bericht-vorschau">Show actual report</a>
        </p>
      )}

      <div aria-live="polite" aria-busy={zustand.phase === "beispiele" || zustand.phase === "pruefen"}>
        {zustand.phase === "beispiele" && <Laden text="Loading example BoQ …" />}
        {zustand.phase === "pruefen" && <Laden text={`Reviewing “${zustand.beispiel.titel}” …`} />}
        {zustand.phase === "fehler" && (
          <div className={styles.fehler} role="alert">
            <h2>Could not create the report</h2>
            <p>Step: {zustand.schritt}. {zustand.meldung}</p>
            <p className={styles.tipp}>
              Is the backend running? Locally, <code>python tools/dev.py</code> starts the UI and backend together.
            </p>
            <button type="button" className={styles.knopf} onClick={() => void lade()}>Try again</button>
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
