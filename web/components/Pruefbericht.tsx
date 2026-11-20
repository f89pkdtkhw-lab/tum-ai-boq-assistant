"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Finding, Position, Pruefbericht as PruefberichtDaten } from "@/lib/api";
import { mengenSchluessel } from "@/lib/mengen";
import { baueTitelbaum, imTeilbaum, OHNE_TITEL_NAME, ozImTeilbaum } from "@/lib/titelbaum";
import { filtereFindings, normalisiere, positionTrifft } from "@/lib/suche";
import {
  anzahlGeprueft, bewertungVon, ladeBewertungen, setze, speichereBewertungen, STATUS,
  type Bewertung as BewertungDaten, type Bewertungen, type Status,
} from "@/lib/bewertung";
import { Bewertung, MitStatus } from "./bewertung/Bewertung";
import { Mengen } from "./mengen/Mengen";
import { Bieterfragen } from "./bieterfragen/Bieterfragen";
import { Suche } from "./suche/Suche";
import { Titelbaum } from "./titelbaum/Titelbaum";
import { Top } from "./top/Top";
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
  return <span className={styles.unbekannt}>unknown</span>;
}

function Euro({ wert }: { wert: number | null }) {
  return wert === null ? <Unbekannt /> : <>{euro.format(wert)}</>;
}

function Menge({ menge, einheit }: { menge: number | null; einheit: string | null }) {
  return (
    <>
      {menge === null ? <Unbekannt /> : zahl.format(menge)}{" "}
      {einheit ? einheit : <span className={styles.unbekannt}>(unit unknown)</span>}
    </>
  );
}

function dateiname(name: string) {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `pruefbericht-${basis || "lv"}.json`;
}

type Auswahl = { oz: string; findingId: string | null };

export function Pruefbericht({ bericht, offline = false }: { bericht: PruefberichtDaten; offline?: boolean }) {
  const { lv, findings, kennzahlen } = bericht;
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
  const detailRef = useRef<HTMLElement>(null);
  const positionenRef = useRef<HTMLDetailsElement>(null);

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

  function waehle(oz: string, findingId: string | null) {
    setAuswahl({ oz, findingId });
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
      setExportFehler("Could not pass the report to the export page (browser storage blocked). Please use the JSON download.");
    }
  }

  const sucheAktiv = normalisiere(suche) !== "";
  const filterAktiv = kategorie !== null || schwere !== null || status !== null || titel !== null || sucheAktiv;
  const sichtbarePositionen = lv.positionen.filter(
    (p) => (einheit === null || mengenSchluessel(p) === einheit) && (titel === null || imTeilbaum(p, titel)) && positionTrifft(p, suche),
  );

  function sucheAendern(wert: string) {
    setSuche(wert);
    if (normalisiere(wert) !== "" && positionenRef.current) positionenRef.current.open = true;
  }

  function waehleTitel(pfad: string[] | null) {
    setTitel(pfad);
    if (pfad !== null && positionenRef.current) positionenRef.current.open = true;
  }

  function waehleEinheit(schluessel: string | null) {
    setEinheit(schluessel);
    if (schluessel !== null && positionenRef.current) positionenRef.current.open = true;
  }

  return (
    <section className={styles.bericht} aria-labelledby="pruefbericht-titel">
      <header className={styles.kopf}>
        <div>
          <p className={styles.kicker}>Review report</p>
          <h2 id="pruefbericht-titel" className={styles.titel}>{lv.name || "Unnamed BoQ"}</h2>
          <p className={styles.quelle}>Source: {lv.quelle || <Unbekannt />}</p>
        </div>
        <div className={styles.aktionen}>
          <button type="button" className={styles.knopf} onClick={herunterladen}>Download JSON</button>
          <a className={styles.knopfZweit} href="/export" onClick={zumExport}>Export report</a>
        </div>
      </header>
      {exportFehler && <p className={styles.fehler} role="alert">{exportFehler}</p>}

      {offline && (
        <p className={styles.offlineHinweis} role="note">
          <strong>Offline example – not live analysis.</strong> The backend is unreachable; this is a saved report for the synthetic example BoQ.
        </p>
      )}

      {kennzahlen.modell_mock && (
        <p className={styles.mockHinweis} role="note">
          <strong>Demo mode:</strong> The model review runs as an offline mock. Entries with
          the identifier <code>{MOCK_REGEL}</code> only demonstrate the report format and are not domain findings.
        </p>
      )}

      <dl className={styles.kennzahlen}>
        <div className={styles.kachel}>
          <dt>Items</dt>
          <dd>{zahl.format(kennzahlen.positionen)}</dd>
          {doppelteOz > 0 && <small>{doppelteOz} duplicate item numbers</small>}
        </div>
        <div className={styles.kachel}>
          <dt>Entries</dt>
          <dd>{zahl.format(kennzahlen.findings)}</dd>
          <small>{findings.length === 0 ? "no entries" : mockAnzahl > 0 ? `including ${mockAnzahl} demo entries` : "all from the review"}</small>
        </div>
        <div className={`${styles.kachel} ${kennzahlen.kritisch > 0 ? styles.kachelKritisch : ""}`}>
          <dt>Critical</dt>
          <dd>{zahl.format(kennzahlen.kritisch)}</dd>
        </div>
        <div className={styles.kachel}>
          <dt>Reviewed</dt>
          <dd>{zahl.format(geprueft)} <small className={styles.anzahl}>of {zahl.format(findings.length)}</small></dd>
          <small>{findings.length === 0 ? "nothing to review" : geprueft === findings.length ? "all findings reviewed" : `${findings.length - geprueft} still open`}</small>
        </div>
        <div className={styles.kachel}>
          <dt>Evidenced euro impact</dt>
          <dd>{bekannteEuro.length > 0 ? euro.format(euroSumme) : <Unbekannt />}</dd>
          <small>
            {echteAnzahl === 0
              ? "no domain findings"
              : euroUnbekannt > 0
                ? `unknown for ${euroUnbekannt} of ${echteAnzahl} findings`
                : "evidenced across all findings"}
          </small>
        </div>
      </dl>

      <Top findings={findings} positionen={lv.positionen} onWaehle={(oz, id) => {
        waehle(oz, id);
        // The panel sits above the list, so the detail is off-screen on wide layouts too.
        requestAnimationFrame(() => { detailRef.current?.scrollIntoView({ block: "nearest" }); detailRef.current?.focus({ preventScroll: true }); });
      }} />

      <Bieterfragen findings={findings} positionen={lv.positionen} />

      <Mengen positionen={lv.positionen} aktiv={einheit} onWaehle={waehleEinheit} />

      <Titelbaum baum={titelbaum} aktiv={titel} onWaehle={waehleTitel} />

      <Suche wert={suche} onAendern={sucheAendern} zaehler={sucheAktiv
        ? `${sichtbarePositionen.length} of ${lv.positionen.length} items · ${gefiltert.length} of ${findings.length} findings`
        : null} />

      <div className={styles.filter} role="group" aria-label="Filter findings">
        <fieldset className={styles.filterGruppe}>
          <legend>Category</legend>
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
          <legend>Severity</legend>
          <FilterKnopf aktiv={schwere === null} onClick={() => setSchwere(null)}>All</FilterKnopf>
          {SCHWEREN.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={schwere === wert} onClick={() => setSchwere(wert)}>
              <span className={`${styles.punkt} ${styles[`schwere_${wert}`]}`} aria-hidden="true" />
              {name} <span className={styles.anzahl}>{findings.filter((f) => f.schwere === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
        <fieldset className={styles.filterGruppe}>
          <legend>Review</legend>
          <FilterKnopf aktiv={status === null} onClick={() => setStatus(null)}>All</FilterKnopf>
          {STATUS.map(({ wert, name }) => (
            <FilterKnopf key={wert} aktiv={status === wert} onClick={() => setStatus(wert)}>
              {name} <span className={styles.anzahl}>{findings.filter((f) => bewertungVon(bewertungen, f.id).status === wert).length}</span>
            </FilterKnopf>
          ))}
        </fieldset>
      </div>

      <div className={styles.layout}>
        <div className={styles.liste}>
          <h3 className={styles.abschnitt}>
            Findings <span className={styles.anzahl} aria-live="polite">{gefiltert.length} of {findings.length}</span>
          </h3>
          {findings.length === 0 ? (
            <div className={styles.leer}>
              <p><strong>No findings.</strong> The review reported no issues for this BoQ.</p>
              <p>This does not guarantee an error-free BoQ: only the available review rules were applied.</p>
            </div>
          ) : gefiltert.length === 0 ? (
            <div className={styles.leer}>
              <p>No findings match this filter.</p>
              {filterAktiv && (
                <button type="button" className={styles.knopfZweit} onClick={() => { setKategorie(null); setSchwere(null); setStatus(null); setTitel(null); setSuche(""); }}>
                  Reset filters
                </button>
              )}
            </div>
          ) : (
            <ul className={styles.findings}>
              {gefiltert.map((finding) => (
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
          )}

          <details ref={positionenRef} className={styles.positionen}>
            <summary>
              {einheit === null && titel === null && !sucheAktiv
                ? `Show all ${lv.positionen.length} items`
                : `Showing ${sichtbarePositionen.length} of ${lv.positionen.length} items${titel === null ? "" : ` under “${titel.length === 0 ? OHNE_TITEL_NAME : titel.join(" › ")}”`}${einheit === null ? "" : ` summed in ${lv.positionen.find((p) => mengenSchluessel(p) === einheit)?.einheit?.trim() ?? einheit}`}${sucheAktiv ? ` matching “${suche.trim()}”` : ""}`}
            </summary>
            {(einheit !== null || titel !== null || sucheAktiv) && (
              <button type="button" className={styles.knopfZweit} onClick={() => { setEinheit(null); setTitel(null); setSuche(""); }}>Show all items</button>
            )}
            {lv.positionen.length === 0 ? (
              <p className={styles.leer}>The BoQ contains no items.</p>
            ) : sichtbarePositionen.length === 0 ? (
              <p className={styles.leer}>No positions match.</p>
            ) : (
              <div className={styles.tabelleRahmen}>
                <table className={styles.tabelle}>
                  <thead>
                    <tr>
                      <th scope="col">OZ</th><th scope="col">Short description</th><th scope="col" className={styles.rechts}>Quantity</th>
                      <th scope="col" className={styles.rechts}>Unit price</th><th scope="col" className={styles.rechts}>Total price</th>
                      <th scope="col" className={styles.rechts}>Findings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sichtbarePositionen.map((position, index) => (
                      <tr key={`${position.oz}-${index}`} className={auswahl?.oz === position.oz ? styles.zeileGewaehlt : undefined}>
                        <td>
                          <button type="button" className={styles.ozKnopf} onClick={() => waehle(position.oz, null)}
                            aria-label={`Show item ${position.oz}`}>
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
              bewertungen={bewertungen}
              onBewerte={bewerte}
              speicherFehler={speicherFehler}
            />
          ) : (
            <div className={styles.detailLeer}>
              <h3 id="pruefbericht-detail-titel" className={styles.abschnitt}>Details</h3>
              <p>Select a finding or item number to see its short and detailed descriptions, explanation and suggestion.</p>
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
      <span className={styles.marke}>{finding.quelle === "regel" ? "Rule" : "Model"} · {finding.regel_id}</span>
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
        <span>OZ <span className={styles.oz}>{finding.oz}</span>{!ozBekannt && " (not in BoQ)"}</span>
        <span>Euro impact: <Euro wert={finding.euro_wirkung} /></span>
      </span>
    </button>
  );
}

function Detail({ oz, findingId, positionen, findings, onWaehle, onSchliessen, bewertungen, onBewerte, speicherFehler }: {
  oz: string; findingId: string | null; positionen: Position[]; findings: Finding[];
  onWaehle: (id: string) => void; onSchliessen: () => void;
  bewertungen: Bewertungen; onBewerte: (id: string, a: Partial<BewertungDaten>) => void; speicherFehler: boolean;
}) {
  const gewaehlt = findings.find((f) => f.id === findingId) ?? null;
  const weitere = findings.filter((f) => f.id !== findingId);
  return (
    <div>
      <div className={styles.detailKopf}>
        <h3 id="pruefbericht-detail-titel" className={styles.abschnitt}>OZ <span className={styles.oz}>{oz}</span></h3>
        <button type="button" className={styles.schliessen} onClick={onSchliessen} aria-label="Close details">×</button>
      </div>

      {gewaehlt && (
        <article className={`${styles.befund} ${istMock(gewaehlt) ? styles.karteMock : ""}`}>
          <Merkmale finding={gewaehlt} />
          <h4>{gewaehlt.titel}</h4>
          <dl className={styles.felder}>
            <dt>Explanation</dt><dd>{gewaehlt.begruendung || <Unbekannt />}</dd>
            <dt>Suggestion</dt><dd>{gewaehlt.vorschlag || <Unbekannt />}</dd>
            <dt>Euro impact</dt><dd><Euro wert={gewaehlt.euro_wirkung} /></dd>
            <dt>Source</dt><dd>{gewaehlt.quelle === "regel" ? "Fixed review rule" : "Model"} ({gewaehlt.regel_id})</dd>
          </dl>
          <Bewertung key={gewaehlt.id} bewertung={bewertungVon(bewertungen, gewaehlt.id)}
            onAendern={(a) => onBewerte(gewaehlt.id, a)} speicherFehler={speicherFehler} />
        </article>
      )}

      {weitere.length > 0 && (
        <div className={styles.weitere}>
          <p>{gewaehlt ? "Other findings for this item number:" : "Findings for this item number:"}</p>
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
      {!gewaehlt && findings.length === 0 && <p className={styles.hinweis}>No findings for this item number.</p>}

      {positionen.length === 0 ? (
        <p className={styles.fehler}>This item number does not exist in the BoQ. The finding cannot be linked to an original item.</p>
      ) : (
        <>
          {positionen.length > 1 && (
            <p className={styles.warnung}>Item number {oz} occurs {positionen.length} times. All original items:</p>
          )}
          {positionen.map((position, index) => (
            <article key={index} className={styles.position}>
              <p className={styles.pfad}>{position.titel_pfad.length > 0 ? position.titel_pfad.join(" / ") : "no section"}</p>
              <h4>{position.kurztext || <Unbekannt />}</h4>
              <p className={styles.langtext}>
                {position.langtext ? position.langtext : <span className={styles.unbekannt}>No detailed description supplied.</span>}
              </p>
              <dl className={styles.werte}>
                <div><dt>Quantity</dt><dd><Menge menge={position.menge} einheit={position.einheit} /></dd></div>
                <div><dt>Unit price</dt><dd><Euro wert={position.ep} /></dd></div>
                <div><dt>Total price</dt><dd><Euro wert={position.gp} /></dd></div>
                <div><dt>Type</dt><dd>{TYP_NAME[position.typ] ?? position.typ}</dd></div>
              </dl>
            </article>
          ))}
        </>
      )}
    </div>
  );
}

export default Pruefbericht;
