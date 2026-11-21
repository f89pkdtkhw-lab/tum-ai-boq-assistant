"use client";

import { useDok } from "@/components/dok/useDok";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Finding, Position, Pruefbericht as PruefberichtDaten } from "@/lib/api";
import { mengenSchluessel } from "@/lib/mengen";
import { baueTitelbaum, imTeilbaum, OHNE_TITEL_NAME, ozImTeilbaum } from "@/lib/titelbaum";
import { filtereFindings, normalisiere, positionTrifft } from "@/lib/suche";
import {
  anzahlGeprueft, bewertungVon, ladeBewertungen, setze, speichereBewertungen, STATUS,
  type Bewertung as BewertungDaten, type Bewertungen, type Status,
} from "@/lib/bewertung";
import { aktuelleSeite, ausschnitt, seiteFuer, seiteNachGroesse, seiteVon, STANDARD_SEITENGROESSE, type Blatt } from "@/lib/seiten";
import { Bewertung, MitStatus } from "./bewertung/Bewertung";
import { Mengen } from "./mengen/Mengen";
import { Bieterfragen } from "./bieterfragen/Bieterfragen";
import { Suche } from "./suche/Suche";
import { Titelbaum } from "./titelbaum/Titelbaum";
import { Top } from "./top/Top";
import { Seiten } from "./seiten/Seiten";
import { Historie } from "./historie/Historie";
import { Einschaetzung, useEinschaetzung, type Bewertungsdaten } from "./einschaetzung/Einschaetzung";
import { Icon, type IconName } from "./icon/Icon";
import { Preisspiegel } from "./preise/Preisspiegel";
import { liesJetzt, useEinstellungen, useT } from "@/lib/einstellungen";
import { befundAnzeige } from "@/lib/befundtext";
import styles from "./pruefbericht.module.css";

/**
 * Handoff to the export page (/export, follow-up issue #15):
 * Before navigating, store the displayed `Pruefbericht` unchanged as JSON
 * (`JSON.stringify(bericht)`) under this sessionStorage key. The JSON download
 * contains the same object, so /export can read both sources in the same way.
 * Format: the unwrapped `Pruefbericht` type from web/lib/api.ts.
 * A new format requires a new key.
 */
export const PRUEFBERICHT_SPEICHER_SCHLUESSEL = "lv-pruefbericht-v1";

const MOCK_REGEL = "MOCK_LLM";
const REITER_SCHLUESSEL = "lv-reiter-v1";

type Kategorie = Finding["kategorie"];
type Schwere = Finding["schwere"];

const KATEGORIEN: { wert: Kategorie; name: string }[] = [
  { wert: "fehler", name: "Error" },
  { wert: "risiko", name: "Risk" },
  { wert: "nachtrag", name: "Change order" },
];
const SCHWEREN: { wert: Schwere; name: string }[] = [
  { wert: "kritisch", name: "Critical" },
  { wert: "hoch", name: "High" },
  { wert: "mittel", name: "Medium" },
  { wert: "niedrig", name: "Low" },
];
const SCHWERE_RANG: Record<Schwere, number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const TYP_NAME: Record<Position["typ"], string> = {
  normal: "Standard item", bedarf: "Optional item", alternativ: "Alternative item",
  zulage: "Supplement item", pauschal: "Lump sum item", stundenlohn: "Hourly rate item",
};

const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" });
const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });
// KPI tile: whole euros, millions as "€5.8M" (full value in the tooltip), so the tile never overflows.
const euroKurz = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 });
const euroGanz = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

/** CSS custom property for the danger stripe: worst severity, or green when there are no findings. */
function gefahr(liste: Finding[] | undefined): React.CSSProperties {
  const schlimmste = liste?.reduce<Schwere | null>((a, f) => (a === null || SCHWERE_RANG[f.schwere] < SCHWERE_RANG[a] ? f.schwere : a), null);
  return { "--sev": `var(--sev-${schlimmste ?? "ok"})` } as React.CSSProperties;
}

function istMock(finding: Finding) {
  // Contract (api/app/pruefung/llm_pruefung.py): every model-mock rule ID starts with MOCK_.
  return finding.regel_id.startsWith("MOCK_");
}

function kategorieName(wert: Kategorie) {
  return KATEGORIEN.find((k) => k.wert === wert)?.name ?? wert;
}

function schwereName(wert: Schwere) {
  return SCHWEREN.find((s) => s.wert === wert)?.name ?? wert;
}

function Unbekannt() {
  const t = useT();
  return <span className={styles.unbekannt}>{t("unknown")}</span>;
}

function Euro({ wert }: { wert: number | null }) {
  return wert === null ? <Unbekannt /> : <>{euro.format(wert)}</>;
}

function Menge({ menge, einheit }: { menge: number | null; einheit: string | null }) {
  const t = useT();
  return (
    <>
      {menge === null ? <Unbekannt /> : zahl.format(menge)}{" "}
      {einheit ? einheit : <span className={styles.unbekannt}>{t("(unit unknown)")}</span>}
    </>
  );
}

function dateiname(name: string) {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `pruefbericht-${basis || "lv"}.json`;
}

type Auswahl = { oz: string; findingId: string | null };
type Reiter = "uebersicht" | "findings" | "positionen" | "preise" | "fragen" | "mengen";

/** `anzeigeName`: the readable report name (e.g. the translated example title); the file's own name stays in the source line. */
/** `bewertung` comes from the levelled report (components/bericht) when embedded; `eingebettet` hides header and summary there. */
export function Pruefbericht({ bericht, offline = false, anzeigeName, bewertung: vonAussen, eingebettet = false }: {
  bericht: PruefberichtDaten; offline?: boolean; anzeigeName?: string; bewertung?: Bewertungsdaten; eingebettet?: boolean;
}) {
  const d = useDok();
  const { e: einstellungen, t } = useEinstellungen();
  const { lv, kennzahlen } = bericht;
  const eigene = useEinschaetzung(bericht, !vonAussen);
  const bewertung = vonAussen ?? eigene;
  // Setting "hide demo findings": entries from the offline model mock leave every list and count.
  // Display texts: German when chosen, ranking tail removed (lib/befundtext.ts).
  const findings = useMemo(() => (einstellungen.mockAusblenden ? bericht.findings.filter((f) => !istMock(f)) : bericht.findings)
    .map((f) => befundAnzeige(f, einstellungen.sprache)), [bericht.findings, einstellungen.mockAusblenden, einstellungen.sprache]);
  // The open tab survives page switches in this browser tab; a fresh report starts on the tab chosen in settings.
  const [reiter, setReiterState] = useState<Reiter>(() => {
    try { return (window.sessionStorage.getItem(REITER_SCHLUESSEL) as Reiter | null) ?? liesJetzt().startReiter; } catch { return "uebersicht"; }
  });
  const setReiter = (r: Reiter) => { setReiterState(r); try { window.sessionStorage.setItem(REITER_SCHLUESSEL, r); } catch { /* not kept */ } };
  const [kategorie, setKategorie] = useState<Kategorie | null>(null);
  const [schwere, setSchwere] = useState<Schwere | null>(null);
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [exportFehler, setExportFehler] = useState("");
  const [einheit, setEinheit] = useState<string | null>(null);
  const [suche, setSuche] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [titel, setTitel] = useState<string[] | null>(null);
  const [bewertungen, setBewertungen] = useState<Bewertungen>({});
  const [speicherFehler, setSpeicherFehler] = useState(false);
  const [findingBlatt, setFindingBlatt] = useState<Blatt>({ schluessel: "", seite: 0 });
  const [findingGroesse, setFindingGroesse] = useState<number>(() => liesJetzt().seitengroesse ?? STANDARD_SEITENGROESSE);
  const [positionBlatt, setPositionBlatt] = useState<Blatt>({ schluessel: "", seite: 0 });
  const [positionGroesse, setPositionGroesse] = useState<number>(() => liesJetzt().seitengroesse ?? STANDARD_SEITENGROESSE);
  const detailRef = useRef<HTMLElement>(null);
  const positionenRef = useRef<HTMLElement>(null);
  const findingsAnfangRef = useRef<HTMLHeadingElement>(null);

  const positionenNachOz = useMemo(() => {
    const karte = new Map<string, Position[]>();
    for (const position of lv.positionen) {
      karte.set(position.oz, [...(karte.get(position.oz) ?? []), position]);
    }
    return karte;
  }, [lv.positionen]);

  const findingsNachOz = useMemo(() => {
    const karte = new Map<string, Finding[]>();
    for (const finding of findings) {
      karte.set(finding.oz, [...(karte.get(finding.oz) ?? []), finding]);
    }
    return karte;
  }, [findings]);

  const sortiert = useMemo(
    () => findings
      .map((finding, index) => ({ finding, index }))
      .sort((a, b) => SCHWERE_RANG[a.finding.schwere] - SCHWERE_RANG[b.finding.schwere] || a.index - b.index)
      .map(({ finding }) => finding),
    [findings],
  );
  const titelbaum = useMemo(() => baueTitelbaum(lv.positionen, findings), [lv.positionen, findings]);
  const ozImTitel = useMemo(() => (titel === null ? null : ozImTeilbaum(lv.positionen, titel)), [lv.positionen, titel]);
  const gefiltert = useMemo(
    () => filtereFindings(sortiert, lv.positionen, { suche, kategorie, schwere })
      .filter((f) => status === null || bewertungVon(bewertungen, f.id).status === status)
      .filter((f) => ozImTitel === null || ozImTitel.has(f.oz)),
    [sortiert, lv.positionen, suche, kategorie, schwere, status, bewertungen, ozImTitel],
  );

  // Load after mount: localStorage does not exist during server rendering.
  useEffect(() => { setBewertungen(ladeBewertungen(lv.name, findings)); }, [lv.name, findings]);

  function bewerte(id: string, aenderung: Partial<BewertungDaten>) {
    const neu = setze(bewertungen, id, aenderung);
    setBewertungen(neu);
    setSpeicherFehler(!speichereBewertungen(lv.name, neu));
  }
  const geprueft = anzahlGeprueft(findings, bewertungen);

  const mockAnzahl = findings.filter(istMock).length;
  const echteAnzahl = findings.length - mockAnzahl;
  const bekannteEuro = findings.filter((f) => !istMock(f) && f.euro_wirkung !== null);
  const euroSumme = bekannteEuro.reduce((summe, f) => summe + (f.euro_wirkung ?? 0), 0);
  const euroUnbekannt = echteAnzahl - bekannteEuro.length;
  const doppelteOz = [...positionenNachOz.values()].filter((liste) => liste.length > 1).length;

  function waehle(oz: string, findingId: string | null, springen = true) {
    setAuswahl({ oz, findingId });
    // Opened from elsewhere (top panel, title tree, search, detail): show the page that contains it.
    // A click inside a table passes springen=false, so a duplicate OZ does not jump to its first occurrence.
    const findingSeiteNeu = !springen || findingId === null ? null : seiteFuer(gefiltert, (f) => f.id === findingId, findingGroesse);
    if (findingSeiteNeu !== null) setFindingBlatt({ schluessel: findingSchluessel, seite: findingSeiteNeu });
    const positionSeiteNeu = !springen ? null : seiteFuer(sichtbarePositionen, (p) => p.oz === oz, positionGroesse);
    if (positionSeiteNeu !== null) setPositionBlatt({ schluessel: positionSchluessel, seite: positionSeiteNeu });
    // On narrow screens, details appear below the list: scroll there.
    requestAnimationFrame(() => {
      const ziel = detailRef.current;
      if (!ziel) return;
      if (window.matchMedia("(max-width: 900px)").matches) {
        const ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        ziel.scrollIntoView({ behavior: ruhig ? "auto" : "smooth", block: "start" });
        ziel.focus({ preventScroll: true });
      }
    });
  }

  function herunterladen() {
    const blob = new Blob([JSON.stringify(bericht, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = dateiname(lv.name);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function zumExport(event: React.MouseEvent<HTMLAnchorElement>) {
    try {
      window.sessionStorage.setItem(PRUEFBERICHT_SPEICHER_SCHLUESSEL, JSON.stringify(bericht));
      setExportFehler("");
    } catch {
      event.preventDefault();
      setExportFehler(t("Could not pass the report to the export page (browser storage blocked). Please use the JSON download."));
    }
  }

  const sucheAktiv = normalisiere(suche) !== "";
  const filterAktiv = kategorie !== null || schwere !== null || status !== null || titel !== null || sucheAktiv;
  const sichtbarePositionen = lv.positionen.filter(
    (p) => (einheit === null || mengenSchluessel(p) === einheit) && (titel === null || imTeilbaum(p, titel)) && positionTrifft(p, suche),
  );

  // Paging runs after every filter; a changed filter key shows page 1 again (issue #67).
  const findingSchluessel = JSON.stringify([kategorie, schwere, status, titel, suche]);
  const findingSeite = seiteVon(gefiltert.length, aktuelleSeite(findingBlatt, findingSchluessel), findingGroesse);
  const sichtbareFindings = ausschnitt(gefiltert, findingSeite);
  const positionSchluessel = JSON.stringify([einheit, titel, suche]);
  const positionSeite = seiteVon(sichtbarePositionen.length, aktuelleSeite(positionBlatt, positionSchluessel), positionGroesse);
  const seitenPositionen = ausschnitt(sichtbarePositionen, positionSeite);

  // Step through the current list with the detail's ‹ › buttons or the arrow keys: findings when a finding
  // is open, otherwise the visible items.
  const schrittListe: { oz: string; id: string | null }[] = auswahl?.findingId
    ? gefiltert.map((f) => ({ oz: f.oz, id: f.id }))
    : sichtbarePositionen.map((p) => ({ oz: p.oz, id: null }));
  const schrittIndex = auswahl ? schrittListe.findIndex((x) => (auswahl.findingId ? x.id === auswahl.findingId : x.oz === auswahl.oz)) : -1;
  function schritt(delta: number) {
    const ziel = schrittListe[schrittIndex + delta];
    if (!ziel) return;
    waehle(ziel.oz, ziel.id);
    requestAnimationFrame(() => document.querySelector(`.${styles.karteGewaehlt}, .${styles.zeileGewaehlt}`)?.scrollIntoView({ block: "nearest" }));
  }
  useEffect(() => {
    function taste(event: KeyboardEvent) {
      const ziel = event.target as HTMLElement | null;
      if (event.altKey || event.ctrlKey || event.metaKey || (ziel && (ziel.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(ziel.tagName)))) return;
      // ← ↑ previous, → ↓ next; only while a finding or item is open, so arrows scroll the page otherwise.
      if (event.key === "Escape") { setAuswahl(null); return; }
      if (event.key === "ArrowRight" || event.key === "ArrowDown") { event.preventDefault(); schritt(1); }
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") { event.preventDefault(); schritt(-1); }
    }
    if (schrittIndex < 0) return;
    document.addEventListener("keydown", taste);
    return () => document.removeEventListener("keydown", taste);
  });

  function zumAnfang(anker: HTMLElement | null) {
    requestAnimationFrame(() => anker?.scrollIntoView({ block: "start" }));
  }
  function findingsSteuerung(beschriftung: string, anker: boolean) {
    return (
      <Seiten seite={findingSeite} groesse={findingGroesse} beschriftung={beschriftung}
        onSeite={(seite) => { setFindingBlatt({ schluessel: findingSchluessel, seite }); if (anker) zumAnfang(findingsAnfangRef.current); }}
        onGroesse={(groesse) => { setFindingGroesse(groesse); setFindingBlatt({ schluessel: findingSchluessel, seite: seiteNachGroesse(findingSeite, groesse) }); }} />
    );
  }
  function positionenSteuerung(beschriftung: string, anker: boolean) {
    return (
      <Seiten seite={positionSeite} groesse={positionGroesse} beschriftung={beschriftung} eingerueckt
        onSeite={(seite) => { setPositionBlatt({ schluessel: positionSchluessel, seite }); if (anker) zumAnfang(positionenRef.current); }}
        onGroesse={(groesse) => { setPositionGroesse(groesse); setPositionBlatt({ schluessel: positionSchluessel, seite: seiteNachGroesse(positionSeite, groesse) }); }} />
    );
  }

  function sucheAendern(wert: string) {
    setSuche(wert);
  }

  function waehleTitel(pfad: string[] | null) {
    setTitel(pfad);
  }

  function waehleEinheit(schluessel: string | null) {
    setEinheit(schluessel);
    if (schluessel !== null) setReiter("positionen");
  }

  return (
    <section className={styles.bericht} aria-labelledby="pruefbericht-titel">
      {!eingebettet && (<>
      <header className={styles.kopf}>
        <div>
          <p className={styles.kicker}>{t("Review report")}</p>
          <h2 id="pruefbericht-titel" className={styles.titel}>{anzeigeName || lv.name || t("Unnamed BoQ")}</h2>
          <p className={styles.quelle}>{anzeigeName && anzeigeName !== lv.name && <>{t("File")}: {lv.name} · </>}{t("Source:")} {lv.quelle || <Unbekannt />}</p>
        </div>
        <div className={styles.aktionen}>
          <button type="button" className={styles.knopf} onClick={herunterladen}>{t("Download JSON")}</button>
          <a className={styles.knopfZweit} href="/export" onClick={zumExport}>{t("Export report")}</a>
        </div>
      </header>
      {exportFehler && <p className={styles.fehler} role="alert">{exportFehler}</p>}

      {offline && (
        <p className={styles.offlineHinweis} role="note">
          <strong>{t("Offline example – not live analysis.")}</strong> {t("The backend is unreachable; this is a saved report for the synthetic example BoQ.")}
        </p>
      )}

      {kennzahlen.modell_mock && (
        <p className={styles.mockHinweis} role="note">
          <strong>{t("Demo mode:")}</strong> {t("The model review runs as an offline mock. Entries with the identifier")}{" "}
          <code>{MOCK_REGEL}</code> {t("only demonstrate the report format and are not domain findings.")}
        </p>
      )}

      {/* Team spec: score out of 10, estimated amount ±, then how many recommendations, warnings and big problems. */}
      <div className={styles.kopfzahlen}>
        <button type="button" className={`${styles.zahlKachel} ${styles[`ampel_${bewertung.e.ampel}`]}`} onClick={() => setReiter("uebersicht")}>
          <span className={styles.zahlTitel}><Icon name="gauge" />{t("Score")}</span>
          <span className={styles.zahlWert}>{bewertung.e.score.toFixed(1)}<small> / 10</small></span>
          <span className={styles.zahlUnter}>{t(bewertung.e.urteil)}{!bewertung.e.offiziell && ` · ${t("browser only")}`}</span>
        </button>
        <button type="button" className={styles.zahlKachel} onClick={() => setReiter("uebersicht")}
          title={bewertung.e.schaetzung ? `${euro.format(bewertung.e.schaetzung.mitte)} ± ${euro.format(bewertung.e.schaetzung.plusMinus)}` : undefined}>
          <span className={styles.zahlTitel}><Icon name="euro" />{t("Estimated")}</span>
          {/* Estimate ± (team spec UI 4): the backend's deviation (#94) when it sends one, else the browser range. */}
          <span className={styles.zahlWert}>{bewertung.e.schaetzung
            ? <>{euroKurz.format(bewertung.e.schaetzung.mitte)}<small> ± {euroKurz.format(Math.abs(bericht.zusammenfassung?.schaetzung_abweichung_eur ?? bewertung.e.schaetzung.plusMinus))}</small></>
            : <Unbekannt />}</span>
          <span className={styles.zahlUnter}>{bewertung.e.schaetzung ? t("range from file, history and options") : t("no prices in the file")}</span>
        </button>
        <button type="button" className={styles.zahlKachel} onClick={() => setReiter("uebersicht")}>
          <span className={styles.zahlTitel}><Icon name="lightbulb" />{t("Recommendations")}</span>
          <span className={styles.zahlWert}>{zahl.format(bewertung.empfehlungen)}</span>
          <span className={styles.zahlUnter}>{t("no penalty, for awareness")}</span>
        </button>
        <button type="button" className={`${styles.zahlKachel} ${bewertung.e.zaehler.warnungen ? styles.ampel_gelb : ""}`} onClick={() => { setSchwere("mittel"); setReiter("findings"); }}>
          <span className={styles.zahlTitel}><Icon name="warning" />{t("Warnings")}</span>
          <span className={styles.zahlWert}>{zahl.format(bewertung.e.zaehler.warnungen)}</span>
          <span className={styles.zahlUnter}>{t("check, small effect")}</span>
        </button>
        <button type="button" className={`${styles.zahlKachel} ${bewertung.e.zaehler.grosseProbleme ? styles.ampel_rot : ""}`} onClick={() => { setSchwere(null); setReiter("findings"); }}>
          <span className={styles.zahlTitel}><Icon name="alert" />{t("Big problems")}</span>
          <span className={styles.zahlWert}>{zahl.format(bewertung.e.zaehler.grosseProbleme)}</span>
          <span className={styles.zahlUnter}>{t("fix before bidding")}</span>
        </button>
      </div>
      </>)}

      <p className={styles.metaZeile}>
        {t("{n} items", { n: zahl.format(kennzahlen.positionen) })}{doppelteOz > 0 && <> · {t("{n} duplicate item numbers", { n: doppelteOz })}</>}
        {" · "}{t("{n} entries", { n: zahl.format(kennzahlen.findings) })}{mockAnzahl > 0 && <> ({t("including {n} demo entries", { n: mockAnzahl })})</>}
        {" · "}{t("Reviewed")} {zahl.format(geprueft)}/{zahl.format(findings.length)}
        {" · "}{t("Evidenced euro impact")} {bekannteEuro.length > 0 ? <span title={euro.format(euroSumme)}>{(Math.abs(euroSumme) >= 1e6 ? euroKurz : euroGanz).format(euroSumme)}</span> : <Unbekannt />}
        {echteAnzahl > 0 && euroUnbekannt > 0 && <> ({t("unknown for {a} of {b} findings", { a: euroUnbekannt, b: echteAnzahl })})</>}
      </p>

      <div className={styles.reiter} role="tablist" aria-label={t("Report sections")}>
        {([
          ["uebersicht", "Overview", null, "gauge"],
          ["findings", "Findings", findings.length, "alert"],
          ["positionen", "Items", lv.positionen.length, "steps"],
          ["preise", "Prices", null, "price"],
          ["fragen", "Bidder questions", null, "help"],
          ["mengen", "Quantities", null, "chart"],
        ] as [Reiter, string, number | null, IconName][]).map(([wert, name, n, icon]) => (
          <button key={wert} type="button" role="tab" aria-selected={reiter === wert}
            className={`${styles.reiterKnopf} ${reiter === wert ? styles.reiterAktiv : ""}`} onClick={() => setReiter(wert)}>
            <Icon name={icon} />{t(name)}{n !== null && <span className={styles.anzahl}> {zahl.format(n)}</span>}
          </button>
        ))}
      </div>

      {reiter === "uebersicht" && (
        <>
          <Einschaetzung daten={bewertung} onAmpel={(a) => {
            if (a === "gruen") { setReiter("positionen"); return; }
            setSchwere(a === "gelb" ? "mittel" : null);
            setReiter("findings");
          }} />
          <Top findings={findings} positionen={lv.positionen} onWaehle={(oz, id) => {
            setReiter("findings");
            waehle(oz, id);
            requestAnimationFrame(() => { detailRef.current?.scrollIntoView({ block: "nearest" }); detailRef.current?.focus({ preventScroll: true }); });
          }} />
        </>
      )}

      {reiter === "preise" && <Preisspiegel positionen={lv.positionen} onWaehle={(oz) => { setReiter("positionen"); waehle(oz, null); }} />}

      {reiter === "fragen" && <Bieterfragen findings={findings} positionen={lv.positionen} />}

      {reiter === "mengen" && <Mengen positionen={lv.positionen} aktiv={einheit} onWaehle={waehleEinheit} />}

      {(reiter === "findings" || reiter === "positionen") && (<>
      <Titelbaum baum={titelbaum} aktiv={titel} onWaehle={waehleTitel} />

      <Suche wert={suche} onAendern={sucheAendern} zaehler={sucheAktiv
        ? t("{a} of {b} items · {c} of {d} findings", { a: sichtbarePositionen.length, b: lv.positionen.length, c: gefiltert.length, d: findings.length })
        : null} />

      {reiter === "findings" && (
      <details className={styles.filterKlappe} open={filterAktiv || undefined}>
      <summary>{t("Filter findings")}{filterAktiv ? ` (${t("active")})` : ""}</summary>
      <div className={styles.filter} role="group" aria-label={t("Filter findings")}>
        <fieldset className={styles.filterGruppe}>
          <legend>{t("Category")}</legend>
          <FilterKnopf aktiv={kategorie === null} onClick={() => setKategorie(null)}>
            {t("All")} <span className={styles.anzahl}>{findings.length}</span>
          </FilterKnopf>
          {KATEGORIEN.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={kategorie === wert} onClick={() => setKategorie(wert)}>
              {t(name)} <span className={styles.anzahl}>{findings.filter((f) => f.kategorie === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
        <fieldset className={styles.filterGruppe}>
          <legend>{t("Severity")}</legend>
          <FilterKnopf aktiv={schwere === null} onClick={() => setSchwere(null)}>{t("All")}</FilterKnopf>
          {SCHWEREN.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={schwere === wert} onClick={() => setSchwere(wert)}>
              <span className={`${styles.punkt} ${styles[`schwere_${wert}`]}`} aria-hidden="true" />
              {t(name)} <span className={styles.anzahl}>{findings.filter((f) => f.schwere === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
        <fieldset className={styles.filterGruppe}>
          <legend>{t("Review")}</legend>
          <FilterKnopf aktiv={status === null} onClick={() => setStatus(null)}>{t("All")}</FilterKnopf>
          {STATUS.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={status === wert} onClick={() => setStatus(wert)}>
              {t(name)} <span className={styles.anzahl}>{findings.filter((f) => bewertungVon(bewertungen, f.id).status === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
      </div>
      </details>
      )}

      <div className={`${styles.layout} ${auswahl ? styles.mitDetail : ""}`}>
        <div className={styles.liste}>
          {reiter === "findings" && (<>
          <h3 ref={findingsAnfangRef} className={styles.abschnitt}>
            {t("Findings")} <span className={styles.anzahl} aria-live="polite">{t("{a} of {b}", { a: gefiltert.length, b: findings.length })}</span>
          </h3>
          {findings.length === 0 ? (
            <div className={styles.leer}>
              <p><strong>{t("No findings.")}</strong> {t("The review reported no issues for this BoQ.")}</p>
              <p>{t("This does not guarantee an error-free BoQ: only the available review rules were applied.")}</p>
            </div>
          ) : gefiltert.length === 0 ? (
            <div className={styles.leer}>
              <p>{t("No findings match this filter.")}</p>
              {filterAktiv && (
                <button type="button" className={styles.knopfZweit} onClick={() => { setKategorie(null); setSchwere(null); setStatus(null); setTitel(null); setSuche(""); }}>
                  {t("Reset filters")}
                </button>
              )}
            </div>
          ) : (
            <>
            {findingsSteuerung(t("Findings pages"), false)}
            <ul className={styles.findings}>
              {sichtbareFindings.map((finding) => (
                <li key={finding.id}>
                  <MitStatus status={bewertungVon(bewertungen, finding.id).status} titel={finding.titel}
                    onAendern={(s) => bewerte(finding.id, { status: s })}>
                    <FindingKarte
                      finding={finding}
                      gewaehlt={auswahl?.findingId === finding.id}
                      ozBekannt={positionenNachOz.has(finding.oz)}
                      onWaehle={() => waehle(finding.oz, finding.id)}
                    />
                  </MitStatus>
                </li>
              ))}
            </ul>
            {sichtbareFindings.length > 10 && findingsSteuerung(t("Findings pages, bottom"), true)}
            </>
          )}

          </>)}

          {reiter === "positionen" && (
          <section ref={positionenRef} className={styles.positionen}>
            <h3 className={styles.abschnitt}>
              {einheit === null && titel === null && !sucheAktiv
                ? t("All {n} items", { n: zahl.format(lv.positionen.length) })
                : `${t("Showing {a} of {b} items", { a: sichtbarePositionen.length, b: lv.positionen.length })}${titel === null ? "" : ` ${t("under")} “${titel.length === 0 ? OHNE_TITEL_NAME : titel.join(" › ")}”`}${einheit === null ? "" : ` ${t("summed in")} ${lv.positionen.find((p) => mengenSchluessel(p) === einheit)?.einheit?.trim() ?? einheit}`}${sucheAktiv ? ` ${t("matching")} “${suche.trim()}”` : ""}`}
            </h3>
            {(einheit !== null || titel !== null || sucheAktiv) && (
              <button type="button" className={styles.knopfZweit} onClick={() => { setEinheit(null); setTitel(null); setSuche(""); }}>{t("Show all items")}</button>
            )}
            {lv.positionen.length === 0 ? (
              <p className={styles.leer}>{t("The BoQ contains no items.")}</p>
            ) : sichtbarePositionen.length === 0 ? (
              <p className={styles.leer}>{t("No positions match.")}</p>
            ) : (
              <>
              {positionenSteuerung(t("Item pages"), false)}
              <div className={styles.tabelleRahmen}>
                <table className={styles.tabelle}>
                  <thead>
                    <tr>
                      <th scope="col">OZ</th><th scope="col">{t("Short description")}</th><th scope="col" className={styles.rechts}>{t("Quantity")}</th>
                      <th scope="col" className={styles.rechts}>{t("Unit price")}</th><th scope="col" className={styles.rechts}>{t("Total price")}</th>
                      <th scope="col" className={styles.rechts}>{t("Findings")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seitenPositionen.map((position, index) => (
                      <tr key={`${position.oz}-${positionSeite.von + index}`} className={auswahl?.oz === position.oz ? styles.zeileGewaehlt : undefined}
                        style={gefahr(findingsNachOz.get(position.oz))}>
                        <td>
                          <button type="button" className={styles.ozKnopf} onClick={() => waehle(position.oz, null, false)}
                            aria-label={t("Show item {oz}", { oz: position.oz })}>
                            {position.oz}
                          </button>
                        </td>
                        <td title={position.kurztext}>{d(position.kurztext) || <Unbekannt />}</td>
                        <td className={`${styles.rechts} ${styles.umbruch}`}><Menge menge={position.menge} einheit={position.einheit} /></td>
                        <td className={styles.rechts}><Euro wert={position.ep} /></td>
                        <td className={styles.rechts}><Euro wert={position.gp} /></td>
                        <td className={styles.rechts}>{findingsNachOz.get(position.oz)?.length ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {seitenPositionen.length > 10 && positionenSteuerung(t("Item pages, bottom"), true)}
              </>
            )}
          </section>
          )}
        </div>

        {auswahl && (
        <aside ref={detailRef} className={styles.detail} tabIndex={-1} aria-labelledby="pruefbericht-detail-titel">
            <Detail
              oz={auswahl.oz}
              findingId={auswahl.findingId}
              positionen={positionenNachOz.get(auswahl.oz) ?? []}
              findings={findingsNachOz.get(auswahl.oz) ?? []}
              onWaehle={(id) => waehle(auswahl.oz, id)}
              onSchliessen={() => setAuswahl(null)}
              bewertungen={bewertungen}
              onBewerte={bewerte}
              speicherFehler={speicherFehler}
              schritt={schrittIndex < 0 ? null : { index: schrittIndex, gesamt: schrittListe.length, onSchritt: schritt }}
            />
        </aside>
        )}
      </div>
      </>)}
    </section>
  );
}

function FilterKnopf({ aktiv, onClick, children }: { aktiv: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" className={`${styles.chip} ${aktiv ? styles.chipAktiv : ""}`} aria-pressed={aktiv} onClick={onClick}>
      {children}
    </button>
  );
}

function Merkmale({ finding }: { finding: Finding }) {
  const t = useT();
  return (
    <span className={styles.merkmale}>
      <span className={`${styles.schwere} ${styles[`schwere_${finding.schwere}`]}`}>{t(schwereName(finding.schwere))}</span>
      <span className={styles.marke}>{t(kategorieName(finding.kategorie))}</span>
      <span className={styles.marke}>{t(finding.quelle === "regel" ? "Rule" : "Model")} · {finding.regel_id}</span>
      {istMock(finding) && <span className={styles.markeMock}>{t("Demonstration")}</span>}
    </span>
  );
}

function FindingKarte({ finding, gewaehlt, ozBekannt, onWaehle }: {
  finding: Finding; gewaehlt: boolean; ozBekannt: boolean; onWaehle: () => void;
}) {
  const t = useT();
  return (
    <button type="button" className={`${styles.karte} ${gewaehlt ? styles.karteGewaehlt : ""} ${istMock(finding) ? styles.karteMock : ""}`}
      aria-pressed={gewaehlt} onClick={onWaehle} style={gefahr([finding])}>
      <span className={`${styles.schwere} ${styles[`schwere_${finding.schwere}`]}`}>{t(schwereName(finding.schwere))}</span>
      <span className={styles.oz}>{finding.oz}{!ozBekannt && <small> ({t("not in BoQ")})</small>}</span>
      <span className={styles.zeileText}>
        <span className={styles.karteTitel}>{finding.titel}</span>
        <span className={styles.zeileMeta}>{t(kategorieName(finding.kategorie))} · {t(finding.quelle === "regel" ? "Rule" : "Model")} · {finding.regel_id}
          {istMock(finding) && <> · <b className={styles.markeMock}>{t("Demonstration")}</b></>}</span>
      </span>
      <span className={styles.zeileEuro}><Euro wert={finding.euro_wirkung} /></span>
    </button>
  );
}

function Detail({ oz, findingId, positionen, findings, onWaehle, onSchliessen, bewertungen, onBewerte, speicherFehler, schritt }: {
  oz: string; findingId: string | null; positionen: Position[]; findings: Finding[];
  onWaehle: (id: string) => void; onSchliessen: () => void;
  bewertungen: Bewertungen; onBewerte: (id: string, a: Partial<BewertungDaten>) => void; speicherFehler: boolean;
  schritt: { index: number; gesamt: number; onSchritt: (d: number) => void } | null;
}) {
  const d = useDok();
  const t = useT();
  const gewaehlt = findings.find((f) => f.id === findingId) ?? null;
  const weitere = findings.filter((f) => f.id !== findingId);
  return (
    <div>
      <div className={styles.detailKopf}>
        <h3 id="pruefbericht-detail-titel" className={styles.abschnitt}>OZ <span className={styles.oz}>{oz}</span></h3>
        {schritt && (
          <div className={styles.schritte} role="group" aria-label={t("Step through")}>
            <button type="button" className={styles.schrittKnopf} disabled={schritt.index === 0} onClick={() => schritt.onSchritt(-1)}
              aria-label={t("Previous")} title={`${t("Previous")} (← ↑)`}>‹</button>
            <span className={styles.schrittStand}>{(schritt.index + 1).toLocaleString("en-GB")} / {schritt.gesamt.toLocaleString("en-GB")}</span>
            <button type="button" className={styles.schrittKnopf} disabled={schritt.index >= schritt.gesamt - 1} onClick={() => schritt.onSchritt(1)}
              aria-label={t("Next")} title={`${t("Next")} (→ ↓)`}>›</button>
          </div>
        )}
        <button type="button" className={styles.schliessen} onClick={onSchliessen} aria-label={t("Close details")}>×</button>
      </div>

      {gewaehlt && (
        <article className={`${styles.befund} ${istMock(gewaehlt) ? styles.karteMock : ""}`}>
          <Merkmale finding={gewaehlt} />
          <h4>{gewaehlt.titel}</h4>
          <dl className={styles.felder}>
            <dt>{t("Explanation")}</dt><dd>{gewaehlt.begruendung || <Unbekannt />}</dd>
            <dt>{t("Suggestion")}</dt><dd>{gewaehlt.vorschlag || <Unbekannt />}</dd>
            <dt>{t("Euro impact")}</dt><dd><Euro wert={gewaehlt.euro_wirkung} /></dd>
            <dt>{t("Source")}</dt><dd>{t(gewaehlt.quelle === "regel" ? "Fixed review rule" : "Model")} ({gewaehlt.regel_id})</dd>
          </dl>
          <Bewertung key={gewaehlt.id} bewertung={bewertungVon(bewertungen, gewaehlt.id)}
            onAendern={(a) => onBewerte(gewaehlt.id, a)} speicherFehler={speicherFehler} />
        </article>
      )}

      {weitere.length > 0 && (
        <div className={styles.weitere}>
          <p>{t(gewaehlt ? "Other findings for this item number:" : "Findings for this item number:")}</p>
          <ul>
            {weitere.map((f) => (
              <li key={f.id}>
                <button type="button" className={styles.linkKnopf} onClick={() => onWaehle(f.id)}>
                  {t(schwereName(f.schwere))} · {f.titel}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {!gewaehlt && findings.length === 0 && <p className={styles.hinweis}>{t("No findings for this item number.")}</p>}

      {positionen.length === 0 ? (
        <p className={styles.fehler}>{t("This item number does not exist in the BoQ. The finding cannot be linked to an original item.")}</p>
      ) : (
        <>
          {positionen.length > 1 && (
            <p className={styles.warnung}>{t("Item number {oz} occurs {n} times. All original items:", { oz, n: positionen.length })}</p>
          )}
          {positionen.map((position, index) => (
            <article key={index} className={styles.position}>
              <p className={styles.pfad}>{position.titel_pfad.length > 0 ? position.titel_pfad.map((x) => d(x)).join(" / ") : t("no section")}</p>
              <h4 title={position.kurztext}>{d(position.kurztext) || <Unbekannt />}</h4>
              {position.langtext ? (
                <details className={styles.langtextKlappe}>
                  <summary>{t("Detailed description")}</summary>
                  <p className={styles.langtext} title={position.langtext}>{d(position.langtext)}</p>
                </details>
              ) : <p className={styles.unbekannt}>{t("No detailed description supplied.")}</p>}
              <dl className={styles.werte}>
                <div><dt>{t("Quantity")}</dt><dd><Menge menge={position.menge} einheit={position.einheit} /></dd></div>
                <div><dt>{t("Unit price")}</dt><dd><Euro wert={position.ep} /></dd></div>
                <div><dt>{t("Total price")}</dt><dd><Euro wert={position.gp} /></dd></div>
                <div><dt>{t("Type")}</dt><dd>{t(TYP_NAME[position.typ] ?? position.typ)}</dd></div>
              </dl>
            </article>
          ))}
          <Historie key={oz} oz={oz} kurztext={positionen[0].kurztext} />
        </>
      )}
    </div>
  );
}

export default Pruefbericht;
