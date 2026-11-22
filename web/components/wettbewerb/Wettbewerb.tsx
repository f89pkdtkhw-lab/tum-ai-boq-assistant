"use client";

// Competitor dashboard: every saved tender opening result, each bidder's usual margin over our own costs
// (strip chart, one dot per tender) and a warning for bidders whose prices are unrealistic.
import { useEffect, useMemo, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { auswerten, bewerte, empfehle, lade, leseDokument, speichere, zahl, type Firma, type Gebot, type Submission } from "@/lib/wettbewerb";
import { AUFGREIFSCHWELLE, STANDARD, kalkuliere } from "@/lib/zuschlag";
import { Info } from "../info/Info";
import styles from "./wettbewerb.module.css";

const STUFE: Record<Firma["einstufung"], { label: string; farbe: string }> = {
  unrealistisch: { label: "Unrealistic – don't compete", farbe: "var(--sev-kritisch)" },
  aggressiv: { label: "Aggressive", farbe: "var(--sev-hoch)" },
  normal: { label: "Normal", farbe: "var(--sev-ok)" },
};
/** Square status mark + label (no emoji): colour is never the only signal. */
const Marke = ({ farbe }: { farbe: string }) => <i style={{ display: "inline-block", width: 9, height: 9, background: farbe, marginRight: 6, verticalAlign: "1px" }} />;

export function Wettbewerb() {
  const { e: einstellungen, t } = useEinstellungen();
  const [subs, setSubs] = useState<Submission[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  // Loaded bidder document, previewed before it is stored.
  const [entwurf, setEntwurf] = useState<{ projekt: string; datum: string; selbstkosten: string }>({ projekt: "", datum: "", selbstkosten: "" });
  // Bidder rows: filled from the document (rules or AI) and editable by hand.
  const [zeilen, setZeilen] = useState<{ firma: string; summe: string }[]>([]);
  const [lesen, setLesen] = useState<{ laeuft: boolean; methode?: string; hinweis?: string | null }>({ laeuft: false });
  const gelesen: Gebot[] = useMemo(() => zeilen.map((z) => ({ firma: z.firma.trim(), summe: zahl(z.summe) })).filter((g) => g.firma && g.summe > 0), [zeilen]);
  const euroEingabe = (n: number) => n.toLocaleString("de-DE", { maximumFractionDigits: 2 });
  const kosten = zahl(entwurf.selbstkosten);
  const vorschau = kosten > 0 ? bewerte(gelesen, kosten) : [];
  // Next tender: what to bid, from the stored behaviour.
  const [plan, setPlan] = useState({ selbstkosten: "", unterbieten: 1, minMarge: 2 });
  useEffect(() => { setSubs(lade()); }, []);
  const setzen = (n: Submission[]) => { setSubs(n); speichere(n); };
  const firmen = useMemo(() => auswerten(subs), [subs]);
  const loc = einstellungen.sprache === "de" ? "de-DE" : "en-GB";
  const euro = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

  /** Document → backend (PDF, Excel, CSV, text: rules first, AI when rules fail); CSV/text also offline in the browser. */
  async function datei(file: File | undefined) {
    if (!file) return;
    setEntwurf((e) => ({ ...e, projekt: e.projekt || file.name.replace(/\.[^.]+$/, "") }));
    setLesen({ laeuft: true });
    let bieter: Gebot[] = [], methode = "regeln", hinweis: string | null = null;
    try {
      const form = new FormData();
      form.append("datei", file);
      const r = await fetch("/backend/api/submission/lesen", { method: "POST", body: form });
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail ?? `HTTP ${r.status}`);
      ({ bieter, methode, hinweis } = await r.json());
    } catch (err) {
      if (/\.(csv|txt|tsv)$/i.test(file.name)) { bieter = leseDokument(await file.text()); hinweis = t("Backend not reachable – read in the browser with rules only."); }
      else hinweis = `${t("Could not read the document")}: ${(err as Error).message}`;
    }
    setZeilen(bieter.map((b) => ({ firma: b.firma, summe: euroEingabe(b.summe) })));
    setLesen({ laeuft: false, methode, hinweis });
    setMeldung(bieter.length ? null : t("No bidder with an amount found – add the bidders by hand below."));
  }
  function speichern() {
    if (gelesen.length === 0 || !(kosten > 0)) { setMeldung(t("Enter our own costs and at least one bid.")); return; }
    setzen([...subs, { id: `${Date.now()}`, projekt: entwurf.projekt || t("Tender"), datum: entwurf.datum || new Date().toISOString().slice(0, 10), selbstkosten: kosten, gebote: gelesen }]);
    setEntwurf({ projekt: "", datum: "", selbstkosten: "" }); setZeilen([]); setLesen({ laeuft: false });
    setMeldung(null);
  }
  const planKosten = zahl(plan.selbstkosten);
  const rat = planKosten > 0 && firmen.length ? empfehle(planKosten, firmen, subs, plan) : null;

  const kritisch = firmen.filter((f) => f.einstufung === "unrealistisch");

  // Jobs to price against: the report that is open (its bill total as direct costs, our markups on top) and past tenders.
  const [aktuell, setAktuell] = useState<{ projekt: string; selbstkosten: number } | null>(null);
  useEffect(() => {
    try {
      const b = JSON.parse(window.sessionStorage.getItem("lv-aktuell-v1") ?? "null")?.bericht;
      const summe = b?.lv?.positionen?.reduce((x: number, p: { gp: number | null }) => x + (p.gp ?? 0), 0);
      if (summe > 0) setAktuell({ projekt: b.lv.name, selbstkosten: Math.round(kalkuliere(summe, { ...STANDARD, ...JSON.parse(window.localStorage.getItem("lv-zuschlag-v1") ?? "{}") }).selbstkosten) });
    } catch { /* no open report */ }
  }, []);
  const jobs = [...(aktuell ? [{ ...aktuell, offen: true }] : []), ...subs.map((x) => ({ projekt: x.projekt, selbstkosten: x.selbstkosten, offen: false }))];
  const kostenJob = planKosten > 0 ? planKosten : jobs[0]?.selbstkosten ?? 0;
  const jobName = jobs.find((j) => j.selbstkosten === kostenJob)?.projekt ?? t("your job");
  const preis = (m: number) => Math.round(kostenJob / (1 - m / 100));

  // One line: every bidder at its usual price for this job, our costs and our recommended bid on the same € axis.
  const marken = firmen.map((f) => ({ f, wert: preis(f.marge), von: preis(f.min), bis: preis(f.max) })).sort((a, b) => a.wert - b.wert);
  const empf = planKosten > 0 ? rat?.empfohlen : kostenJob > 0 && firmen.length ? empfehle(kostenJob, firmen, subs, plan).empfohlen : undefined;
  const werte = [kostenJob, ...marken.map((m) => m.wert), ...(empf ? [empf] : [])];
  const lo = Math.min(...werte) * 0.97, hi = Math.max(...werte) * 1.02;
  const B = 760, RAND = 30, MITTE = 150, H = 340;
  const x = (v: number) => RAND + (v - lo) / (hi - lo || 1) * (B - 2 * RAND);
  // Labels alternate above/below and step outward when they would collide.
  const ebenen: number[][] = [[], []];
  const etiketten = marken.map((m, i) => {
    const seite = i % 2;
    let stufe = 0;
    while ((ebenen[seite][stufe] ?? -1e9) > x(m.wert) - 92) stufe++;
    ebenen[seite][stufe] = x(m.wert);
    return { ...m, seite, stufe };
  });
  const kompakt = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 2 });
  const kurz = { format: (v: number) => (Math.abs(v) >= 1e6 ? kompakt.format(v) : euro.format(v)) };
  // Round tick steps (1, 2 or 5 × 10^n) so the axis reads like a scale, not like computed decimals.
  const roh = (hi - lo) / 5, zehner = 10 ** Math.floor(Math.log10(roh || 1));
  const schritt = [1, 2, 5, 10].map((k) => k * zehner).find((k) => k >= roh) ?? zehner * 10;
  const ticks = Array.from({ length: 8 }, (_, i) => Math.ceil(lo / schritt) * schritt + i * schritt).filter((v) => v <= hi);
  const farbe = (e: Firma["einstufung"]) => (e === "unrealistisch" ? "var(--sev-kritisch)" : e === "aggressiv" ? "var(--sev-hoch)" : "var(--accent-2)");

  return (
    <main className={styles.seite}>
      <h1 className={styles.titel}>{t("Competitors")}</h1>

      <div className={styles.kacheln}>
        <div><span>{t("Tenders")}</span><strong>{subs.length}</strong></div>
        <div><span>{t("Bidders")}</span><strong>{firmen.length}</strong></div>
        <div data-warn={kritisch.length > 0}><span>{t("Unrealistic bidders")}</span><strong>{kritisch.length}</strong>
          {kritisch.length > 0 && <small>{kritisch.map((f) => f.firma).join(", ")}</small>}</div>
      </div>

      {firmen.length === 0 ? (
        <section className={styles.karte}>
          <p>{t("No tender results yet. Add one below or save one from the bid section of a report.")}</p>
        </section>
      ) : (
        <section className={styles.karte}>
          <h2 className={styles.abschnitt}>{t("Where the bidders play – {job}", { job: jobName })}
            <Info text={t("Every bidder at its usual price for this job: our own costs ÷ (1 − its usual margin). Left of the dashed line is below our own costs – those prices lose money. Hover a bidder for its range from past tenders. Pick another job to see real prices for it.")} /></h2>
          {/* Job switcher: one control however many jobs there are – arrows step, the list jumps. */}
          {(() => {
            const i = Math.max(0, jobs.findIndex((j) => j.selbstkosten === kostenJob));
            const waehle = (k: number) => { const j = jobs[(k + jobs.length) % jobs.length]; if (j) setPlan({ ...plan, selbstkosten: j.selbstkosten.toLocaleString("de-DE") }); };
            return (
              <div className={styles.schalter}>
                <button type="button" className={styles.leise} aria-label={t("Previous job")} onClick={() => waehle(i - 1)}>‹</button>
                <select className={styles.leise} aria-label={t("Jobs")} value={i} onChange={(ev) => waehle(Number(ev.target.value))}>
                  {jobs.map((j, k) => <option key={`${j.projekt}-${k}`} value={k}>{j.offen ? `● ${j.projekt}` : j.projekt} · {kurz.format(j.selbstkosten)}</option>)}
                </select>
                <button type="button" className={styles.leise} aria-label={t("Next job")} onClick={() => waehle(i + 1)}>›</button>
                <span className={styles.leiseText}>{i + 1} / {jobs.length}</span>
              </div>
            );
          })()}
          <div className={styles.diagramm} onMouseLeave={() => setHover(null)}>
            <svg viewBox={`0 0 ${B} ${H}`} role="img" aria-label={t("Where the bidders play – {job}", { job: jobName })}>
              <rect x={RAND} y={MITTE - 6} width={Math.max(0, x(kostenJob) - RAND)} height="12" fill="var(--sev-kritisch)" opacity=".12" />
              <line x1={RAND} x2={B - RAND} y1={MITTE} y2={MITTE} stroke="var(--ink)" strokeWidth="2" />
              {ticks.map((v, i) => <g key={i}><line x1={x(v)} x2={x(v)} y1={MITTE - 4} y2={MITTE + 4} stroke="var(--ink)" /><text x={x(v)} y={H - 6} textAnchor="middle" className={styles.achse}>{kurz.format(v)}</text></g>)}
              <line x1={x(kostenJob)} x2={x(kostenJob)} y1={14} y2={H - 22} stroke="var(--sev-kritisch)" strokeDasharray="4 3" />
              <text x={x(kostenJob) - 4} y={16} textAnchor="end" className={styles.zone}>{t("our own costs")} {kurz.format(kostenJob)}</text>
              {etiketten.map(({ f, wert, von, bis, seite, stufe }) => {
                const ty = seite === 0 ? MITTE - 28 - stufe * 46 : MITTE + 34 + stufe * 46;
                return (
                  <g key={f.firma} onMouseEnter={(ev) => {
                    const box = (ev.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                    setHover({ x: (x(wert) / B) * box.width, y: (MITTE / H) * box.height,
                      text: `${f.firma} · ${t(STUFE[f.einstufung].label)}\n${t("usually")} ${euro.format(wert)} (${f.marge > 0 ? "+" : ""}${f.marge} %)\n${t("range")} ${euro.format(von)} … ${euro.format(bis)} · ${f.projekte} ${t("tenders")}, ${f.siege} ${t("won")}` });
                  }}>
                    <line x1={x(wert)} x2={x(wert)} y1={MITTE} y2={seite === 0 ? ty + 4 : ty - 12} stroke="var(--line)" />
                    <circle cx={x(wert)} cy={MITTE} r="7" fill={f.einstufung === "unrealistisch" ? "var(--card)" : farbe(f.einstufung)} stroke={farbe(f.einstufung)} strokeWidth="2.5" />
                    <text x={x(wert)} y={ty - 12} textAnchor="middle" className={styles.name}>{f.einstufung === "unrealistisch" ? "× " : ""}{f.firma}</text>
                    <text x={x(wert)} y={ty + 10} textAnchor="middle" className={styles.preisText}>{kurz.format(wert)}</text>
                  </g>
                );
              })}
              {empf && (
                <g>
                  <rect x={x(empf) - 7} y={MITTE - 7} width="14" height="14" transform={`rotate(45 ${x(empf)} ${MITTE})`} fill="var(--brand)" stroke="var(--card)" strokeWidth="2" />
                  <text x={x(empf)} y={H - 24} textAnchor="middle" className={styles.unser}>{t("our bid")} {kurz.format(empf)}</text>
                </g>
              )}
            </svg>
            {hover && <div className={styles.tipp} style={{ left: hover.x, top: hover.y }}>{hover.text}</div>}
          </div>
          <p className={styles.legende}><i className={styles.voll} /> {t("usual price")} <i className={styles.leerRot} /> {t("unrealistic")} <i className={styles.raute} /> {t("our recommended bid")}</p>

          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr><th>{t("Bidder")}</th><th className={styles.rechts}>{t("Tenders")}</th><th className={styles.rechts}>{t("Won")}</th><th className={styles.rechts}>{t("Usual margin")}</th>
                <th className={styles.rechts}>{t("Usual price for {job}", { job: jobName })}</th><th className={styles.rechts}>{t("Range")}</th><th className={styles.rechts}>{t("≥{s} % under next bid", { s: AUFGREIFSCHWELLE })}</th><th>{t("Assessment")}</th></tr></thead>
              <tbody>
                {firmen.map((f) => (
                  <tr key={f.firma}>
                    <td><b>{f.firma}</b></td><td className={styles.rechts}>{f.projekte}</td><td className={styles.rechts}>{f.siege}</td>
                    <td className={styles.rechts}>{f.marge > 0 ? "+" : ""}{f.marge} %</td><td className={styles.rechts}><b>{euro.format(preis(f.marge))}</b></td>
                    <td className={styles.rechts}>{kurz.format(preis(f.min))} … {kurz.format(preis(f.max))}<br /><small className={styles.leiseText}>{f.min} … {f.max} %</small></td>
                    <td className={styles.rechts}>{f.sprunghaft}</td>
                    <td style={{ fontWeight: 600 }}><Marke farbe={STUFE[f.einstufung].farbe} />{t(STUFE[f.einstufung].label)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {kritisch.length > 0 && <p className={styles.rat}>{t("Where {names} bid, price to your calculation instead of chasing them – their usual price is below what the job costs.", { names: kritisch.map((f) => f.firma).join(", ") })}</p>}
        </section>
      )}

      {/* Next tender: expected bids from each serious bidder's own history, then our bid just under the cheapest. */}
      {firmen.length > 0 && (
        <section className={styles.karte}>
          <h2 className={styles.abschnitt}>{t("Next tender: what to bid")}
            <Info text={t("Each serious bidder is expected at the low end of its own history (25th percentile of its margins, outliers left out). We go a little under the cheapest expectation, never below our minimum margin. Unrealistic bidders are ignored: chasing them only loses money.")} /></h2>
          <div className={styles.formular}>
            <label>{t("Our own costs")}<input inputMode="decimal" placeholder="1.250.000" value={plan.selbstkosten} onChange={(e) => setPlan({ ...plan, selbstkosten: e.target.value })} /></label>
            <label>{t("Go under the cheapest by %")}<input type="number" step="0.5" min={0} value={plan.unterbieten} onChange={(e) => setPlan({ ...plan, unterbieten: Number(e.target.value) || 0 })} /></label>
            <label>{t("Minimum margin %")}<input type="number" step="0.5" value={plan.minMarge} onChange={(e) => setPlan({ ...plan, minMarge: Number(e.target.value) || 0 })} /></label>
          </div>
          {rat && (
            <div className={styles.rat2}>
              <div className={styles.empfehlung}>
                <span>{t("Recommended bid")}</span>
                <strong>{euro.format(rat.empfohlen)}</strong>
                <small>{t(rat.grund === "unter_guenstigstem" ? "{p} % under {f}, the cheapest serious bidder we expect." : rat.grund === "mindestmarge" ? "At your minimum margin – the cheapest serious bidder is expected lower; winning would cost money." : "No usable history yet.",
                  { p: plan.unterbieten, f: rat.vorhersagen[0]?.firma ?? "" })}</small>
                <dl>
                  <div><dt>{t("Margin left")}</dt><dd>{rat.marge} %</dd></div>
                  <div><dt>{t("Would have won")}</dt><dd>{rat.siegquote === null ? "–" : `${rat.siegquote} %`} <small>{t("of past tenders")}</small></dd></div>
                </dl>
              </div>
              <table className={styles.tabelle}>
                <thead><tr><th>{t("Expected bidder")}</th><th className={styles.rechts}>{t("Expected margin")}</th><th className={styles.rechts}>{t("Expected bid")}</th></tr></thead>
                <tbody>
                  {rat.vorhersagen.map((v) => <tr key={v.firma}><td>{v.firma} <small className={styles.leiseText}>· {v.projekte} {t("tenders")}</small></td><td className={styles.rechts}>{v.marge > 0 ? "+" : ""}{v.marge} %</td><td className={styles.rechts}>{euro.format(v.summe)}</td></tr>)}
                  {rat.ignoriert.map((f) => <tr key={f} className={styles.ignoriert}><td>{f}</td><td colSpan={2} className={styles.rechts}><Marke farbe="var(--sev-kritisch)" />{t("ignored – unrealistic prices")}</td></tr>)}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <section className={styles.karte}>
        <h2 className={styles.abschnitt}>{t("Load a bidder document")}
          <Info text={t("The tender opening record (Submissionsergebnis / Niederschrift) as CSV or text: a table with bidder and amount, or one bidder per line. Check the preview, enter our own costs for that job, then save – the margins are remembered per company.")} /></h2>
        <label className={styles.ablage}>
          <input type="file" accept=".pdf,.xlsx,.csv,.txt,.tsv" onChange={(e) => { void datei(e.target.files?.[0]); e.target.value = ""; }} />
          {lesen.laeuft ? t("Reading the document …") : t("Choose bidder document")} <small>PDF · Excel · CSV · TXT</small>
        </label>
        <div className={styles.formular}>
          <label>{t("Project")}<input value={entwurf.projekt} placeholder={t("e.g. Kita Nord")} onChange={(e) => setEntwurf({ ...entwurf, projekt: e.target.value })} /></label>
          <label>{t("Date")}<input type="date" value={entwurf.datum} onChange={(e) => setEntwurf({ ...entwurf, datum: e.target.value })} /></label>
          <label>{t("Our own costs")}<input inputMode="decimal" placeholder="1.250.000" value={entwurf.selbstkosten} onChange={(e) => setEntwurf({ ...entwurf, selbstkosten: e.target.value })} /></label>
        </div>
        {lesen.methode && !lesen.laeuft && <p className={styles.leiseText}>{t(lesen.methode === "ki" ? "Read by the AI model – amounts checked against the document." : "Read with fixed rules.")}{lesen.hinweis && ` ${lesen.hinweis}`}</p>}
        {/* Manual entry: every row stays editable, also after reading a document. */}
        <div className={styles.zeilen}>
          {zeilen.map((z, i) => (
            <div key={i} className={styles.zeileEingabe}>
              <input aria-label={t("Bidder")} placeholder={t("Company")} value={z.firma} onChange={(e) => setZeilen(zeilen.map((x, j) => (j === i ? { ...x, firma: e.target.value } : x)))} />
              <input aria-label={t("Bid")} inputMode="decimal" placeholder="1.250.000" value={z.summe} onChange={(e) => setZeilen(zeilen.map((x, j) => (j === i ? { ...x, summe: e.target.value } : x)))} />
              <button type="button" className={styles.weg} aria-label={`${t("Remove")} ${z.firma}`} onClick={() => setZeilen(zeilen.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <button type="button" className={styles.leise} onClick={() => setZeilen([...zeilen, { firma: "", summe: "" }])}>+ {t("Add bidder")}</button>
        </div>
        {gelesen.length > 0 && (
          <div className={styles.rahmen}>
            <table className={styles.tabelle}>
              <thead><tr><th>{t("Rank")}</th><th>{t("Bidder")}</th><th className={styles.rechts}>{t("Bid")}</th><th className={styles.rechts}>{t("Margin over our costs")}</th><th>{t("Note")}</th></tr></thead>
              <tbody>
                {(vorschau.length ? vorschau : gelesen.map((g, i) => ({ ...g, rang: i + 1, marge: NaN, ausreisser: false }))).map((z) => (
                  <tr key={`${z.firma}-${z.rang}`}><td>{z.rang}</td><td>{z.firma}</td><td className={styles.rechts}>{euro.format(z.summe)}</td>
                    <td className={styles.rechts}>{Number.isNaN(z.marge) ? "–" : `${z.marge > 0 ? "+" : ""}${z.marge} %`}</td>
                    <td>{z.ausreisser && <><Marke farbe="var(--sev-kritisch)" />{t("Outlier – going very low, not our competition")}</>}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {gelesen.length > 0 && !(kosten > 0) && <p className={styles.leiseText}>{t("Enter our own costs to see each bidder's margin.")}</p>}
        <button type="button" className={styles.knopf} onClick={speichern} disabled={gelesen.length === 0}>+ {t("Save tender")} {gelesen.length > 0 && `(${gelesen.length} ${t("bids")})`}</button>
        {meldung && <p className={styles.fehler} role="alert">{meldung}</p>}
        {subs.length > 0 && (
          <ul className={styles.liste}>
            {subs.map((s) => (
              <li key={s.id}><span><b>{s.projekt}</b> · {s.datum} · {t("own costs")} {euro.format(s.selbstkosten)} · {s.gebote.length} {t("bids")}</span>
                <button type="button" className={styles.weg} aria-label={`${t("Remove")} ${s.projekt}`} onClick={() => setzen(subs.filter((x) => x.id !== s.id))}>×</button></li>
            ))}
          </ul>
        )}
        {subs.length > 0 && <button type="button" className={styles.leise} onClick={() => setzen([])}>{t("Remove all")}</button>}
      </section>
    </main>
  );
}
