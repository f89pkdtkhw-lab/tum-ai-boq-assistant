"use client";

import { type ChangeEvent, type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { api, type Health, type LV, type Pruefbericht as PruefberichtDaten } from "@/lib/api";
import { Pruefbericht } from "@/components/Pruefbericht";
import styles from "./lv-upload.module.css";

// Same limit as MAX_UPLOAD_BYTES in api/app/main.py; checked locally so oversized files never leave the browser.
const MAX_BYTES = 10 * 1024 * 1024;
const GRENZNAH_BYTES = 9.5 * 1024 * 1024;
// Same formats as the dispatcher in api/app/lv/importer.py. Whether a format is already
// implemented is decided by the backend (HTTP 501), never by this page.
const FORMATS: { endung: string; name: string }[] = [
  { endung: ".json", name: "LV-JSON" },
  { endung: ".x83", name: "GAEB X83" },
  { endung: ".x84", name: "GAEB X84" },
  { endung: ".xlsx", name: "Excel" },
  { endung: ".pdf", name: "PDF" },
];
const ACCEPT = FORMATS.map((f) => f.endung).join(",");

type SchrittId = "datei" | "import" | "pruefung";
type SchrittStatus = "wartet" | "laeuft" | "fertig" | "fehler" | "entfaellt";
type Schritt = { status: SchrittStatus; text: string };
type Schritte = Record<SchrittId, Schritt>;
type Lauf =
  | { art: "datei"; datei: File }
  | { art: "beispiel" };
type Ergebnis =
  | { phase: "leer" }
  | { phase: "laeuft"; lauf: Lauf; schritte: Schritte }
  | { phase: "fertig"; lauf: Lauf; schritte: Schritte; lv: LV; bericht: PruefberichtDaten; nummer: number }
  | { phase: "fehler"; lauf: Lauf; schritte: Schritte; titel: string; meldung: string; tipp: string | null };

const SCHRITT_NAMEN: Record<SchrittId, string> = {
  datei: "Upload",
  import: "Import",
  pruefung: "Review",
};
const STATUS_NAMEN: Record<SchrittStatus, string> = {
  wartet: "waiting",
  laeuft: "running",
  fertig: "done",
  fehler: "failed",
  entfaellt: "skipped",
};
const BACKEND_TIPP = "Locally, python tools/dev.py starts the UI (port 3000) and backend (port 8000) together.";
const zahl = new Intl.NumberFormat("en-GB");

function groesse(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${zahl.format(Math.round(bytes / 1024))} KiB`;
  return `${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MiB`;
}

function endung(name: string) {
  const punkt = name.lastIndexOf(".");
  return punkt < 0 ? "" : name.slice(punkt).toLowerCase();
}

function anzahl(n: number, einzahl: string, mehrzahl: string) {
  return `${zahl.format(n)} ${n === 1 ? einzahl : mehrzahl}`;
}

/** Local checks before anything is sent; returns a readable reason or null. */
function lokalerFehler(datei: File): string | null {
  if (!FORMATS.some((f) => f.endung === endung(datei.name))) {
    return `“${datei.name}” has an unsupported format. Allowed formats: ${FORMATS.map((f) => f.endung.slice(1).toUpperCase()).join(", ")}.`;
  }
  if (datei.size === 0) return "The file is empty.";
  if (datei.size > MAX_BYTES) {
    return `The file is ${groesse(datei.size)}. The maximum is 10 MiB. It was not uploaded.`;
  }
  return null;
}

function startSchritte(lauf: Lauf): Schritte {
  if (lauf.art === "beispiel") {
    return {
      datei: { status: "entfaellt", text: "No upload: the synthetic example is already on the server." },
      import: { status: "laeuft", text: "Loading the example BoQ from the server …" },
      pruefung: { status: "wartet", text: "Starts after import." },
    };
  }
  return {
    datei: { status: "laeuft", text: `Uploading ${lauf.datei.name} (${groesse(lauf.datei.size)}) …` },
    import: { status: "laeuft", text: "The server imports the file in the same request …" },
    pruefung: { status: "wartet", text: "Starts after import." },
  };
}

function fehlerText(fehler: unknown) {
  if (fehler instanceof TypeError) return "Cannot connect to the backend.";
  return fehler instanceof Error && fehler.message ? fehler.message : "Unknown error.";
}

async function backendErreichbar() {
  try {
    await api.health();
    return true;
  } catch {
    return false;
  }
}

export function LvUpload() {
  const [health, setHealth] = useState<Health | null | "offline">(null);
  const [datei, setDatei] = useState<File | null>(null);
  const [dateiFehler, setDateiFehler] = useState("");
  const [ziehen, setZiehen] = useState(false);
  const [ergebnis, setErgebnis] = useState<Ergebnis>({ phase: "leer" });
  const laufNummer = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const meldungRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth("offline"));
  }, []);

  useEffect(() => {
    // Move keyboard and screen reader focus to the outcome once a run has ended.
    if (ergebnis.phase === "fehler" || ergebnis.phase === "fertig") meldungRef.current?.focus();
  }, [ergebnis.phase]);

  const busy = ergebnis.phase === "laeuft";

  function waehleDatei(neu: File | null) {
    // A new file invalidates every older result, including one that is still loading.
    laufNummer.current += 1;
    setErgebnis({ phase: "leer" });
    setDatei(neu);
    setDateiFehler(neu ? lokalerFehler(neu) ?? "" : "");
  }

  function aufAuswahl(event: ChangeEvent<HTMLInputElement>) {
    waehleDatei(event.target.files?.[0] ?? null);
  }

  function aufAblegen(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setZiehen(false);
    if (busy) return;
    const neu = event.dataTransfer.files?.[0];
    if (!neu) return;
    if (inputRef.current) inputRef.current.value = "";
    waehleDatei(neu);
  }

  async function starte(lauf: Lauf) {
    const nummer = ++laufNummer.current;
    const aktuell = () => nummer === laufNummer.current;
    let schritte = startSchritte(lauf);
    setErgebnis({ phase: "laeuft", lauf, schritte });

    const scheitern = async (schritt: SchrittId, titel: string, fehler: unknown, tipp: string | null) => {
      let meldung = fehlerText(fehler);
      let hinweis = tipp;
      if (!(await backendErreichbar())) {
        meldung = "The backend is unreachable.";
        hinweis = BACKEND_TIPP;
        setHealth("offline");
      }
      if (!aktuell()) return;
      schritte = { ...schritte, [schritt]: { status: "fehler", text: meldung } };
      if (schritt === "import" && lauf.art === "datei") {
        schritte.datei = { status: "fertig", text: `${lauf.datei.name} (${groesse(lauf.datei.size)}) uploaded.` };
      }
      if (schritte.pruefung.status === "wartet") schritte.pruefung = { status: "wartet", text: "Not started." };
      setErgebnis({ phase: "fehler", lauf, schritte, titel, meldung, tipp: hinweis });
    };

    let lv: LV;
    try {
      if (lauf.art === "datei") {
        lv = await api.importiere(lauf.datei);
      } else {
        const beispiele = await api.examples();
        if (beispiele.length === 0) throw new Error("The backend returned no example BoQ.");
        lv = beispiele[0].lv;
      }
    } catch (fehler) {
      let tipp: string | null = null;
      if (lauf.art === "datei" && lauf.datei.size > GRENZNAH_BYTES) {
        // The dev/start proxy in front of the backend may cut request bodies near the 10 MiB limit.
        tipp = "The file is close to the 10 MiB limit. Please try a smaller file.";
      } else if (lauf.art === "datei" && endung(lauf.datei.name) !== ".json") {
        tipp = "Use a BoQ JSON file or the synthetic example to try the flow immediately.";
      }
      await scheitern("import", "Import failed", fehler, tipp);
      return;
    }
    if (!aktuell()) return;

    const quelle = lv.quelle ? ` from ${lv.quelle}` : "";
    schritte = {
      datei: lauf.art === "datei"
        ? { status: "fertig", text: `${lauf.datei.name} (${groesse(lauf.datei.size)}) uploaded.` }
        : schritte.datei,
      import: { status: "fertig", text: `${anzahl(lv.positionen.length, "Item", "Items")} detected${quelle}.` },
      pruefung: { status: "laeuft", text: "Running review rules …" },
    };
    setErgebnis({ phase: "laeuft", lauf, schritte });

    let bericht: PruefberichtDaten;
    try {
      bericht = await api.pruefen(lv);
    } catch (fehler) {
      await scheitern("pruefung", "Review failed", fehler, null);
      return;
    }
    if (!aktuell()) return;
    schritte = {
      ...schritte,
      pruefung: { status: "fertig", text: `${anzahl(bericht.findings.length, "Entry", "Entries")} in the report.` },
    };
    setErgebnis({ phase: "fertig", lauf, schritte, lv, bericht, nummer });
    if (health === "offline") api.health().then(setHealth).catch(() => {});
  }

  function absenden(event: FormEvent) {
    event.preventDefault();
    if (!datei || dateiFehler || busy) return;
    void starte({ art: "datei", datei });
  }

  function zuruecksetzen() {
    if (inputRef.current) inputRef.current.value = "";
    waehleDatei(null);
    inputRef.current?.focus();
  }

  const status = health === null
    ? { klasse: styles.statusWartet, text: "Checking backend …" }
    : health === "offline"
      ? { klasse: styles.statusOffline, text: "Backend offline" }
      : { klasse: health.mock ? styles.statusMock : styles.statusLive, text: `${health.provider} · ${health.model}` };

  return (
    <main className={styles.seite}>
      <header className={styles.kopf}>
        <span className={styles.marke}>◆ BoQ Review Assistant</span>
        <span className={`${styles.status} ${status.klasse}`}>{status.text}</span>
      </header>

      <section className={styles.einleitung} aria-labelledby="upload-titel">
        <p className={styles.kicker}>Review a bill of quantities</p>
        <h1 id="upload-titel" className={styles.titel}>Find errors, risks and potential change orders in your BoQ before submitting a bid.</h1>
        <p className={styles.lead}>
          Upload a BoQ file. The assistant imports and checks its items, then shows each finding with its item number and source.
        </p>
      </section>

      <form className={styles.karte} onSubmit={absenden} aria-describedby="upload-regeln">
        <label
          className={`${styles.ablage} ${ziehen ? styles.ablageAktiv : ""} ${busy ? styles.ablageGesperrt : ""}`}
          onDragOver={(event) => { event.preventDefault(); if (!busy) setZiehen(true); }}
          onDragLeave={() => setZiehen(false)}
          onDrop={aufAblegen}
        >
          <input
            ref={inputRef}
            className={styles.dateiEingabe}
            type="file"
            name="datei"
            accept={ACCEPT}
            onChange={aufAuswahl}
            disabled={busy}
          />
          <span className={styles.ablageTitel}>{datei ? datei.name : "Choose a BoQ file"}</span>
          <span className={styles.ablageText}>
            {datei ? `${groesse(datei.size)} · choose another file or drag it here` : "Click, press Enter or drag a file here"}
          </span>
        </label>
        <p id="upload-regeln" className={styles.regeln}>
          Formats: {FORMATS.map((f) => `${f.name} (${f.endung})`).join(", ")}. Maximum 10 MiB. The file is read only for this review and is not stored.
        </p>
        {dateiFehler && <p className={styles.dateiFehler} role="alert">{dateiFehler}</p>}
        <div className={styles.aktionen}>
          <button type="submit" className={styles.knopf} disabled={!datei || !!dateiFehler || busy}>
            {busy && ergebnis.lauf.art === "datei" ? "Reviewing …" : "Review file"}
          </button>
          <button type="button" className={styles.knopfZweit} disabled={busy} onClick={() => { waehleDatei(null); if (inputRef.current) inputRef.current.value = ""; void starte({ art: "beispiel" }); }}>
            {busy && ergebnis.lauf.art === "beispiel" ? "Reviewing example …" : "Review synthetic example"}
          </button>
          {datei && !busy && (
            <button type="button" className={styles.knopfLeise} onClick={zuruecksetzen}>Clear selection</button>
          )}
        </div>
        <p className={styles.regeln}>The example is a synthetic structural works BoQ without partner data and requires no upload.</p>
      </form>

      {ergebnis.phase !== "leer" && (
        <section className={styles.karte} aria-labelledby="ablauf-titel" aria-busy={busy}>
          <h2 id="ablauf-titel" className={styles.abschnitt}>
            {ergebnis.lauf.art === "datei" ? `Progress for ${ergebnis.lauf.datei.name}` : "Progress for the synthetic example"}
          </h2>
          <ol className={styles.schritte}>
            {(Object.keys(SCHRITT_NAMEN) as SchrittId[]).map((id) => {
              const schritt = ergebnis.schritte[id];
              return (
                <li key={id} className={`${styles.schritt} ${styles[`schritt_${schritt.status}`]}`}>
                  <span className={styles.symbol} aria-hidden="true" />
                  <span className={styles.schrittName}>{SCHRITT_NAMEN[id]}</span>
                  <span className={styles.schrittStatus}>{STATUS_NAMEN[schritt.status]}</span>
                  <span className={styles.schrittText}>{schritt.text}</span>
                </li>
              );
            })}
          </ol>
          <div aria-live="polite" className={styles.ansage}>
            {busy && `${SCHRITT_NAMEN[ergebnis.schritte.pruefung.status === "laeuft" ? "pruefung" : "import"]} is running.`}
          </div>
          {ergebnis.phase === "fehler" && (
            <div ref={meldungRef} tabIndex={-1} className={styles.fehler} role="alert">
              <h3>{ergebnis.titel}</h3>
              <p>{ergebnis.meldung}</p>
              {ergebnis.tipp && <p className={styles.tipp}>{ergebnis.tipp}</p>}
              <div className={styles.aktionen}>
                <button type="button" className={styles.knopf} onClick={() => void starte(ergebnis.lauf)}>Try again</button>
                {ergebnis.lauf.art === "datei" && (
                  <button type="button" className={styles.knopfZweit} onClick={zuruecksetzen}>Choose another file</button>
                )}
              </div>
            </div>
          )}
          {ergebnis.phase === "fertig" && (
            <div ref={meldungRef} tabIndex={-1} className={styles.erfolg}>
              <p>
                <strong>{anzahl(ergebnis.lv.positionen.length, "Item", "Items")}</strong> imported and reviewed. The review report is below.
              </p>
              <button type="button" className={styles.knopfZweit} onClick={() => void starte(ergebnis.lauf)}>Review again</button>
            </div>
          )}
        </section>
      )}

      {ergebnis.phase === "fertig" && (
        <Pruefbericht key={ergebnis.nummer} bericht={ergebnis.bericht} />
      )}
    </main>
  );
}
