"use client";

import { useMemo, useRef, useState } from "react";
import type { Finding, Position, Pruefbericht as PruefberichtDaten } from "@/lib/api";
import styles from "./pruefbericht.module.css";

/**
 * Übergabe an die Exportseite (/export, Folgeauftrag #15):
 * Vor dem Wechsel nach /export schreibt der Bericht den aktuell angezeigten
 * `Pruefbericht` unverändert als JSON (`JSON.stringify(bericht)`) unter diesem
 * sessionStorage-Schlüssel. Der JSON-Download enthält genau dasselbe Objekt,
 * sodass /export beide Wege gleich einlesen kann. Format: Typ `Pruefbericht`
 * aus web/lib/api.ts, ohne Hülle. Ein neues Format bekommt einen neuen Schlüssel.
 */
export const PRUEFBERICHT_SPEICHER_SCHLUESSEL = "lv-pruefbericht-v1";

const MOCK_REGEL = "MOCK_LLM";

type Kategorie = Finding["kategorie"];
type Schwere = Finding["schwere"];

const KATEGORIEN: { wert: Kategorie; name: string }[] = [
  { wert: "fehler", name: "Fehler" },
  { wert: "risiko", name: "Risiko" },
  { wert: "nachtrag", name: "Nachtrag" },
];
const SCHWEREN: { wert: Schwere; name: string }[] = [
  { wert: "kritisch", name: "Kritisch" },
  { wert: "hoch", name: "Hoch" },
  { wert: "mittel", name: "Mittel" },
  { wert: "niedrig", name: "Niedrig" },
];
const SCHWERE_RANG: Record<Schwere, number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const TYP_NAME: Record<Position["typ"], string> = {
  normal: "Normalposition", bedarf: "Bedarfsposition", alternativ: "Alternativposition",
  zulage: "Zulageposition", pauschal: "Pauschalposition", stundenlohn: "Stundenlohnposition",
};

const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const zahl = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3 });

function istMock(finding: Finding) {
  return finding.regel_id === MOCK_REGEL;
}

function kategorieName(wert: Kategorie) {
  return KATEGORIEN.find((k) => k.wert === wert)?.name ?? wert;
}

function schwereName(wert: Schwere) {
  return SCHWEREN.find((s) => s.wert === wert)?.name ?? wert;
}

function Unbekannt() {
  return <span className={styles.unbekannt}>unbekannt</span>;
}

function Euro({ wert }: { wert: number | null }) {
  return wert === null ? <Unbekannt /> : <>{euro.format(wert)}</>;
}

function Menge({ menge, einheit }: { menge: number | null; einheit: string | null }) {
  return (
    <>
      {menge === null ? <Unbekannt /> : zahl.format(menge)}{" "}
      {einheit ? einheit : <span className={styles.unbekannt}>(Einheit unbekannt)</span>}
    </>
  );
}

function dateiname(name: string) {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `pruefbericht-${basis || "lv"}.json`;
}

type Auswahl = { oz: string; findingId: string | null };

export function Pruefbericht({ bericht }: { bericht: PruefberichtDaten }) {
  const { lv, findings, kennzahlen } = bericht;
  const [kategorie, setKategorie] = useState<Kategorie | null>(null);
  const [schwere, setSchwere] = useState<Schwere | null>(null);
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [exportFehler, setExportFehler] = useState("");
  const detailRef = useRef<HTMLElement>(null);

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
  const gefiltert = sortiert.filter(
    (f) => (kategorie === null || f.kategorie === kategorie) && (schwere === null || f.schwere === schwere),
  );

  const mockAnzahl = findings.filter(istMock).length;
  const echteAnzahl = findings.length - mockAnzahl;
  const bekannteEuro = findings.filter((f) => !istMock(f) && f.euro_wirkung !== null);
  const euroSumme = bekannteEuro.reduce((summe, f) => summe + (f.euro_wirkung ?? 0), 0);
  const euroUnbekannt = echteAnzahl - bekannteEuro.length;
  const doppelteOz = [...positionenNachOz.values()].filter((liste) => liste.length > 1).length;

  function waehle(oz: string, findingId: string | null) {
    setAuswahl({ oz, findingId });
    // Auf schmalen Bildschirmen steht das Detail unter der Liste: dorthin springen.
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
      setExportFehler("Der Bericht konnte nicht an die Exportseite übergeben werden (Browserspeicher gesperrt). Bitte stattdessen den JSON-Download nutzen.");
    }
  }

  const filterAktiv = kategorie !== null || schwere !== null;

  return (
    <section className={styles.bericht} aria-labelledby="pruefbericht-titel">
      <header className={styles.kopf}>
        <div>
          <p className={styles.kicker}>Prüfbericht</p>
          <h2 id="pruefbericht-titel" className={styles.titel}>{lv.name || "Unbenanntes LV"}</h2>
          <p className={styles.quelle}>Quelle: {lv.quelle || <Unbekannt />}</p>
        </div>
        <div className={styles.aktionen}>
          <button type="button" className={styles.knopf} onClick={herunterladen}>JSON herunterladen</button>
          <a className={styles.knopfZweit} href="/export" onClick={zumExport}>Zum Export</a>
        </div>
      </header>
      {exportFehler && <p className={styles.fehler} role="alert">{exportFehler}</p>}

      {kennzahlen.modell_mock && (
        <p className={styles.mockHinweis} role="note">
          <strong>Demonstrationsmodus:</strong> Die Modellprüfung läuft als Offline-Mock. Einträge mit
          der Kennung <code>{MOCK_REGEL}</code> zeigen nur das Berichtsformat und sind keine fachlichen Befunde.
        </p>
      )}

      <dl className={styles.kennzahlen}>
        <div className={styles.kachel}>
          <dt>Positionen</dt>
          <dd>{zahl.format(kennzahlen.positionen)}</dd>
          {doppelteOz > 0 && <small>{doppelteOz} OZ mehrfach vergeben</small>}
        </div>
        <div className={styles.kachel}>
          <dt>Einträge</dt>
          <dd>{zahl.format(kennzahlen.findings)}</dd>
          <small>{findings.length === 0 ? "keine Einträge" : mockAnzahl > 0 ? `davon ${mockAnzahl} Demonstration` : "alle aus der Prüfung"}</small>
        </div>
        <div className={`${styles.kachel} ${kennzahlen.kritisch > 0 ? styles.kachelKritisch : ""}`}>
          <dt>Kritisch</dt>
          <dd>{zahl.format(kennzahlen.kritisch)}</dd>
        </div>
        <div className={styles.kachel}>
          <dt>Belegte Euro-Wirkung</dt>
          <dd>{bekannteEuro.length > 0 ? euro.format(euroSumme) : <Unbekannt />}</dd>
          <small>
            {echteAnzahl === 0
              ? "keine fachlichen Befunde"
              : euroUnbekannt > 0
                ? `bei ${euroUnbekannt} von ${echteAnzahl} Befunden unbekannt`
                : "aus allen Befunden belegt"}
          </small>
        </div>
      </dl>

      <div className={styles.filter} role="group" aria-label="Befunde filtern">
        <fieldset className={styles.filterGruppe}>
          <legend>Kategorie</legend>
          <FilterKnopf aktiv={kategorie === null} onClick={() => setKategorie(null)}>
            Alle <span className={styles.anzahl}>{findings.length}</span>
          </FilterKnopf>
          {KATEGORIEN.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={kategorie === wert} onClick={() => setKategorie(wert)}>
              {name} <span className={styles.anzahl}>{findings.filter((f) => f.kategorie === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
        <fieldset className={styles.filterGruppe}>
          <legend>Schwere</legend>
          <FilterKnopf aktiv={schwere === null} onClick={() => setSchwere(null)}>Alle</FilterKnopf>
          {SCHWEREN.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={schwere === wert} onClick={() => setSchwere(wert)}>
              <span className={`${styles.punkt} ${styles[`schwere_${wert}`]}`} aria-hidden="true" />
              {name} <span className={styles.anzahl}>{findings.filter((f) => f.schwere === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
      </div>

      <div className={styles.layout}>
        <div className={styles.liste}>
          <h3 className={styles.abschnitt}>
            Befunde <span className={styles.anzahl} aria-live="polite">{gefiltert.length} von {findings.length}</span>
          </h3>
          {findings.length === 0 ? (
            <div className={styles.leer}>
              <p><strong>Keine Befunde.</strong> Die Prüfung hat für dieses LV keine Auffälligkeiten gemeldet.</p>
              <p>Das heißt nicht, dass das LV fehlerfrei ist: Es wurden nur die vorhandenen Prüfregeln angewendet.</p>
            </div>
          ) : gefiltert.length === 0 ? (
            <div className={styles.leer}>
              <p>Kein Befund passt zu diesem Filter.</p>
              {filterAktiv && (
                <button type="button" className={styles.knopfZweit} onClick={() => { setKategorie(null); setSchwere(null); }}>
                  Filter zurücksetzen
                </button>
              )}
            </div>
          ) : (
            <ul className={styles.findings}>
              {gefiltert.map((finding) => (
                <li key={finding.id}>
                  <FindingKarte
                    finding={finding}
                    gewaehlt={auswahl?.findingId === finding.id}
                    ozBekannt={positionenNachOz.has(finding.oz)}
                    onWaehle={() => waehle(finding.oz, finding.id)}
                  />
                </li>
              ))}
            </ul>
          )}

          <details className={styles.positionen}>
            <summary>Alle {lv.positionen.length} Positionen anzeigen</summary>
            {lv.positionen.length === 0 ? (
              <p className={styles.leer}>Das LV enthält keine Positionen.</p>
            ) : (
              <div className={styles.tabelleRahmen}>
                <table className={styles.tabelle}>
                  <thead>
                    <tr>
                      <th scope="col">OZ</th><th scope="col">Kurztext</th><th scope="col" className={styles.rechts}>Menge</th>
                      <th scope="col" className={styles.rechts}>EP</th><th scope="col" className={styles.rechts}>GP</th>
                      <th scope="col" className={styles.rechts}>Befunde</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lv.positionen.map((position, index) => (
                      <tr key={`${position.oz}-${index}`} className={auswahl?.oz === position.oz ? styles.zeileGewaehlt : undefined}>
                        <td>
                          <button type="button" className={styles.ozKnopf} onClick={() => waehle(position.oz, null)}
                            aria-label={`Position ${position.oz} anzeigen`}>
                            {position.oz}
                          </button>
                        </td>
                        <td>{position.kurztext || <Unbekannt />}</td>
                        <td className={`${styles.rechts} ${styles.umbruch}`}><Menge menge={position.menge} einheit={position.einheit} /></td>
                        <td className={styles.rechts}><Euro wert={position.ep} /></td>
                        <td className={styles.rechts}><Euro wert={position.gp} /></td>
                        <td className={styles.rechts}>{findingsNachOz.get(position.oz)?.length ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        </div>

        <aside ref={detailRef} className={styles.detail} tabIndex={-1} aria-labelledby="pruefbericht-detail-titel">
          {auswahl ? (
            <Detail
              oz={auswahl.oz}
              findingId={auswahl.findingId}
              positionen={positionenNachOz.get(auswahl.oz) ?? []}
              findings={findingsNachOz.get(auswahl.oz) ?? []}
              onWaehle={(id) => waehle(auswahl.oz, id)}
              onSchliessen={() => setAuswahl(null)}
            />
          ) : (
            <div className={styles.detailLeer}>
              <h3 id="pruefbericht-detail-titel" className={styles.abschnitt}>Details</h3>
              <p>Befund oder OZ wählen, um Kurztext, Langtext, Begründung und Vorschlag zu sehen.</p>
            </div>
          )}
        </aside>
      </div>
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
  return (
    <span className={styles.merkmale}>
      <span className={`${styles.schwere} ${styles[`schwere_${finding.schwere}`]}`}>{schwereName(finding.schwere)}</span>
      <span className={styles.marke}>{kategorieName(finding.kategorie)}</span>
      <span className={styles.marke}>{finding.quelle === "regel" ? "Regel" : "Modell"} · {finding.regel_id}</span>
      {istMock(finding) && <span className={styles.markeMock}>Demonstration</span>}
    </span>
  );
}

function FindingKarte({ finding, gewaehlt, ozBekannt, onWaehle }: {
  finding: Finding; gewaehlt: boolean; ozBekannt: boolean; onWaehle: () => void;
}) {
  return (
    <button type="button" className={`${styles.karte} ${gewaehlt ? styles.karteGewaehlt : ""} ${istMock(finding) ? styles.karteMock : ""}`}
      aria-pressed={gewaehlt} onClick={onWaehle}>
      <Merkmale finding={finding} />
      <span className={styles.karteTitel}>{finding.titel}</span>
      <span className={styles.karteFuss}>
        <span>OZ <span className={styles.oz}>{finding.oz}</span>{!ozBekannt && " (nicht im LV)"}</span>
        <span>Euro-Wirkung: <Euro wert={finding.euro_wirkung} /></span>
      </span>
    </button>
  );
}

function Detail({ oz, findingId, positionen, findings, onWaehle, onSchliessen }: {
  oz: string; findingId: string | null; positionen: Position[]; findings: Finding[];
  onWaehle: (id: string) => void; onSchliessen: () => void;
}) {
  const gewaehlt = findings.find((f) => f.id === findingId) ?? null;
  const weitere = findings.filter((f) => f.id !== findingId);
  return (
    <div>
      <div className={styles.detailKopf}>
        <h3 id="pruefbericht-detail-titel" className={styles.abschnitt}>OZ <span className={styles.oz}>{oz}</span></h3>
        <button type="button" className={styles.schliessen} onClick={onSchliessen} aria-label="Details schließen">×</button>
      </div>

      {gewaehlt && (
        <article className={`${styles.befund} ${istMock(gewaehlt) ? styles.karteMock : ""}`}>
          <Merkmale finding={gewaehlt} />
          <h4>{gewaehlt.titel}</h4>
          <dl className={styles.felder}>
            <dt>Begründung</dt><dd>{gewaehlt.begruendung || <Unbekannt />}</dd>
            <dt>Vorschlag</dt><dd>{gewaehlt.vorschlag || <Unbekannt />}</dd>
            <dt>Euro-Wirkung</dt><dd><Euro wert={gewaehlt.euro_wirkung} /></dd>
            <dt>Quelle</dt><dd>{gewaehlt.quelle === "regel" ? "Feste Prüfregel" : "Modell"} ({gewaehlt.regel_id})</dd>
          </dl>
        </article>
      )}

      {weitere.length > 0 && (
        <div className={styles.weitere}>
          <p>{gewaehlt ? "Weitere Befunde zu dieser OZ:" : "Befunde zu dieser OZ:"}</p>
          <ul>
            {weitere.map((f) => (
              <li key={f.id}>
                <button type="button" className={styles.linkKnopf} onClick={() => onWaehle(f.id)}>
                  {schwereName(f.schwere)} · {f.titel}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {!gewaehlt && findings.length === 0 && <p className={styles.hinweis}>Zu dieser OZ gibt es keine Befunde.</p>}

      {positionen.length === 0 ? (
        <p className={styles.fehler}>Diese OZ kommt im LV nicht vor. Der Befund lässt sich keiner Originalposition zuordnen.</p>
      ) : (
        <>
          {positionen.length > 1 && (
            <p className={styles.warnung}>Die OZ {oz} ist {positionen.length}-mal vergeben. Alle Originalpositionen:</p>
          )}
          {positionen.map((position, index) => (
            <article key={index} className={styles.position}>
              <p className={styles.pfad}>{position.titel_pfad.length > 0 ? position.titel_pfad.join(" / ") : "ohne Titel"}</p>
              <h4>{position.kurztext || <Unbekannt />}</h4>
              <p className={styles.langtext}>
                {position.langtext ? position.langtext : <span className={styles.unbekannt}>Kein Langtext angegeben.</span>}
              </p>
              <dl className={styles.werte}>
                <div><dt>Menge</dt><dd><Menge menge={position.menge} einheit={position.einheit} /></dd></div>
                <div><dt>EP</dt><dd><Euro wert={position.ep} /></dd></div>
                <div><dt>GP</dt><dd><Euro wert={position.gp} /></dd></div>
                <div><dt>Art</dt><dd>{TYP_NAME[position.typ] ?? position.typ}</dd></div>
              </dl>
            </article>
          ))}
        </>
      )}
    </div>
  );
}

export default Pruefbericht;
