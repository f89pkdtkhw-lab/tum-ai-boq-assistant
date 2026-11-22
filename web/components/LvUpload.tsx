"use client";

import { type ChangeEvent, type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";
import { api, type AnalyseStatus, type Example, type Health, type LV, type Preisliste, type Pruefbericht as PruefberichtDaten, type Regelwerk } from "@/lib/api";
import { analyseAnfrage, importFehlerText, regelwerkText, routeFehlt } from "@/lib/regelwerk";
import { useT } from "@/lib/einstellungen";
import { lesePreisliste, preislisteText, speicherePreisliste } from "@/lib/preisliste";
import { Icon } from "./icon/Icon";
import { Bericht } from "@/components/bericht/Bericht";
import { bietetOffline } from "@/lib/offline";
import { beobachteJob, verfolgeJob, type JobHaken } from "@/lib/analyse-lauf";
import { Ladeanzeige, useWizard } from "@/components/wizard/Wizard";
import { JOB_NICHT_GESTARTET_TEXT, JOB_VERLOREN_TEXT } from "@/lib/analyse-job";
import {
  aktiviereEvaluation, aktualisiereEvaluation, archiviereAktuelleEvaluation, fortzusetzenderJob, istBerichtGespeichert, istNeuerAuftrag,
  ladeBericht, ladeSitzung, nichtWiederherstellbareEvaluation, setzeAktuelleEvaluation, speichereBericht,
} from "@/lib/evaluation-session";
import { istWizardSchritt } from "@/lib/wizard";
import { KontingentHinweis } from "@/components/saas/KontingentHinweis";
import { zaehleAuswertung } from "@/lib/saas/client";
import { BewertungsmodellWahl } from "@/components/bewertung/BewertungsmodellWahl";
import { useBewertungsmodell } from "@/lib/useBewertungsmodell";
import { AuswahlMenue } from "./ui/AuswahlMenue";
import { TYP_LABEL, datumText, rolleFuerTyp, vaultApi, type VaultEintrag } from "@/lib/vault";
import { ladeAuswahl, leereAuswahl, merkeAuswahl, type UploadRolle } from "@/lib/upload-auswahl";
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

function laufTitel(lauf: Lauf): string {
  return lauf.art === "datei" ? lauf.datei.name : lauf.titel;
}

function merkeLauf(lauf: Lauf, stand: { id: string; jobId: string | null; status: "laeuft" | "fertig" | "fehler"; prozent?: number | null; meldung?: string }, ersetzt?: string) {
  setzeAktuelleEvaluation({
    id: stand.id, jobId: stand.jobId, titel: laufTitel(lauf), status: stand.status,
    schritt: "pruefen", prozent: stand.prozent ?? null, meldung: stand.meldung ?? "",
  }, ersetzt);
}

/** Session side of a job (lib/analyse-lauf.ts): progress, saved report and failure, whichever page is open. */
function jobHaken(jobId: string, titel: string, beispielId: string | null): JobHaken {
  return {
    aufStand: (stand) => aktualisiereEvaluation(jobId, { status: "laeuft", prozent: stand.prozent, meldung: stand.meldung }),
    aufFertig: ({ bericht }) => {
      speichereBericht(titel, beispielId, bericht, jobId);
      aktualisiereEvaluation(jobId, { status: "fertig", prozent: 100, meldung: "" });
    },
    aufFehler: (fehler) => aktualisiereEvaluation(jobId, { status: "fehler", meldung: fehler instanceof Error && fehler.message ? fehler.message : "Unknown error." }),
  };
}

type Rolle = UploadRolle;
/** Guesses a file's role from its name and type; the user can change it in the list. */
function rolleRaten(datei: File, hatLv: boolean): Rolle {
  const n = datei.name.toLowerCase();
  if (/preis|price|kosten|tarif/.test(n) || n.endsWith(".csv")) return "preise";
  // A priced GAEB offer (X84/D84) next to an already chosen bill is its price list.
  if (hatLv && /\.(x84|d84)$/.test(n)) return "preise";
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
  // Resuming a job from an evaluation link: the wizard shows the step from the link once the status is reported.
  const ausLink = useRef(false);
  const lebend = useRef(true);
  // Subscriptions of this page to background jobs (lib/analyse-lauf.ts); the jobs keep running without them.
  const jobAbos = useRef<(() => void)[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const meldungRef = useRef<HTMLDivElement>(null);

  const [beispiele, setBeispiele] = useState<Example[]>([]);
  // t243: reuse a stored bill, regulation or price list from the vault instead of uploading it again.
  const [vaultListe, setVaultListe] = useState<VaultEintrag[] | null>(null);
  const t = useT();
  const { schritt, setSchritt, setStatus } = useWizard();
  const [bewertungsmodell] = useBewertungsmodell();

  useEffect(() => {
    setStatus({ hatBericht: ergebnis.phase === "fertig", laeuft: ergebnis.phase === "laeuft" });
  }, [ergebnis.phase, setStatus]);

  useEffect(() => {
    if (ergebnis.phase === "laeuft" && !ausLink.current && (schritt === "hochladen" || !schritt)) setSchritt("pruefen");
  }, [ergebnis.phase, schritt, setSchritt]);

  useEffect(() => {
    lebend.current = true;
    api.health().then(setHealth).catch(() => setHealth("offline"));
    const params = new URLSearchParams(window.location.search);
    const ausVault = params.get("vault");
    const neu = istNeuerAuftrag(params);
    const beispielId = params.get("beispiel");
    const jobId = params.get("job");
    const evalId = params.get("eval");
    // Files picked before leaving the page (e.g. to Settings) come back with their roles.
    const gemerkt = ladeAuswahl();
    if (gemerkt.length > 0) setzeDateien(gemerkt);
    if (ausVault) {
      window.history.replaceState(null, "", "/");
      vaultApi.liste(["lv", "regelwerk", "preisliste"]).then((liste) => {
        const treffer = liste.find((x) => x.id === ausVault);
        if (treffer) void ausVaultWaehlen(treffer, gemerkt);
      }).catch(() => setDateiFehler(t("The vault is unreachable.")));
    }
    const sitzung = ladeSitzung();
    const berichtDa = (id: string) => istBerichtGespeichert(id);
    const laufend = !neu && !ausVault && !beispielId && fortzusetzenderJob(sitzung, jobId, evalId, berichtDa);
    if (laufend) {
      const id = laufend;
      ausLink.current = true;
      const name = (sitzung.aktuell && (sitzung.aktuell.jobId === id || sitzung.aktuell.id === id) && sitzung.aktuell.titel)
        || ladeBericht(id)?.titel
        || sitzung.aktuell?.titel
        || "Evaluation";
      aktiviereEvaluation(id);
      void setzeFortsetzen(id, name);
      if (!istWizardSchritt(params.get("schritt"))) setSchritt(sitzung.aktuell?.schritt && sitzung.aktuell.schritt !== "hochladen" ? sitzung.aktuell.schritt : "pruefen");
    } else if (!neu && !ausVault && !beispielId) {
      // Coming back from another page: show the report that was open instead of the empty start screen.
      const offen = ladeBericht(evalId || sitzung.aktuell?.id) ?? (sitzung.aktuell ? ladeBericht() : null);
      if (offen) {
        if (evalId) aktiviereEvaluation(evalId);
        const lauf: Lauf = offen.beispielId ? { art: "beispiel", id: offen.beispielId, titel: offen.titel } : { art: "lv", titel: offen.titel, lv: offen.bericht.lv };
        const fertig: Schritt = { status: "fertig", text: "Restored from this browser session." };
        setErgebnis({ phase: "fertig", lauf, lv: offen.bericht.lv, bericht: offen.bericht, nummer: ++laufNummer.current, offline: false,
          schritte: { datei: fertig, import: fertig, pruefung: fertig } });
        if (!istWizardSchritt(params.get("schritt"))) {
          setSchritt(sitzung.aktuell?.schritt && sitzung.aktuell.schritt !== "hochladen" ? sitzung.aktuell.schritt : "pruefen");
        }
      } else {
        const verloren = nichtWiederherstellbareEvaluation(sitzung, jobId, evalId, berichtDa);
        if (verloren) {
          ausLink.current = true;
          aktiviereEvaluation(verloren.id);
          const meldung = verloren.jobId ? JOB_VERLOREN_TEXT : JOB_NICHT_GESTARTET_TEXT;
          aktualisiereEvaluation(verloren.id, { status: "fehler", meldung });
          const lauf: Lauf = { art: "lv", titel: verloren.titel, lv: { name: verloren.titel, quelle: "session", positionen: [], summen: {} } };
          const fertig: Schritt = { status: "fertig", text: "Restored from this browser session." };
          setErgebnis({
            phase: "fehler", lauf,
            schritte: { datei: fertig, import: fertig, pruefung: { status: "fehler", text: meldung } },
            titel: "Review failed", meldung, tipp: null, offline: false,
          });
          if (!istWizardSchritt(params.get("schritt"))) setSchritt("pruefen");
        }
      }
    }
    api.examples().then((liste) => {
      setBeispiele(liste);
      // The dashboard opens a past example again with /?beispiel=<id>.
      const id = new URLSearchParams(window.location.search).get("beispiel");
      const treffer = liste.find((b) => b.id === id);
      if (treffer) void starte({ art: "beispiel", id: treffer.id, titel: treffer.titel });
    }).catch(() => {});
    return () => {
      lebend.current = false;
      jobAbos.current.forEach((ab) => ab());
      jobAbos.current = [];
    };
    // starte / setzeFortsetzen run only once on mount.
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
    merkeAuswahl(liste);
    setDateien(liste);
    waehleDatei(liste.find((d) => d.rolle === "lv")?.datei ?? null);
    setRegelwerk(liste.find((d) => d.rolle === "regel")?.datei ?? null);
  }
  function hinzufuegen(neu: File[]) {
    const liste = [...dateien];
    for (const f of neu) liste.push({ datei: f, rolle: rolleRaten(f, liste.some((d) => d.rolle === "lv")) });
    setzeDateien(liste);
  }

  async function ausVaultWaehlen(eintrag: VaultEintrag, bisher = dateien) {
    setVaultListe(null);
    const rolle = rolleFuerTyp(eintrag.typ);
    if (!rolle) return;
    try {
      const neu = await vaultApi.alsDatei(eintrag);
      // One bill per run: a bill from the vault replaces a previous bill; attachments are added.
      setzeDateien([...bisher.filter((d) => rolle !== "lv" || d.rolle !== "lv"), { datei: neu, rolle }]);
    } catch (fehler) {
      setDateiFehler(fehler instanceof Error ? fehler.message : String(fehler));
    }
  }
  async function vaultOeffnen() {
    try {
      setVaultListe(await vaultApi.liste(["lv", "regelwerk", "preisliste"]));
    } catch {
      setDateiFehler(t("The vault is unreachable."));
    }
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
    ausLink.current = false;
    // #166: with a live model the review also researches standards on the web (N5), which takes longer.
    const recherche = health !== null && health !== "offline" && !health.mock;
    const nummer = ++laufNummer.current;
    // Not tied to the page being mounted: leaving during import still starts the job (state updates are then no-ops).
    const aktuell = () => nummer === laufNummer.current;
    let schritte = startSchritte(lauf);
    let gestarteterJob: string | null = null;
    setErgebnis({ phase: "laeuft", lauf, schritte });
    merkeLauf(lauf, { id: `lokal-${nummer}`, jobId: null, status: "laeuft", prozent: 0, meldung: "" });
    zaehleAuswertung(); // soft plan quota (lib/saas): fire-and-forget, never blocks or fails the run

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
      const id = stand?.job_id ?? gestarteterJob;
      merkeLauf(lauf, { id: id ?? `lokal-${nummer}`, jobId: id, status: "fehler", prozent: stand?.prozent ?? null, meldung });
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
        tipp = "Use a GAEB, Excel, PDF or BoQ JSON file.";
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
      pruefung: { status: "laeuft", text: recherche ? "Running review rules; researching standards …" : "Running review rules …" },
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
      schritte = { ...schritte, pruefung: { status: "laeuft", text: recherche ? "Analysing the bill with its attachments; researching standards …" : "Analysing the bill with its attachments …" } };
      setErgebnis({ phase: "laeuft", lauf, schritte });
    }

    let bericht: PruefberichtDaten;
    const job: { stand: AnalyseStatus | null } = { stand: null };
    try {
      // #167: always the full analysis, so the price database, calculation and estimated bill run without attachments too.
      const anfrage = analyseAnfrage(lv, regelwerkDaten, preislisteDaten, bewertungsmodell);
      const synchron = () => api.analyse(anfrage).catch((fehler) => {
        if (!routeFehlt(fehler)) throw fehler;
        if (regelwerkDaten || preislisteDaten) hinweise.push("This backend has no combined analysis yet: the bill was reviewed without its attachments.");
        return api.pruefen(lv, bewertungsmodell);
      });
      // #165: background job with progress; #167: always the full analysis (no `nur_pruefen`).
      try {
        const { job_id } = await api.starteAnalyse(anfrage);
        gestarteterJob = job_id;
        merkeLauf(lauf, { id: job_id, jobId: job_id, status: "laeuft", prozent: 0, meldung: "" }, `lokal-${nummer}`);
        // Polling runs in the background (lib/analyse-lauf.ts), so progress and the report survive leaving the page.
        const fertig = verfolgeJob(api, job_id, jobHaken(job_id, laufTitel(lauf), lauf.art === "beispiel" ? lauf.id : null));
        jobAbos.current.push(beobachteJob(job_id, (stand) => {
          job.stand = stand;
          if (!aktuell()) return;
          schritte = { ...schritte, pruefung: { status: "laeuft", text: stand.meldung } };
          setErgebnis({ phase: "laeuft", lauf, schritte, stand });
        }));
        const ende = await fertig;
        bericht = ende.bericht;
        hinweise.push(...ende.stand.fehler);
      } catch (fehler) {
        if (gestarteterJob || !routeFehlt(fehler)) throw fehler;
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
    if (!gestarteterJob) { // older backend without jobs; with a job the background hooks saved the report
      speichereBericht(laufTitel(lauf), lauf.art === "beispiel" ? lauf.id : null, bericht, `lokal-${nummer}`);
      merkeLauf(lauf, { id: `lokal-${nummer}`, jobId: null, status: "fertig", prozent: 100, meldung: "" });
    }
    if (health === "offline") api.health().then(setHealth).catch(() => {});
  }

  async function setzeFortsetzen(jobId: string, titel: string) {
    const nummer = ++laufNummer.current;
    const aktuell = () => nummer === laufNummer.current && lebend.current;
    const lauf: Lauf = { art: "lv", titel, lv: { name: titel, quelle: "session", positionen: [], summen: {} } };
    let schritte: Schritte = {
      datei: { status: "fertig", text: "Restored from this browser session." },
      import: { status: "fertig", text: "Restored from this browser session." },
      pruefung: { status: "laeuft", text: "Resuming the analysis …" },
    };
    if (!aktiviereEvaluation(jobId)) merkeLauf(lauf, { id: jobId, jobId, status: "laeuft", prozent: 0, meldung: "Resuming the analysis …" });
    setErgebnis({ phase: "laeuft", lauf, schritte, stand: null });
    const job: { stand: AnalyseStatus | null } = { stand: null };
    // Joins the background poller if this tab already follows the job, so the live percent shows at once.
    const fertig = verfolgeJob(api, jobId, jobHaken(jobId, titel, null));
    jobAbos.current.push(beobachteJob(jobId, (stand) => {
      job.stand = stand;
      if (!aktuell()) return;
      schritte = { ...schritte, pruefung: { status: "laeuft", text: stand.meldung } };
      setErgebnis({ phase: "laeuft", lauf, schritte, stand });
    }));
    try {
      const ende = await fertig;
      if (!aktuell()) return;
      const bericht = ende.bericht;
      const lv = bericht.lv;
      schritte = { ...schritte, pruefung: { status: "fertig", text: `${anzahl(bericht.findings.length, "Entry", "Entries")} in the report.` } };
      setErgebnis({ phase: "fertig", lauf: { art: "lv", titel, lv }, schritte, lv, bericht, nummer, offline: false, hinweise: ende.stand.fehler });
    } catch (fehler) {
      if (!aktuell()) return;
      const stand = (fehler as { stand?: AnalyseStatus }).stand ?? job.stand ?? null;
      const meldung = fehler instanceof Error && fehler.message ? fehler.message : "Unknown error.";
      schritte = { ...schritte, pruefung: { status: "fehler", text: meldung } };
      setErgebnis({ phase: "fehler", lauf, schritte, titel: "Review failed", meldung, tipp: null, offline: false, stand });
    }
  }

  async function absenden(event: FormEvent) {
    event.preventDefault();
    if (!datei || dateiFehler || busy) return;
    // A price list goes into the (browser) price database first, so the price report can use it.
    const preisDatei = dateien.find((d) => d.rolle === "preise")?.datei;
    if (preisDatei) { try { speicherePreisliste(lesePreisliste(await preisDatei.text())); } catch { /* not readable: review runs without it */ } }
    leereAuswahl();
    void starte({ art: "datei", datei, regelwerk, preisliste: preisDatei ?? null });
  }

  function zuruecksetzen() {
    archiviereAktuelleEvaluation();
    leereAuswahl();
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
      : health.mock
        ? { klasse: styles.statusMock, text: t("AI not configured") }
        : { klasse: styles.statusLive, text: `${health.provider} · ${health.model}` };

  return (
    <main className={styles.seite}>
      <header className={styles.kopf}>
        <span className={styles.marke}>{t("Upload & report")}</span>
        <span className={`${styles.status} ${status.klasse}`}>{status.text}</span>
      </header>

      {(ergebnis.phase === "leer" || (schritt === "hochladen" && ergebnis.phase !== "fehler" && ergebnis.phase !== "laeuft")) && (<>
      <KontingentHinweis />
      {/* Start screen from the team sketch: one upload button, the list of current files, Evaluate. */}
      <form className={styles.start} onSubmit={absenden} aria-describedby="upload-regeln"
        onDragOver={(e) => { e.preventDefault(); setZiehen(true); }} onDragLeave={() => setZiehen(false)} onDrop={aufAblegen}>
        <h1 className={styles.startTitel}>{t("New evaluation")}</h1>
        <label className={`${styles.hochladen} ${ziehen ? styles.ablageAktiv : ""}`}>
          <input ref={inputRef} className={styles.dateiEingabe} type="file" multiple accept={`${ACCEPT},.csv,.docx,.txt,.md,.x86,.d84`} onChange={aufAuswahl} disabled={busy} />
          <Icon name="upload" size={22} /> {t("Upload files")}
        </label>
        <AuswahlMenue knopfKlasse={styles.vaultKnopf} disabled={busy} ausrichtung="mitte" label={t("Choose from vault")}
          knopfInhalt={<><Icon name="folder" /> {t("Choose from vault")}</>}
          leerText={t("The vault is empty. Files you analyse are stored there automatically.")}
          onOeffnen={() => void vaultOeffnen()} onSchliessen={() => setVaultListe(null)}
          eintraege={vaultListe && vaultListe.slice(0, 30).map((x) => ({ key: x.id, label: `${x.dateiname} · ${t(TYP_LABEL[x.typ])} · ${datumText(x.hochgeladen_am)}`, onClick: () => void ausVaultWaehlen(x) }))} />
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

        <BewertungsmodellWahl />
        <button type="submit" className={`${styles.knopf} ${styles.auswerten}`} disabled={!datei || !!dateiFehler || busy}>
          <Icon name="sparkles" /> {t("Evaluate")}
        </button>
      </form>
      </>)}

      {(ergebnis.phase === "laeuft" || ergebnis.phase === "fehler" || (ergebnis.phase === "fertig" && schritt === "pruefen")) && (
        <section className={styles.karte} aria-labelledby="ablauf-titel" aria-busy={busy}>
          <h2 id="ablauf-titel" className={styles.abschnitt}>
            {ergebnis.lauf.art === "datei" ? ergebnis.lauf.datei.name : t(ergebnis.lauf.titel)}
          </h2>
          <Ladeanzeige
            phase={ergebnis.phase === "fertig" ? "fertig" : ergebnis.phase}
            importFertig={ergebnis.schritte.import.status === "fertig"}
            standStatus={ergebnis.phase === "fertig" ? "fertig" : (ergebnis.stand?.status ?? (ergebnis.schritte.pruefung.status === "laeuft" ? "laeuft" : null))}
            stand={"stand" in ergebnis ? ergebnis.stand ?? null : null}
            dateiname={ergebnis.phase === "fertig" ? t("{n} items imported and reviewed.", { n: zahl.format(ergebnis.lv.positionen.length) }) : undefined}
          />
          {ergebnis.phase === "fertig" && ergebnis.bericht.zusammenfassung && (
            <p className={styles.ansage}>
              {t("{n} items imported and reviewed.", { n: zahl.format(ergebnis.lv.positionen.length) })}
              {ergebnis.bericht.zusammenfassung.grosse_probleme ? ` · ${ergebnis.bericht.zusammenfassung.grosse_probleme} ${t("Issues")}` : ""}
            </p>
          )}
          {ergebnis.phase === "fehler" && (
            <div ref={meldungRef} tabIndex={-1} className={styles.fehler} role="alert">
              <h3>{t(ergebnis.titel)}</h3>
              <p>{t(ergebnis.meldung)}</p>
              {ergebnis.tipp && <p className={styles.tipp}>{t(ergebnis.tipp)}</p>}
              <div className={styles.aktionen}>
                <button type="button" className={styles.knopf} onClick={() => void starte(ergebnis.lauf)}>{t("Try again")}</button>
                {ergebnis.lauf.art === "datei" && (
                  <button type="button" className={styles.knopfZweit} onClick={zuruecksetzen}>{t("Choose another file")}</button>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {ergebnis.phase === "fertig" && schritt !== "pruefen" && (
        <div ref={meldungRef} tabIndex={-1} className={`${styles.karte} ${styles.geladen}`}>
          <p>
            <span className={styles.haken} aria-hidden="true">✓</span>{" "}
            {<><strong>{ergebnis.lauf.art === "datei" ? ergebnis.lauf.datei.name : t(ergebnis.lauf.titel)}</strong> · {t("{n} items imported and reviewed.", { n: zahl.format(ergebnis.lv.positionen.length) })}
                {regelwerk && <> · {t("Regulation document")}: {regelwerk.name}</>}</>}
          </p>
          {ergebnis.hinweise?.map((h) => <p key={h} className={styles.tipp} role="note">{h}</p>)}
          <div className={styles.aktionen}>
            <button type="button" className={styles.knopfZweit} onClick={() => void starte(ergebnis.lauf)}>{t("Review again")}</button>
            <button type="button" className={styles.knopf} onClick={zuruecksetzen}>{t("Load another file")}</button>
          </div>
        </div>
      )}

      {ergebnis.phase === "fertig" && (schritt === "fehler" || schritt === "preis") && (
        <Bericht key={`${ergebnis.nummer}-${schritt}`} bericht={ergebnis.bericht} offline={ergebnis.offline}
          anzeigeName={ergebnis.lauf.art === "datei" ? undefined : t(ergebnis.lauf.titel)}
          original={ergebnis.lauf.art === "datei" ? ergebnis.lauf.datei : null}
          ansicht={schritt === "preis" ? "preis" : "fehler"} />
      )}
    </main>
  );
}
