"use client";

// Markup calculation and bid advice (report level 3): direct costs → BGK, AGK, W+G → bid total,
// then the tender opening result (competitor totals) → a bid just under the cheapest competitor, never below own costs.
import { useEffect, useMemo, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { AUFGREIFSCHWELLE, SPANNEN, STANDARD, gebot, kalkuliere, type Zuschlaege } from "@/lib/zuschlag";
import { auswerten, empfehle, lade as ladeSubmissionen, leseZeilen, speichere as speichereSubmissionen, type Submission } from "@/lib/wettbewerb";
import { Info } from "../info/Info";
import styles from "./angebot.module.css";

const SCHLUESSEL = "lv-zuschlag-v1";
const GEBOTE = "lv-gebote-v1";

export function Angebot({ ekt: ektVorschlag, projekt }: { ekt: number; projekt: string }) {
  const { e: einstellungen, t } = useEinstellungen();
  const [z, setZ] = useState<Zuschlaege>(STANDARD);
  const [ekt, setEkt] = useState<number | null>(null);
  const [gebote, setGebote] = useState("");
  const [gespeichert, setGespeichert] = useState(false);
  const [historie, setHistorie] = useState<Submission[]>([]);
  useEffect(() => { setHistorie(ladeSubmissionen()); }, [gespeichert]);
  const summen = useMemo(() => leseZeilen(gebote).map((g) => g.summe), [gebote]);
  useEffect(() => {
    try { setZ({ ...STANDARD, ...JSON.parse(window.localStorage.getItem(SCHLUESSEL) ?? "{}") }); setGebote(window.localStorage.getItem(GEBOTE) ?? ""); } catch { /* defaults */ }
  }, []);
  const aendern = (neu: Partial<Zuschlaege>) => { const n = { ...z, ...neu }; setZ(n); try { window.localStorage.setItem(SCHLUESSEL, JSON.stringify(n)); } catch { /* not kept */ } };
  const loc = einstellungen.sprache === "de" ? "de-DE" : "en-GB";
  const euro = new Intl.NumberFormat(loc, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

  const basis = ekt ?? ektVorschlag;
  const ergebnis = useMemo(() => {
    try { const k = kalkuliere(basis, z); return { k, g: gebot(k, summen, z) }; } catch (err) { return { fehler: (err as Error).message }; }
  }, [basis, z, summen]);

  const feld = (name: string, wert: number, setze: (n: number) => void, spanne?: readonly [number, number], einheit = "%") => (
    <label className={styles.feld}>
      <span>{t(name)}{spanne && <small> {spanne[0]}–{spanne[1]} %</small>}</span>
      <span className={styles.eingabe}><input type="number" step="any" min={0} value={wert} onChange={(ev) => setze(Number(ev.target.value) || 0)} /><i>{einheit}</i></span>
    </label>
  );
  const ausserhalb = (w: number, s: readonly [number, number]) => w < s[0] || w > s[1];

  return (
    <section className={styles.angebot} aria-label={t("Markup and bid")}>
      <h3 className={styles.titel}>{t("Markup and bid")}
        <Info text={t("Endsummen calculation: site overheads (BGK), general business costs (AGK) and risk + profit (W+G) as shares of the bid total. Ranges are orientation values from bauprofessor.de (BGK 5–12 %, AGK 8–20 %, W+G 3–8 % of turnover); use your company's own figures.")} /></h3>

      <div className={styles.raster}>
        <div className={styles.eingaben}>
          <label className={styles.feld}>
            <span>{t("Direct costs (EKT)")} <small>{t("default: estimated bill")}</small></span>
            <span className={styles.eingabe}><input type="number" step="any" min={0} value={Math.round(basis)} onChange={(ev) => setEkt(Number(ev.target.value) || 0)} /><i>€</i></span>
          </label>
          {feld("Site overheads (BGK)", z.bgkProzent, (n) => aendern({ bgkProzent: n }), SPANNEN.bgk)}
          <div className={styles.feld}>
            <span>{t("General business costs (AGK)")}<small> {SPANNEN.agk[0]}–{SPANNEN.agk[1]} %</small></span>
            <span className={styles.umschalter} role="radiogroup" aria-label="AGK">
              {(["prozent", "monat"] as const).map((m) => (
                <button key={m} type="button" role="radio" aria-checked={z.agkModus === m} onClick={() => aendern({ agkModus: m })}>{t(m === "prozent" ? "% of bid" : "€ per month")}</button>
              ))}
            </span>
          </div>
          {z.agkModus === "prozent" ? feld("AGK share", z.agkProzent, (n) => aendern({ agkProzent: n }))
            : <>{feld("AGK per month", z.agkMonat, (n) => aendern({ agkMonat: n }), undefined, "€")}{feld("Construction time", z.monate, (n) => aendern({ monate: n }), undefined, t("months"))}</>}
          {feld("Risk and profit (W+G)", z.wgProzent, (n) => aendern({ wgProzent: n }), SPANNEN.wg)}
          <label className={styles.feld}>
            <span>{t("Tender opening result")} <small>{t("one per line: company; total")}</small></span>
            <textarea rows={3} value={gebote} placeholder={"Muster Bau GmbH; 1.245.000\nNord Hochbau AG; 1.310.500"} onChange={(ev) => { setGebote(ev.target.value); setGespeichert(false); try { window.localStorage.setItem(GEBOTE, ev.target.value); } catch { /* not kept */ } }} />
          </label>
          {feld("Undercut the cheapest by", z.unterbieten, (n) => aendern({ unterbieten: n }))}
        </div>

        {"fehler" in ergebnis ? <p className={styles.warnung}>{t(ergebnis.fehler ?? "")}</p> : (() => {
          const { k, g } = ergebnis;
          return (
            <div className={styles.ergebnis}>
              <table className={styles.tabelle}>
                <tbody>
                  <tr><td>{t("Direct costs (EKT)")}</td><td>{euro.format(k.ekt)}</td></tr>
                  <tr><td>+ {t("Site overheads (BGK)")} {z.bgkProzent} %</td><td>{euro.format(k.bgk)}</td></tr>
                  <tr><td>+ {t("General business costs (AGK)")} {k.agkProzent} %</td><td>{euro.format(k.agk)}</td></tr>
                  <tr className={styles.zwischen}><td>= {t("Own costs")}</td><td>{euro.format(k.selbstkosten)}</td></tr>
                  <tr><td>+ {t("Risk and profit (W+G)")} {z.wgProzent} %</td><td>{euro.format(k.wg)}</td></tr>
                  <tr className={styles.summe}><td>= {t("Calculated bid")} <small>(+{k.zuschlagAufEkt} % {t("on EKT")})</small></td><td>{euro.format(k.angebot)}</td></tr>
                </tbody>
              </table>
              {(ausserhalb(z.bgkProzent, SPANNEN.bgk) || (z.agkModus === "prozent" ? ausserhalb(z.agkProzent, SPANNEN.agk) : ausserhalb(k.agkProzent, SPANNEN.agk)) || ausserhalb(z.wgProzent, SPANNEN.wg)) &&
                <p className={styles.hinweis}>{t("A markup is outside the usual range – check it against your company figures.")}</p>}

              <div className={styles.empfehlung} data-ok={g.warnungen.length === 0}>
                <span>{t("Recommended bid")}</span>
                <strong>{euro.format(g.empfohlen)}</strong>
                <small>
                  {g.naechstes === null ? t("Enter competitor totals for advice.")
                    : t({ kalkuliert: "Your calculation.", unterbietet: "{p} % under the cheapest competitor ({n}).", angehoben: "Raised to {p} % under the cheapest competitor ({n}) – you still win and keep more margin.", selbstkosten: "At own costs – going lower would lose money.", schwelle: "Kept at {s} % under the cheapest competitor ({n}) – lower triggers a price check (§ 16d VOB/A)." }[g.grund],
                      { p: z.unterbieten, n: euro.format(g.naechstes), s: AUFGREIFSCHWELLE })}
                </small>
                <dl>
                  <div><dt>{t("Risk and profit left")}</dt><dd style={{ color: g.wgProzent < 0 ? "var(--sev-kritisch)" : g.wgProzent < SPANNEN.wg[0] ? "var(--sev-mittel-text)" : "var(--sev-ok)" }}>{g.wgProzent} %</dd></div>
                  {g.naechstes !== null && <div><dt>{t("Place")}</dt><dd>{g.rang} / {summen.length + 1}</dd></div>}
                  {g.naechstes !== null && <div><dt>{t("Gap to cheapest competitor")}</dt><dd>{Math.round((1 - g.empfohlen / g.naechstes) * 1000) / 10} %</dd></div>}
                </dl>
                {summen.length > 0 && (
                  <button type="button" className={styles.speichern} disabled={gespeichert} onClick={() => {
                    speichereSubmissionen([...ladeSubmissionen(), { id: `${Date.now()}`, projekt, datum: new Date().toISOString().slice(0, 10), selbstkosten: k.selbstkosten, gebote: leseZeilen(gebote) }]);
                    setGespeichert(true);
                  }}>{gespeichert ? `✓ ${t("Saved to competitors")}` : t("Save result to competitors")}</button>
                )}
                {summen.length === 0 && historie.length > 0 && (() => {
                  const r = empfehle(k.selbstkosten, auswerten(historie), historie, { unterbieten: z.unterbieten, minMarge: 2 });
                  return r.vorhersagen.length > 0 && (
                    <p className={styles.historie}>
                      <b>{t("From competitor history")}: {euro.format(r.empfohlen)}</b> · {r.marge} % {t("margin")}
                      {r.siegquote !== null && <> · {t("would have won")} {r.siegquote} % {t("of past tenders")}</>}
                      <br /><small>{t("Cheapest serious bidder expected")}: {r.vorhersagen[0].firma} {euro.format(r.vorhersagen[0].summe)}{r.ignoriert.length > 0 && <> · {t("ignored")}: {r.ignoriert.join(", ")}</>} · <a href="/wettbewerb">{t("Competitors")} ›</a></small>
                    </p>
                  );
                })()}
                {g.warnungen.includes("teurer_als_alle") && <p className={styles.warnung}>{t("Your own costs are above the cheapest competitor – this job is hard to win without losing money.")}</p>}
              </div>
            </div>
          );
        })()}
      </div>
    </section>
  );
}
