"use client";

import { type ChangeEvent, type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { api, type AnalyseStatus, type Example, type Health, type LV, type Preisliste, type Pruefbericht as PruefberichtDaten, type Regelwerk } from "@/lib/api";
import { analyseAnfrage, importFehlerText, regelwerkText, routeFehlt } from "@/lib/regelwerk";
import { useT } from "@/lib/einstellungen";
import { lesePreisliste, preislisteText, speicherePreisliste } from "@/lib/preisliste";
import { Icon } from "./icon/Icon";
import { Bericht } from "@/components/bericht/Bericht";
import { bietetOffline, ladeOfflineBericht } from "@/lib/offline";
import { fuehreAnalyseAus } from "@/lib/analyse-job";
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
  { endung: ".d83", name: "GAEB 90 D83" },
  { endung: ".d86", name: "GAEB 90 D86" },
  { endung: ".xlsx", name: "Excel" },
  { endung: ".pdf", name: "PDF" },
];
const ACCEPT = FORMATS.map((f) => f.endung).join(",");

type SchrittId = "datei" | "import" | "pruefung";
type SchrittStatus = "wartet" | "laeuft" | "fertig" | "fehler" | "entfaellt";
type Schritt = { status: SchrittStatus; text: string };
type Schritte = Record<SchrittId, Schritt>;
type Lauf =
  // Optional attachments go to the backend with the bill (POST /api/lv/analyse: regulation document B3, price list D4/#158).
  | { art: "datei"; datei: File; regelwerk?: File | null; preisliste?: File | null }
  | { art: "beispiel"; id: string | null; titel: string }
  // A report restored after switching pages; "Review again" re-runs the review on its LV.
  | { art: "lv"; titel: string; lv: LV };
type Ergebnis =
  | { phase: "leer" }
  // `stand`: live status of the background analysis job (#165), drawn as the progress bar.
  | { phase: "laeuft"; lauf: Lauf; schritte: Schritte; stand?: AnalyseStatus | null }
  | { phase: "fertig"; lauf: Lauf; schritte: Schritte; lv: LV; bericht: PruefberichtDaten; nummer: number; offline: boolean; hinweise?: string[] }
  | { phase: "fehler"; lauf: Lauf; schritte: Schritte; titel: string; meldung: string; tipp: string | null; offline: boolean; stand?: AnalyseStatus | null };

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
  if (lauf.art !== "datei") {
    return {
      datei: { status: "entfaellt", text: `No upload: “${lauf.titel}” is already on the server.` },
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

// The open report survives page switches within this tab (sessionStorage, never sent anywhere).
const AKTUELL = "lv-aktuell-v1";
type Aktuell = { titel: string; beispielId: string | null; bericht: PruefberichtDaten };
function speichereAktuell(titel: string, beispielId: string | null, bericht: PruefberichtDaten) {
  try { window.sessionStorage.setItem(AKTUELL, JSON.stringify({ titel, beispielId, bericht })); } catch { /* too large or blocked: start screen next time */ }
}
function ladeAktuell(): Aktuell | null {
  try {
    const roh = JSON.parse(window.sessionStorage.getItem(AKTUELL) ?? "null");
    return roh && typeof roh.titel === "string" && roh.bericht?.lv ? roh : null;
  } catch {
    return null;
  }
}
function vergiss() {
  try { window.sessionStorage.removeItem(AKTUELL); } catch { /* nothing stored */ }
}

type Rolle = "lv" | "regel" | "preise";
/** Guesses a file's role from its name and type; the user can change it in the list. */
function rolleRaten(datei: File, hatLv: boolean): Rolle {
  const n = datei.name.toLowerCase();
  if (/preis|price|kosten|tarif/.test(n) || n.endsWith(".csv")) return "preise";
  if (/\.(x8[1-6]|d8[1-6]|xlsx|xls)$/.test(n)) return "lv";
  if (/\.(docx|txt)$/.test(n) || /norm|regel|spezif|spec|anforder|vorgabe|din/.test(n)) return "regel";
  return hatLv ? "regel" : "lv";
}

async function backendErreichbar() {
  try {
    await api.health();
    return true;
  } catch {
    return false;
  }
}

/** Progress bar of the background analysis (#165): percent, current step and the finished steps. */
function AnalyseFortschritt({ stand, t }: { stand: AnalyseStatus; t: ReturnType<typeof useT> }) {
  const schritt = Math.max(1, Math.min(stand.schritt, stand.schritte_gesamt));
  return (
    <div className={`${styles.fortschritt} ${stand.status === "fehler" ? styles.fortschrittGestoppt : ""}`}>
      <div className={styles.fortschrittKopf}>
        <span>{t("Step {n} of {total}", { n: schritt, total: stand.schritte_gesamt })}</span>
        <span className={styles.prozent}>{stand.prozent} %</span>
      </div>
      <div className={styles.balken} role="progressbar" aria-label={t("Analysis progress")}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={stand.prozent} aria-valuetext={stand.meldung}>
        <span className={styles.balkenFuellung} style={{ width: `${stand.prozent}%` }} />
      </div>
      <p className={styles.fortschrittText}>{stand.meldung}</p>
      {stand.fertige_schritte.length > 0 && (
        <ol className={styles.fertigListe} aria-label={t("Finished steps")}>
          {stand.fertige_schritte.map((s) => (
            <li key={s.schritt}>
              <span className={styles.haken} aria-hidden="true">✓</span>
              <span>{s.meldung}</span>
              <small>{zahl.format(Math.round(s.sekunden * 10) / 10)} s</small>
            </li>
          ))}
        </ol>
      )}
      {stand.fehler.length > 0 && (
        <ul className={styles.fortschrittFehler} role="note">
          {stand.fehler.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
    </div>
  );
}

export function LvUpload() {
  const [health, setHealth] = useState<Health | null | "offline">(null);
  const [datei, setDatei] = useState<File | null>(null);
  // Optional regulation/specification document (team spec, UI step 1). Not analysed yet: no backend service reads it.
  const [regelwerk, setRegelwerk] = useState<File | null>(null);
  const [dateien, setDateien] = useState<{ datei: File; rolle: Rolle }[]>([]);
  const [dateiFehler, setDateiFehler] = useState("");
  const [ziehen, setZiehen] = useState(false);
  const [ergebnis, setErgebnis] = useState<Ergebnis>({ phase: "leer" });
  const laufNummer = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const meldungRef = useRef<HTMLDivElement>(null);

  const [beispiele, setBeispiele] = useState<Example[]>([]);
  const t = useT();

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth("offline"));
    // Coming back from another page: show the report that was open instead of the empty start screen.
    const offen = new URLSearchParams(window.location.search).get("beispiel") ? null : ladeAktuell();
    if (offen) {
      const lauf: Lauf = offen.beispielId ? { art: "beispiel", id: offen.beispielId, titel: offen.titel } : { art: "lv", titel: offen.titel, lv: offen.bericht.lv };
      const fertig: Schritt = { status: "fertig", text: "Restored from this browser session." };
      setErgebnis({ phase: "fertig", lauf, lv: offen.bericht.lv, bericht: offen.bericht, nummer: ++laufNummer.current, offline: false,
        schritte: { datei: fertig, import: fertig, pruefung: fertig } });
    }
    api.examples().then((liste) => {
      setBeispiele(liste);
      // The dashboard opens a past example again with /?beispiel=<id>.
      const id = new URLSearchParams(window.location.search).get("beispiel");
      const treffer = liste.find((b) => b.id === id);
      if (treffer) void starte({ art: "beispiel", id: treffer.id, titel: treffer.titel });
    }).catch(() => {});
    // starte is stable enough here: it only runs once, after the example list arrived.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Current files with their role; the bill drives the review, the others are attached (see Rolle).
  function setzeDateien(liste: { datei: File; rolle: Rolle }[]) {
    setDateien(liste);
    waehleDatei(liste.find((d) => d.rolle === "lv")?.datei ?? null);
    setRegelwerk(liste.find((d) => d.rolle === "regel")?.datei ?? null);
  }
  function hinzufuegen(neu: File[]) {
    const liste = [...dateien];
    for (const f of neu) liste.push({ datei: f, rolle: rolleRaten(f, liste.some((d) => d.rolle === "lv")) });
    setzeDateien(liste);
  }

  function aufAuswahl(event: ChangeEvent<HTMLInputElement>) {
    hinzufuegen([...(event.target.files ?? [])]);
    event.target.value = "";
  }

  function aufAblegen(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setZiehen(false);
    if (busy) return;
    hinzufuegen([...(event.dataTransfer.files ?? [])]);
  }

  async function starte(lauf: Lauf) {
    const nummer = ++laufNummer.current;
    const aktuell = () => nummer === laufNummer.current;
    let schritte = startSchritte(lauf);
    setErgebnis({ phase: "laeuft", lauf, schritte });

    const scheitern = async (schritt: SchrittId, titel: string, fehler: unknown, tipp: string | null, stand: AnalyseStatus | null = null) => {
      let meldung = fehlerText(fehler);
      let hinweis = tipp;
      const erreichbar = await backendErreichbar();
      if (!erreichbar) {
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
      setErgebnis({ phase: "fehler", lauf, schritte, titel, meldung, tipp: hinweis, offline: bietetOffline(fehler, erreichbar), stand });
    };

    let lv: LV;
    try {
      if (lauf.art === "datei") {
        lv = await api.importiere(lauf.datei);
      } else if (lauf.art === "lv") {
        lv = lauf.lv;
      } else {
        const liste = await api.examples();
        const beispiel = liste.find((b) => b.id === lauf.id) ?? liste[0];
        if (!beispiel) throw new Error("The backend returned no example BoQ.");
        lv = beispiel.lv;
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

    // Attachments (main: #102 regulation document, #115/#158 price list): imported by the backend, then one combined analysis.
    // An attachment the backend cannot read never blocks the review; it is named in the result bar instead.
    const hinweise: string[] = [];
    let regelwerkDaten: Regelwerk | null = null;
    let preislisteDaten: Preisliste | null = null;
    if (lauf.art === "datei" && (lauf.regelwerk || lauf.preisliste)) {
      schritte = { ...schritte, pruefung: { status: "laeuft", text: "Importing the attachments …" } };
      setErgebnis({ phase: "laeuft", lauf, schritte });
      const texte: string[] = [];
      for (const [art, anhang, laden] of [
        ["Regulation document", lauf.regelwerk, async (d: File) => { regelwerkDaten = await api.importiereRegelwerk(d); texte.push(regelwerkText(regelwerkDaten)); }],
        ["Price list", lauf.preisliste, async (d: File) => { preislisteDaten = await api.importierePreisliste(d); texte.push(preislisteText(preislisteDaten)); }],
      ] as const) {
        if (!anhang) continue;
        try {
          await laden(anhang);
        } catch (fehler) {
          hinweise.push(routeFehlt(fehler) ? `${art}: this backend cannot import it yet, so the review continues without it.` : importFehlerText(art, anhang.name, fehler));
        }
        if (!aktuell()) return;
      }
      if (texte.length > 0) hinweise.unshift(texte.join(" · "));
      schritte = { ...schritte, pruefung: { status: "laeuft", text: "Analysing the bill with its attachments …" } };
      setErgebnis({ phase: "laeuft", lauf, schritte });
    }

    let bericht: PruefberichtDaten;
    const job: { stand: AnalyseStatus | null } = { stand: null };
    try {
      const anfrage = analyseAnfrage(lv, regelwerkDaten, preislisteDaten);
      const synchron = () => anfrage === null ? api.pruefen(lv) : api.analyse(anfrage).catch((fehler) => {
        if (!routeFehlt(fehler)) throw fehler;
        hinweise.push("This backend has no combined analysis yet: the bill was reviewed without its attachments.");
        return api.pruefen(lv);
      });
      // #165: background job with progress; same pipeline as before (bill only = /api/lv/pruefen via nur_pruefen).
      try {
        const ende = await fuehreAnalyseAus(api, anfrage ?? { lv, regelwerk: null, preisliste: null, nur_pruefen: true }, {
          aktiv: aktuell,
          aufStand: (stand) => {
            job.stand = stand;
            schritte = { ...schritte, pruefung: { status: "laeuft", text: stand.meldung } };
            setErgebnis({ phase: "laeuft", lauf, schritte, stand });
          },
        });
        if (ende === null) return;
        bericht = ende.bericht;
        hinweise.push(...ende.stand.fehler);
      } catch (fehler) {
        if (job.stand || !routeFehlt(fehler)) throw fehler;
        bericht = await synchron(); // older backend without the job routes: one synchronous request as before
      }
    } catch (fehler) {
      await scheitern("pruefung", "Review failed", fehler, null, job.stand);
      return;
    }
    if (!aktuell()) return;
    schritte = {
      ...schritte,
      pruefung: { status: "fertig", text: `${anzahl(bericht.findings.length, "Entry", "Entries")} in the report.` },
    };
    setErgebnis({ phase: "fertig", lauf, schritte, lv, bericht, nummer, offline: false, hinweise });
    speichereAktuell(lauf.art === "datei" ? lauf.datei.name : lauf.titel, lauf.art === "beispiel" ? lauf.id : null, bericht);
    if (health === "offline") api.health().then(setHealth).catch(() => {});
  }

  async function zeigeOffline(lauf: Lauf, schritte: Schritte) {
    const nummer = ++laufNummer.current;
    let bericht: PruefberichtDaten;
    try {
      bericht = await ladeOfflineBericht();
    } catch (fehler) {
      if (nummer !== laufNummer.current) return;
      const meldung = fehlerText(fehler);
      setErgebnis({ phase: "fehler", lauf, schritte, titel: "Offline example unavailable", meldung, tipp: BACKEND_TIPP, offline: false });
      return;
    }
    if (nummer !== laufNummer.current) return;
    const text = "Offline example: saved report, not a live analysis.";
    setErgebnis({
      phase: "fertig", lauf, lv: bericht.lv, bericht, nummer, offline: true,
      schritte: { ...schritte, pruefung: { status: "fertig", text } },
    });
  }

  async function absenden(event: FormEvent) {
    event.preventDefault();
    if (!datei || dateiFehler || busy) return;
    // A price list goes into the (browser) price database first, so the price report can use it.
    const preisDatei = dateien.find((d) => d.rolle === "preise")?.datei;
    if (preisDatei) { try { speicherePreisliste(lesePreisliste(await preisDatei.text())); } catch { /* not readable: review runs without it */ } }
    void starte({ art: "datei", datei, regelwerk, preisliste: preisDatei ?? null });
  }

  function zuruecksetzen() {
    vergiss();
    setDateien([]);
    setRegelwerk(null);
    if (inputRef.current) inputRef.current.value = "";
    waehleDatei(null);
    inputRef.current?.focus();
  }

  const status = health === null
    ? { klasse: styles.statusWartet, text: t("Checking backend …") }
    : health === "offline"
      ? { klasse: styles.statusOffline, text: t("Backend offline") }
      : { klasse: health.mock ? styles.statusMock : styles.statusLive, text: `${health.provider} · ${health.model}` };

  return (
    <main className={styles.seite}>
      <header className={styles.kopf}>
        <span className={styles.marke}>{t("Upload & report")}</span>
        <span className={`${styles.status} ${status.klasse}`}>{status.text}</span>
      </header>

      {ergebnis.phase === "leer" && (<>
      {/* Start screen from the team sketch: one upload button, the list of current files, Evaluate. */}
      <form className={styles.start} onSubmit={absenden} aria-describedby="upload-regeln"
        onDragOver={(e) => { e.preventDefault(); setZiehen(true); }} onDragLeave={() => setZiehen(false)} onDrop={aufAblegen}>
        <h1 className={styles.startTitel}>{t("New evaluation")}</h1>
        <label className={`${styles.hochladen} ${ziehen ? styles.ablageAktiv : ""}`}>
          <input ref={inputRef} className={styles.dateiEingabe} type="file" multiple accept={`${ACCEPT},.csv,.docx,.txt,.md,.x86,.d84`} onChange={aufAuswahl} disabled={busy} />
          <Icon name="upload" size={22} /> {t("Upload files")}
        </label>
        <p id="upload-regeln" className={styles.regeln}>{t("Bill (GAEB, Excel, PDF, JSON), optionally a regulation document and a price list. Drag files here or click.")}</p>

        <div className={styles.dateiListe} aria-live="polite">
          {dateien.length === 0 ? <p className={styles.leerListe}>{t("No files yet")}</p> : dateien.map((d, i) => (
            <div key={`${d.datei.name}-${i}`} className={styles.dateiZeile}>
              <Icon name={d.rolle === "lv" ? "report" : d.rolle === "preise" ? "price" : "folder"} />
              <span className={styles.dateiName}>{d.datei.name} <small>{groesse(d.datei.size)}</small></span>
              <select value={d.rolle} aria-label={t("Role of {name}", { name: d.datei.name })}
                onChange={(e) => setzeDateien(dateien.map((x, k) => (k === i ? { ...x, rolle: e.target.value as Rolle } : x)))}>
                <option value="lv">{t("Bill of quantities")}</option>
                <option value="regel">{t("Regulation document")}</option>
                <option value="preise">{t("Price list")}</option>
              </select>
              <button type="button" className={styles.entfernen} aria-label={t("Remove")} onClick={() => setzeDateien(dateien.filter((_, k) => k !== i))}>×</button>
            </div>
          ))}
        </div>
        {dateiFehler && <p className={styles.dateiFehler} role="alert">{dateiFehler}</p>}
        {dateien.length > 0 && !datei && <p className={styles.dateiFehler} role="alert">{t("Mark one file as the bill of quantities.")}</p>}

        <button type="submit" className={`${styles.knopf} ${styles.auswerten}`} disabled={!datei || !!dateiFehler || busy}>
          <Icon name="sparkles" /> {t("Evaluate")}
        </button>
        <p className={styles.beispielZeile}>{t("No file at hand?")}{" "}
          {beispiele.map((b) => (
            <button key={b.id} type="button" className={styles.beispielChip} disabled={busy}
              onClick={() => { setzeDateien([]); void starte({ art: "beispiel", id: b.id, titel: b.titel }); }}>
              {t(b.titel)} · {anzahl(b.lv.positionen.length, t("item"), t("items"))}
            </button>
          ))}
        </p>
      </form>
      </>)}

      {(ergebnis.phase === "laeuft" || ergebnis.phase === "fehler") && (
        <section className={styles.karte} aria-labelledby="ablauf-titel" aria-busy={busy}>
          <h2 id="ablauf-titel" className={styles.abschnitt}>
            {t("Progress for")} {ergebnis.lauf.art === "datei" ? ergebnis.lauf.datei.name : t(ergebnis.lauf.titel)}
          </h2>
          <ol className={styles.schritte}>
            {(Object.keys(SCHRITT_NAMEN) as SchrittId[]).map((id) => {
              const schritt = ergebnis.schritte[id];
              return (
                <li key={id} className={`${styles.schritt} ${styles[`schritt_${schritt.status}`]}`}>
                  <span className={styles.symbol} aria-hidden="true" />
                  <span className={styles.schrittName}>{t(SCHRITT_NAMEN[id])}</span>
                  <span className={styles.schrittStatus}>{t(STATUS_NAMEN[schritt.status])}</span>
                  <span className={styles.schrittText}>{t(schritt.text)}</span>
                </li>
              );
            })}
          </ol>
          {ergebnis.stand && <AnalyseFortschritt stand={ergebnis.stand} t={t} />}
          <div aria-live="polite" className={styles.ansage}>
            {busy && t("{step} is running.", { step: t(SCHRITT_NAMEN[ergebnis.schritte.pruefung.status === "laeuft" ? "pruefung" : "import"]) })}
          </div>
          {ergebnis.phase === "fehler" && (
            <div ref={meldungRef} tabIndex={-1} className={styles.fehler} role="alert">
              <h3>{t(ergebnis.titel)}</h3>
              <p>{t(ergebnis.meldung)}</p>
              {ergebnis.tipp && <p className={styles.tipp}>{t(ergebnis.tipp)}</p>}
              <div className={styles.aktionen}>
                <button type="button" className={styles.knopf} onClick={() => void starte(ergebnis.lauf)}>{t("Try again")}</button>
                {ergebnis.offline && (
                  <button type="button" className={styles.knopfZweit} onClick={() => void zeigeOffline(ergebnis.lauf, ergebnis.schritte)}>
                    {t("Show offline example report")}
                  </button>
                )}
                {ergebnis.lauf.art === "datei" && (
                  <button type="button" className={styles.knopfZweit} onClick={zuruecksetzen}>{t("Choose another file")}</button>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {ergebnis.phase === "fertig" && (
        <div ref={meldungRef} tabIndex={-1} className={`${styles.karte} ${styles.geladen}`}>
          <p>
            <span className={styles.haken} aria-hidden="true">✓</span>{" "}
            {ergebnis.offline
              ? <>{t("The backend is unreachable. Below is the saved report for the synthetic example, not an analysis of your file.")}</>
              : <><strong>{ergebnis.lauf.art === "datei" ? ergebnis.lauf.datei.name : t(ergebnis.lauf.titel)}</strong> · {t("{n} items imported and reviewed.", { n: zahl.format(ergebnis.lv.positionen.length) })}
                {regelwerk && <> · {t("Regulation document")}: {regelwerk.name}</>}</>}
          </p>
          {ergebnis.hinweise?.map((h) => <p key={h} className={styles.tipp} role="note">{h}</p>)}
          <div className={styles.aktionen}>
            <button type="button" className={styles.knopfZweit} onClick={() => void starte(ergebnis.lauf)}>{t("Review again")}</button>
            <button type="button" className={styles.knopf} onClick={zuruecksetzen}>{t("Load another file")}</button>
          </div>
        </div>
      )}

      {ergebnis.phase === "fertig" && (
        <Bericht key={ergebnis.nummer} bericht={ergebnis.bericht} offline={ergebnis.offline}
          anzeigeName={ergebnis.lauf.art === "datei" ? undefined : t(ergebnis.lauf.titel)} />
      )}
    </main>
  );
}
