"use client";

import { useDok } from "@/components/dok/useDok";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { Finding, Pruefbericht as PruefberichtDaten } from "@/lib/api";
import { befundAnzeige } from "@/lib/befundtext";
import { bewertungVon, ladeBewertungen, setze, speichereBewertungen, type Bewertung as BewertungDaten, type Bewertungen } from "@/lib/bewertung";
import { useEinstellungen } from "@/lib/einstellungen";
import { lesePreisliste, ladePreisliste, speicherePreisliste, type Preis } from "@/lib/preisliste";
import { preisbericht } from "@/lib/preisbericht";
import { useEinschaetzung } from "../einschaetzung/Einschaetzung";
import { Bewertung } from "../bewertung/Bewertung";
import { Pruefbericht, PRUEFBERICHT_SPEICHER_SCHLUESSEL } from "../Pruefbericht";
import { Angebot } from "../angebot/Angebot";
import { Fundstelle } from "../fundstelle/Fundstelle";
import { Icon } from "../icon/Icon";
import { Info } from "../info/Info";
import { KiHinweis } from "../kihinweis/KiHinweis"; // D #168
import { kiHinweise } from "@/lib/kischritte";
import { Ring } from "../ring/Ring";
import styles from "./bericht.module.css";

type Stufe = 1 | 2 | 3;
type Typ = "issue" | "warning" | "rec";
type Eintrag = { key: string; typ: Typ; titel: string; oz?: string; text?: string; vorschlag?: string; euro?: number | null; rang: number; finding?: Finding };

const STUFE_SCHLUESSEL = "lv-stufe-v1";
const FARBE: Record<Typ, string> = { issue: "var(--sev-kritisch)", warning: "var(--sev-mittel)", rec: "var(--sev-ok)" };
const AMPEL = { rot: "var(--sev-kritisch)", gelb: "var(--sev-mittel)", gruen: "var(--sev-ok)" } as const;
const TEXT = { ...AMPEL, gelb: "var(--sev-mittel-text)" } as const;
const RANG: Record<Finding["schwere"], number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const SEITE = 30;

/**
 * The review report in levels (team sketch): level 1 is the summary everybody needs; the user opens level 2 (filterable,
 * sortable list with details and comments) and level 3 (full estimated price report and all analysis tools) only when
 * they want more. Complexity grows on request, never all at once.
 */
export function Bericht({ bericht, offline = false, anzeigeName, original = null }: { bericht: PruefberichtDaten; offline?: boolean; anzeigeName?: string; original?: File | null }) {
  const d = useDok();
  const { e: einstellungen, t } = useEinstellungen();
  const bewertung = useEinschaetzung(bericht);
  const { e } = bewertung;
  const zahl = useMemo(() => new Intl.NumberFormat(einstellungen.sprache === "de" ? "de-DE" : "en-GB"), [einstellungen.sprache]);
  const euro = useMemo(() => new Intl.NumberFormat(einstellungen.sprache === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }), [einstellungen.sprache]);
  const euro2 = useMemo(() => new Intl.NumberFormat(einstellungen.sprache === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "EUR" }), [einstellungen.sprache]);
  const euroKurz = useMemo(() => new Intl.NumberFormat(einstellungen.sprache === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 }), [einstellungen.sprache]);

  const [stufe, setStufeState] = useState<Stufe>(() => { try { return (Number(window.sessionStorage.getItem(STUFE_SCHLUESSEL)) || 1) as Stufe; } catch { return 1; } });
  const setStufe = (s: Stufe) => { setStufeState(s); try { window.sessionStorage.setItem(STUFE_SCHLUESSEL, String(s)); } catch { /* not kept */ } };
  const [filter, setFilter] = useState<Set<Typ>>(new Set(["issue", "warning", "rec"]));
  const [sortierung, setSortierung] = useState<"wichtig" | "az" | "oz">("wichtig");
  const [offen, setOffen] = useState<string | null>(null);
  const [anzahl, setAnzahl] = useState(SEITE);
  const [nurGeaendert, setNurGeaendert] = useState(true);
  const [preisAnzahl, setPreisAnzahl] = useState(50);
  const [bewertungen, setBewertungen] = useState<Bewertungen>({});
  useEffect(() => { setBewertungen(ladeBewertungen(bericht.lv.name, bericht.findings)); }, [bericht]);
  const bewerte = (id: string, a: Partial<BewertungDaten>) => { const neu = setze(bewertungen, id, a); setBewertungen(neu); speichereBewertungen(bericht.lv.name, neu); };

  const positionen = useMemo(() => new Map(bericht.lv.positionen.map((p) => [p.oz, p])), [bericht]);
  const alleNachOz = useMemo(() => {
    const karte = new Map<string, typeof bericht.lv.positionen>();
    for (const p of bericht.lv.positionen) karte.set(p.oz, [...(karte.get(p.oz) ?? []), p]);
    return karte;
  }, [bericht]);
  const [preisliste, setPreisliste] = useState<Preis[]>([]);
  useEffect(() => { setPreisliste(ladePreisliste()); }, []);
  const [preisOffen, setPreisOffen] = useState<string | null>(null);
  const preis = useMemo(() => preisbericht(bericht.lv.positionen, bewertung.gewerke, preisliste), [bericht, bewertung.gewerke, preisliste]);
  /** Synthetic demo unit prices (tools/demo_preisliste.py), kept like an uploaded price list. */
  async function demoPreise() {
    const liste = lesePreisliste(await (await fetch("/demo-preisliste.json")).text());
    speicherePreisliste(liste); setPreisliste(liste); setNurGeaendert(true);
  }

  // Level 2 entries: findings as issues (critical/high) or warnings, plus recommendations from the assessment and the AI.
  const eintraege = useMemo<Eintrag[]>(() => {
    // The demo entry (MOCK_) is not a finding: the header already says "offline mock", and the counts leave it out too.
    const befunde = bericht.findings.filter((f) => !f.regel_id.startsWith("MOCK_"))
      .map((f) => befundAnzeige(f, einstellungen.sprache))
      .map((f): Eintrag => ({ key: f.id, typ: RANG[f.schwere] <= 1 ? "issue" : "warning", titel: f.titel, oz: f.oz, text: f.begruendung, vorschlag: f.vorschlag, euro: f.euro_wirkung, rang: RANG[f.schwere], finding: f }));
    // Price outliers (unit price far from similar items or past projects) count in the tiles, so they are listed too.
    const preisAuffaellig = bewertung.preise.gruppen.flatMap((g) => g.positionen.filter((p) => p.stufe !== "gruen").map((p): Eintrag => ({
      key: `preis-${p.oz}`, typ: p.stufe === "rot" ? "issue" : "warning", oz: p.oz, rang: p.stufe === "rot" ? 1 : 2,
      titel: t("Unusual unit price: {item}", { item: d(g.kurztext) }),
      text: t("{ep} per {unit}, {d} % from the median {median} of similar items.", { ep: euro2.format(p.ep), unit: g.einheit, d: `${p.abweichung > 0 ? "+" : ""}${Math.round(p.abweichung)}`, median: euro2.format(g.median) }),
    })));
    const lokal = e.empfehlungen.filter((r) => r.ampel !== "gruen").map((r, i): Eintrag => ({ key: `r${i}`, typ: "rec", titel: t(r.text, r.werte), rang: 4 }));
    const ki = (bewertung.ki.daten?.recommendations ?? []).map((r, i): Eintrag => ({ key: `k${i}`, typ: "rec", titel: r.title, text: r.why, rang: 5 }));
    return [...befunde, ...preisAuffaellig, ...lokal, ...ki];
  }, [bericht, e, bewertung.ki.daten, bewertung.preise, einstellungen, t, euro2]);
  const gezeigt = useMemo(() => eintraege.filter((x) => filter.has(x.typ)).sort((a, b) =>
    sortierung === "az" ? a.titel.localeCompare(b.titel) : sortierung === "oz" ? (a.oz ?? "~").localeCompare(b.oz ?? "~")
      : a.rang - b.rang || Math.abs(b.euro ?? 0) - Math.abs(a.euro ?? 0)), [eintraege, filter, sortierung]);
  const zaehler = (typ: Typ) => eintraege.filter((x) => x.typ === typ).length;

  function zeige(typ: Typ | null) {
    setFilter(new Set(typ ? [typ] : ["issue", "warning", "rec"]));
    setStufe(Math.max(stufe, 2) as Stufe);
    requestAnimationFrame(() => document.getElementById("stufe-2")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  /** Was / Estimated tiles: open level 3 and jump to the price table. */
  function zeigePreise() {
    setStufe(3);
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById("stufe-3")?.scrollIntoView({ behavior: "smooth", block: "start" })));
  }
  /** Back to the summary circle; with a level, also close the deeper levels. */
  function zurueck(neu: Stufe) {
    setStufe(neu);
    requestAnimationFrame(() => document.getElementById("bericht-titel")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  // #170: the uploaded PDF stays in this tab as a Blob URL, so a finding can open it at its item's page.
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!original || !original.name.toLowerCase().endsWith(".pdf")) { setOriginalUrl(null); return; }
    const url = URL.createObjectURL(original);
    setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [original]);
  // "Show in BoQ": open level 3 and the analysis tools, then the BoQ view selects and highlights the OZ.
  const [sprung, setSprung] = useState<{ oz: string; n: number } | null>(null);
  const werkzeugeRef = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!sprung || !werkzeugeRef.current) return;
    werkzeugeRef.current.open = true;
  }, [sprung]);
  function imLv(oz: string) { setStufe(3); setSprung((alt) => ({ oz, n: (alt?.n ?? 0) + 1 })); }

  function zumExport() { try { window.sessionStorage.setItem(PRUEFBERICHT_SPEICHER_SCHLUESSEL, JSON.stringify(bericht)); } catch { /* export reads its own upload then */ } }

  const preisZeilen = preis.zeilen.filter((z) => !nurGeaendert || (z.war && z.diff && Math.abs(z.diff) / Math.abs(z.war) >= .02))
    .sort((a, b) => Math.abs(b.diff ?? 0) - Math.abs(a.diff ?? 0));
  const plusMinus = Math.abs(bericht.zusammenfassung?.schaetzung_abweichung_eur ?? e.schaetzung?.plusMinus ?? 0);

  return (
    <section className={styles.bericht} aria-labelledby="bericht-titel">
      <header className={styles.kopf}>
        <div>
          <h2 id="bericht-titel" className={styles.titel}>{anzeigeName || bericht.lv.name}</h2>
          <p className={styles.quelle}>{anzeigeName && anzeigeName !== bericht.lv.name && <>{bericht.lv.name} · </>}{zahl.format(bericht.lv.positionen.length)} {t("items")}
            {bericht.kennzahlen.modell_mock && <> · <span className={styles.mock}>{t("model · offline mock")}</span></>}{offline && <> · {t("Offline example – not live analysis.")}</>}</p>
        </div>
        <a className={styles.knopfLeise} href="/export" onClick={zumExport}><Icon name="download" /> {t("Export report")}</a>
      </header>
      <KiHinweis hinweise={kiHinweise(bericht, bewertung.ki)} />

      {/* Level 1: the summary from the sketch – was, score, estimated; issues, warnings, recommendations. */}
      <div className={styles.stufe1}>
        <button type="button" className={styles.preisKachel} onClick={zeigePreise} title={t("Show full estimated price report")}>
          <span className={styles.label}>{t("Was")}</span>
          <strong className={styles.preis}>{preis.war ? euroKurz.format(preis.war) : "–"}</strong>
          <span className={styles.klein}>{t("total in the bill")}</span>
          <span className={styles.oeffnen}>{t("Price report")} ›</span>
        </button>
        <div className={styles.score}>
          {/* The ring shows exactly the three counts below it: issues (red), warnings (yellow), recommendations (green). */}
          <Ring teile={[{ wert: zaehler("issue"), farbe: AMPEL.rot }, { wert: zaehler("warning"), farbe: AMPEL.gelb }, { wert: zaehler("rec"), farbe: AMPEL.gruen }]}
            mitte={e.score.toFixed(1)} unter="/ 10" farbe={TEXT[e.ampel]} beschriftung={`${t("Score")} ${e.score} / 10`} max={460} plastisch />
          <strong style={{ color: TEXT[e.ampel] }}>{t(e.urteil)}</strong>
        </div>
        <button type="button" className={`${styles.preisKachel} ${styles.geschaetzt}`} onClick={zeigePreise} title={t("Show full estimated price report")}>
          <span className={styles.label}><Icon name="sparkles" /> {t("Estimated")} <Info text={t("Item by item from the price list, past projects of the same trade and the AI evaluation. Open the full price report for every reason.")} /></span>
          <strong className={styles.preis}>{preis.geschaetzt ? euroKurz.format(preis.geschaetzt) : "–"}{plusMinus > 0 && <small> ± {euroKurz.format(plusMinus)}</small>}</strong>
          <span className={styles.klein} style={{ color: preis.diff > 0 ? "var(--sev-kritisch)" : preis.diff < 0 ? "var(--sev-ok)" : undefined }}>
            {preis.diff === 0 ? t("same as the bill") : `${preis.diff > 0 ? "+" : "−"}${euroKurz.format(Math.abs(preis.diff))} ${t("vs. was")}`}
          </span>
          <span className={styles.oeffnen}>{t("Price report")} ›</span>
        </button>
        {([["issue", "Issues", zaehler("issue"), "alert"], ["warning", "Warnings", zaehler("warning"), "warning"], ["rec", "Recommendations", zaehler("rec"), "lightbulb"]] as const).map(([typ, name, n, icon]) => (
          <button key={typ} type="button" className={styles.zaehler} style={{ "--balken": FARBE[typ] } as React.CSSProperties} onClick={() => zeige(typ)}>
            <span className={styles.label}><Icon name={icon} /> {t(name)}</span>
            <strong style={{ color: typ === "warning" ? "var(--sev-mittel-text)" : FARBE[typ] }}>{zahl.format(n)}</strong>
          </button>
        ))}
      </div>

      {stufe < 2 ? (
        <button type="button" className={styles.mehr} onClick={() => setStufe(2)}>{t("Show details")} ▾</button>
      ) : (<>
        <button type="button" className={styles.weniger} onClick={() => zurueck(1)}>▴ {t("Hide details")}</button>
        {/* Always a way back to the summary circle while details are open. */}
        <button type="button" className={styles.zurUebersicht} onClick={() => zurueck(stufe)}>↑ {t("Summary")}</button>
        <section id="stufe-2" className={styles.stufe2} aria-label={t("Details")}>
          <div className={styles.werkzeug}>
            <div className={styles.filter} role="group" aria-label={t("Filter")}>
              <Icon name="filter" />
              {(["issue", "warning", "rec"] as Typ[]).map((typ) => (
                <button key={typ} type="button" aria-pressed={filter.has(typ)} className={styles.chip} style={{ "--f": FARBE[typ] } as React.CSSProperties}
                  onClick={() => { const n = new Set(filter); if (!n.delete(typ)) n.add(typ); setFilter(n.size ? n : new Set([typ])); setAnzahl(SEITE); }}>
                  <i />{t(typ === "issue" ? "Issues" : typ === "warning" ? "Warnings" : "Recommendations")} <b>{zaehler(typ)}</b>
                </button>
              ))}
            </div>
            <label className={styles.sort}>{t("Sort")}
              <select value={sortierung} onChange={(ev) => setSortierung(ev.target.value as typeof sortierung)}>
                <option value="wichtig">{t("Importance")}</option><option value="az">A–Z</option><option value="oz">OZ</option>
              </select>
            </label>
          </div>

          <ul className={styles.liste}>
            {gezeigt.slice(0, anzahl).map((x) => {
              const auf = offen === x.key;
              const pos = x.oz ? positionen.get(x.oz) : undefined;
              return (
                <li key={x.key} className={auf ? styles.offen : undefined} style={{ "--f": FARBE[x.typ] } as React.CSSProperties}>
                  <button type="button" className={styles.zeile} aria-expanded={auf} onClick={() => setOffen(auf ? null : x.key)}>
                    <span className={styles.typ}>{t(x.typ === "issue" ? "Issue" : x.typ === "warning" ? "Warning" : "Recommendation")}</span>
                    <span className={styles.zeileTitel}>{x.titel}</span>
                    <span className={styles.oz}>{x.oz ?? ""}</span>
                    <span className={styles.euro}>{x.euro ? euro.format(x.euro) : ""}</span>
                    {x.finding && bewertungVon(bewertungen, x.finding.id).status !== "offen" && <span className={styles.status}>✓</span>}
                    <span className={styles.pfeil}>{auf ? "▴" : "▾"}</span>
                  </button>
                  {auf && (pos || x.text || x.vorschlag || x.finding) && (
                    <div className={styles.details}>
                      {pos && <p className={styles.position}><b>OZ {pos.oz}</b> · {d(pos.kurztext)}{pos.menge !== null && <> · {zahl.format(pos.menge)} {pos.einheit}</>}</p>}
                      {/* #170: one location per occurrence of the OZ (duplicates show every place); the jump goes to the OZ. */}
                      {x.oz && (alleNachOz.get(x.oz) ?? [undefined]).slice(0, 5).map((p, i) => (
                        <Fundstelle key={i} datei={bericht.lv.quelle} oz={x.oz!} position={p} originalUrl={originalUrl} onImLv={i === 0 ? () => imLv(x.oz!) : undefined} />
                      ))}
                      {x.text && <p><b>{t("Why")}:</b> {x.text}</p>}
                      {x.vorschlag && <p><b>{t("Suggestion")}:</b> {x.vorschlag}</p>}
                      {x.finding && <Bewertung key={x.finding.id} bewertung={bewertungVon(bewertungen, x.finding.id)} onAendern={(a) => bewerte(x.finding!.id, a)} speicherFehler={false} />}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {gezeigt.length > anzahl && (
            <button type="button" className={styles.mehrLeise} onClick={() => setAnzahl(anzahl + SEITE)}>
              {t("Show {n} more", { n: Math.min(SEITE, gezeigt.length - anzahl) })} · {t("{a} of {b}", { a: Math.min(anzahl, gezeigt.length), b: gezeigt.length })}
            </button>
          )}

          {stufe < 3 ? (
            <button type="button" className={styles.mehr} onClick={() => setStufe(3)}>{t("Show full estimated price report")} ▾</button>
          ) : (
            <section id="stufe-3" className={styles.stufe3} aria-label={t("Estimated price report")}>
              <button type="button" className={styles.weniger} onClick={() => setStufe(2)}>▴ {t("Hide price report")}</button>
              <div className={styles.werkzeug}>
                <h3 className={styles.abschnitt}>{t("Estimated price report")}
                  <Info text={t("Every bill item with the price in the bill (was), the estimate and why. Yellow rows changed; red numbers mean more expensive, green cheaper. The backend's estimated bill replaces this once it is connected.")} /></h3>
                {preisliste.length ? (
                  <button type="button" className={styles.knopfLeise} onClick={() => { speicherePreisliste([]); setPreisliste([]); }}>{t("Remove price list")} ({preisliste.length})</button>
                ) : (
                  <button type="button" className={styles.knopfLeise} onClick={demoPreise}><Icon name="download" /> {t("Load demo unit prices")}</button>
                )}
                <label className={styles.sort}><input type="checkbox" checked={nurGeaendert} onChange={(ev) => setNurGeaendert(ev.target.checked)} /> {t("Only changed items")} ({preis.geaendert})</label>
              </div>
              <div className={styles.rahmen}>
                <table className={styles.tabelle}>
                  <thead><tr><th>OZ</th><th>{t("Item")}</th><th className={styles.rechts}>{t("Quantity")}</th><th className={styles.rechts}>{t("Was")}</th><th className={styles.rechts}>{t("Estimated")}</th><th className={styles.rechts}>±</th><th>{t("Why")}</th></tr></thead>
                  <tbody>
                    {preisZeilen.slice(0, preisAnzahl).map((z, i) => { const k = `${z.oz}-${i}`; const auf = preisOffen === k; return (<Fragment key={k}>
                      <tr tabIndex={0} aria-expanded={auf} className={`${styles.klickbar} ${z.diff && z.war && Math.abs(z.diff) / Math.abs(z.war) >= .02 ? styles.geaendert : ""}`}
                        onClick={() => setPreisOffen(auf ? null : k)} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setPreisOffen(auf ? null : k); } }}>
                        <td className={styles.oz}>{z.oz}</td><td title={z.kurztext}>{d(z.kurztext)}</td>
                        <td className={styles.rechts}>{z.menge === null ? "–" : `${zahl.format(z.menge)} ${z.einheit ?? ""}`}</td>
                        <td className={styles.rechts}>{z.war === null ? "–" : euro.format(z.war)}</td>
                        <td className={styles.rechts}>{z.geschaetzt === null ? "–" : euro.format(z.geschaetzt)}</td>
                        <td className={styles.rechts} style={{ color: (z.diff ?? 0) > 0 ? "var(--sev-kritisch)" : (z.diff ?? 0) < 0 ? "var(--sev-ok)" : undefined }}>
                          {z.diff ? `${z.diff > 0 ? "+" : "−"}${euro.format(Math.abs(z.diff))}` : "0"}</td>
                        <td className={styles.grund}>{t(z.grund, z.werte)} <span className={styles.pfeilKlein}>{auf ? "▴" : "▾"}</span></td>
                      </tr>
                      {auf && (
                        <tr className={styles.preisDetail}><td colSpan={7}>
                          <dl>
                            <div><dt>{t("Quantity")}</dt><dd>{z.menge === null ? "–" : `${zahl.format(z.menge)} ${z.einheit ?? ""}`}</dd></div>
                            <div><dt>{t("Unit price in the bill")}</dt><dd>{z.epWar === null ? "–" : `${euro2.format(z.epWar)} / ${z.einheit ?? ""}`}</dd></div>
                            <div><dt>{t("Estimated unit price")}</dt><dd>{z.epGeschaetzt === null ? "–" : `${euro2.format(z.epGeschaetzt)} / ${z.einheit ?? ""}`}</dd></div>
                            <div><dt>{t("Unit price change")}</dt><dd>{z.epWar && z.epGeschaetzt !== null ? `${z.epGeschaetzt >= z.epWar ? "+" : "−"}${euro2.format(Math.abs(z.epGeschaetzt - z.epWar))} (${z.epGeschaetzt >= z.epWar ? "+" : "−"}${Math.abs(Math.round((z.epGeschaetzt / z.epWar - 1) * 1000) / 10)} %)` : "–"}</dd></div>
                            <div><dt>{t("Source")}</dt><dd>{t(z.quelle === "preisliste" ? "Price list" : z.quelle === "historie" ? "Past projects" : z.quelle === "ohne_preis" ? "No price in the bill" : "Unchanged")}</dd></div>
                          </dl>
                          {z.menge !== null && z.epGeschaetzt !== null && <p className={styles.klein}>{zahl.format(z.menge)} {z.einheit} × {euro2.format(z.epGeschaetzt)} = {euro.format(z.geschaetzt ?? 0)}</p>}
                        </td></tr>
                      )}
                    </Fragment>); })}
                  </tbody>
                  <tfoot><tr><td colSpan={3}>{t("Total")}</td><td className={styles.rechts}>{euro.format(preis.war)}</td><td className={styles.rechts}>{euro.format(preis.geschaetzt)}</td>
                    <td className={styles.rechts} style={{ color: preis.diff > 0 ? "var(--sev-kritisch)" : "var(--sev-ok)" }}>{preis.diff > 0 ? "+" : "−"}{euro.format(Math.abs(preis.diff))}</td><td /></tr></tfoot>
                </table>
              </div>
              {preisZeilen.length > preisAnzahl && <button type="button" className={styles.mehrLeise} onClick={() => setPreisAnzahl(preisAnzahl + 50)}>{t("Show {n} more", { n: Math.min(50, preisZeilen.length - preisAnzahl) })}</button>}

              <Angebot ekt={preis.geschaetzt} projekt={anzeigeName || bericht.lv.name} />

              <details ref={werkzeugeRef} className={styles.werkzeuge}>
                <summary><Icon name="dashboard" /> {t("All analysis tools")} <small>{t("overview, findings, items, prices, bidder questions, quantities")}</small></summary>
                <Pruefbericht bericht={bericht} offline={offline} anzeigeName={anzeigeName} bewertung={bewertung} eingebettet springeZu={sprung} originalUrl={originalUrl} />
              </details>
              <button type="button" className={styles.mehrLeise} onClick={() => zurueck(1)}>▴ {t("Show less")}</button>
            </section>
          )}
        </section>
      </>)}
    </section>
  );
}
