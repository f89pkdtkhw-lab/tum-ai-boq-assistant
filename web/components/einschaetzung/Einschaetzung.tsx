"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type AiEvaluation, type Pruefbericht } from "@/lib/api";
import { einschaetzen, type Ampel } from "@/lib/einschaetzung";
import { BewertungsmodellWahl } from "@/components/bewertung/BewertungsmodellWahl";
import { useBewertungsmodell } from "@/lib/useBewertungsmodell";
import { deviationByTrade, historyApi, type HistoryCase } from "@/lib/history-api";
import { useEinstellungen } from "@/lib/einstellungen";
import { preisspiegel } from "@/lib/preise";
import { genauigkeit } from "@/lib/statistik";
import { KiBewertung } from "./KiBewertung";
import styles from "./einschaetzung.module.css";
import { Ring } from "../ring/Ring";

const FARBE: Record<Ampel, string> = { rot: "var(--sev-kritisch)", gelb: "var(--sev-mittel)", gruen: "var(--sev-ok)" };
/** Text colours: yellow needs a darker shade to be readable on light backgrounds. */
const TEXT: Record<Ampel, string> = { ...FARBE, gelb: "var(--sev-mittel-text)" };
const NAME: Record<Ampel, string> = { rot: "Serious findings", gelb: "Check these", gruen: "Fine" };
const euroVoll = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const euroKurz = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 2 });

export type Bewertungsdaten = ReturnType<typeof useEinschaetzung>;

/** Assessment for one report: history, price check, team score and the AI evaluation. Used by the header and the Overview. */
/** `laden=false` skips loading (used when a parent already provides the data). */
export function useEinschaetzung(bericht: Pruefbericht, laden = true) {
  const { e: einstellungen } = useEinstellungen();
  const [modell] = useBewertungsmodell();
  const [faelle, setFaelle] = useState<HistoryCase[] | null>(null);
  const [ki, setKi] = useState<{ daten: AiEvaluation | null; fehler: string }>({ daten: null, fehler: "" });
  useEffect(() => { if (laden) historyApi.list(null, 100).then(setFaelle).catch(() => setFaelle([])); }, [laden]);
  const gewerke = useMemo(() => (faelle ? deviationByTrade(faelle) : null), [faelle]);
  const preise = useMemo(() => preisspiegel(bericht.lv.positionen, faelle), [bericht, faelle]);
  const preisSignal = { auffaellig: preise.zaehler.gelb + preise.zaehler.rot, verglichen: preise.zaehler.gruen + preise.zaehler.gelb + preise.zaehler.rot, rot: preise.zaehler.rot };
  const e = useMemo(() => einschaetzen(bericht, gewerke, preisSignal, modell),
    // preisSignal is derived from preise
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bericht, gewerke, preise, modell]);

  // AI evaluation of the whole BoQ: evidence computed here, answer from the server's model boundary.
  useEffect(() => {
    if (faelle === null || !laden) return;
    const echte = bericht.findings.filter((f) => !f.regel_id.startsWith("MOCK_"));
    const ausreisser = preise.gruppen.flatMap((g) => g.positionen.filter((p) => p.stufe !== "gruen").map((p) => ({ oz: p.oz, work: g.kurztext, deviation_pct: Math.round(p.abweichung * 100) })))
      .sort((a, b) => Math.abs(b.deviation_pct) - Math.abs(a.deviation_pct)).slice(0, 20);
    let aktiv = true;
    setKi({ daten: null, fehler: "" });
    api.aiEvaluation({
      name: bericht.lv.name, items: bericht.lv.positionen.length, score: e.punkte, traffic_light: e.ampel,
      stated_total: e.kosten.angegeben, recalculated_total: e.kosten.nachgerechnet, with_optional_total: e.kosten.risiko, history_expected_total: e.kosten.historie,
      serious_items: e.positionen.rot,
      findings_by_rule: echte.reduce<Record<string, number>>((r, f) => ({ ...r, [f.regel_id]: (r[f.regel_id] ?? 0) + 1 }), {}),
      change_order_findings: echte.filter((f) => f.kategorie !== "fehler").length,
      price_outliers: ausreisser, unusual_prices: preisSignal.auffaellig,
      trades: (gewerke ?? []).filter((g) => g.avgDeviation !== null).slice(0, 20).map((g) => ({ trade: g.trade, avg_overrun_pct: Math.round((g.avgDeviation ?? 0) * 10) / 10, projects: g.projects })),
      past_overrun_share: genauigkeit(faelle).ueberzogen, language: einstellungen.sprache,
    }).then((daten) => { if (aktiv) setKi({ daten, fehler: "" }); })
      .catch((err: Error) => { if (aktiv) setKi({ daten: null, fehler: err.message }); });
    return () => { aktiv = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [faelle, e, einstellungen.sprache]);
  const kiKosten = ki.daten?.predictions.find((p) => p.unit === "EUR" && p.low !== null && p.high !== null && p.low > 0) ?? null;
  // Recommendations shown to the user: the local ones that ask for action plus the AI's.
  const empfehlungen = e.zaehler.empfehlungen + (ki.daten?.recommendations.length ?? 0);
  return { e, faelle, gewerke, ki, kiKosten, empfehlungen, preise };
}

/** One-glance verdict for the Overview tab: score donut, deductions, real vs. estimated cost, recommendations. */
export function Einschaetzung({ daten, onAmpel }: { daten: Bewertungsdaten; onAmpel: (a: Ampel) => void }) {
  const { t } = useEinstellungen();
  const { e, faelle, ki, kiKosten } = daten;

  const balken: { name: string; quelle: string; wert: number | null; hinweis?: string }[] = [
    { name: "Stated in the BoQ", quelle: "extracted", wert: e.kosten.angegeben },
    { name: "Recalculated: quantity × unit price", quelle: "extracted", wert: e.kosten.nachgerechnet },
    { name: "With optional and alternative items", quelle: "rules", wert: e.kosten.risiko },
    { name: "Expected from past projects", quelle: "history", wert: e.kosten.historie, hinweis: faelle === null ? "Loading history…" : "No matching past projects" },
    { name: "AI estimate (upper end)", quelle: "model", wert: kiKosten?.high ?? null, hinweis: ki.fehler ? "AI evaluation unavailable" : "Waiting for the AI evaluation…" },
  ];
  const max = Math.max(1, ...balken.map((b) => b.wert ?? 0));

  return (
    <section className={styles.karte} aria-labelledby="urteil-titel">
      <div className={styles.oben}>
        <div className={styles.kreisSpalte}>
          <Ring teile={(["rot", "gelb", "gruen"] as Ampel[]).map((a) => ({ wert: e.positionen[a], farbe: FARBE[a] }))}
            mitte={e.score.toFixed(1)} unter="/ 10" farbe={TEXT[e.ampel]} beschriftung={`${t("Assessment")}: ${e.score} / 10`} />
          <ul className={styles.legende}>
            {(["rot", "gelb", "gruen"] as Ampel[]).map((a) => (
              <li key={a}>
                <button type="button" onClick={() => onAmpel(a)}>
                  <span className={styles.punkt} style={{ background: FARBE[a] }} />{t(NAME[a])} <strong>{e.positionen[a].toLocaleString("en-GB")}</strong>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className={styles.urteilSpalte}>
          <p className={styles.kicker}>{t("Assessment")} · {t("starts at 10, deductions below")}</p>
          <BewertungsmodellWahl />
          <h3 id="urteil-titel" className={styles.urteil} style={{ color: TEXT[e.ampel] }}>{t(e.urteil)}</h3>
          <ul className={styles.faktoren}>
            {e.faktoren.map((f) => (
              <li key={f.name}><span className={styles.punkt} style={{ background: FARBE[f.ampel] }} />{t(f.name, f.werte)}<strong>{f.wert}</strong></li>
            ))}
          </ul>
        </div>
      </div>

      <div className={styles.block}>
        <h4 className={styles.abschnitt}>{t("Cost: real numbers vs. estimates")}</h4>
        <ul className={styles.balkenListe}>
          {balken.map((b) => (
            <li key={b.name} className={b.wert === null ? styles.leer : undefined}>
              <span className={styles.balkenName}>{t(b.name)} <span className={styles.quelle}>{t(b.quelle)}</span></span>
              <span className={styles.balkenSpur}>
                {b.wert !== null && <span className={`${styles.balkenWert} ${styles[`q_${b.quelle}`]}`} style={{ width: `${(b.wert / max) * 100}%` }} />}
              </span>
              <span className={styles.betrag} title={b.wert === null ? undefined : euroVoll.format(b.wert)}>
                {b.wert === null ? t(b.hinweis ?? "–") : euroKurz.format(b.wert)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.block}>
        <h4 className={styles.abschnitt}>{t("What to do")}</h4>
        <ol className={styles.empfehlungen}>
          {e.empfehlungen.map((r) => (
            <li key={r.text}>
              <span className={styles.punkt} style={{ background: FARBE[r.ampel] }} />
              <span>{t(r.text, r.werte && Object.fromEntries(Object.entries(r.werte).map(([k, v]) => [k, k === "euro" ? euroVoll.format(Number(v)) : v])))}</span>
            </li>
          ))}
        </ol>
      </div>
      <KiBewertung daten={ki.daten} fehler={ki.fehler} />
    </section>
  );
}
