"use client";

import { type FormEvent, useState } from "react";
import { api, type LV } from "@/lib/api";
import { abschliessen, lvAusJson } from "@/lib/abschluss";
import { historyApi, type HistoryCase } from "@/lib/history-api";
import { useT } from "@/lib/einstellungen";
import { Icon } from "../icon/Icon";
import { DateiWahl } from "../ui/DateiWahl";
import styles from "./history.module.css";

/** Reads our estimate or the final bill: JSON directly (report or BoQ), anything else through the backend importer. */
async function lies(datei: File): Promise<LV> {
  if (datei.name.toLowerCase().endsWith(".json")) {
    const lv = lvAusJson(JSON.parse(await datei.text()));
    if (!lv) throw new Error(`${datei.name}: no review report or BoQ found in this JSON.`);
    return lv;
  }
  return api.importiere(datei);
}

/** Team spec, UI step 7: after the job, our estimate and the real final bill go into the history database. */
export function ProjektAbschluss({ onFertig, offen = false }: { onFertig: (fall: HistoryCase) => void; offen?: boolean }) {
  const t = useT();
  const [schaetzung, setSchaetzung] = useState<File | null>(null);
  const [rechnung, setRechnung] = useState<File | null>(null);
  const [datum, setDatum] = useState(() => new Date().toISOString().slice(0, 10));
  const [notiz, setNotiz] = useState("");
  const [stand, setStand] = useState<{ art: "leer" | "laeuft" | "ok" | "fehler"; text: string }>({ art: "leer", text: "" });

  async function absenden(e: FormEvent) {
    e.preventDefault();
    if (!schaetzung || !rechnung) return;
    setStand({ art: "laeuft", text: t("Reading both files …") });
    try {
      const [geschaetzt, real] = await Promise.all([lies(schaetzung), lies(rechnung)]);
      // The history store needs unique OZ; duplicates keep their first occurrence.
      const gesehen = new Set<string>();
      const eindeutig = { ...geschaetzt, positionen: geschaetzt.positionen.filter((p) => !gesehen.has(p.oz) && gesehen.add(p.oz)) };
      const a = abschliessen(eindeutig, real);
      if (a.estimated_values.length === 0) throw new Error(t("The estimate has no prices to compare."));
      const fall = await historyApi.create({
        date: datum, estimated_values: a.estimated_values,
        lv: { name: geschaetzt.name, quelle: `${schaetzung.name} + ${rechnung.name}`, positionen: eindeutig.positionen.map((p) => ({ oz: p.oz, kurztext: p.kurztext })) },
      });
      const gespeichert = await historyApi.update(fall.case_id, { real_values: a.real_values, marks: a.marks, comments: notiz.trim() ? [notiz.trim()] : [] });
      const abweichungen = a.marks.filter((m) => m.status === "deviation").length;
      setStand({ art: "ok", text: t("Saved as {id}: {n} items compared, {d} deviations over 10 %, tags: {tags}.", {
        id: gespeichert.case_id, n: a.marks.length, d: abweichungen, tags: gespeichert.tags.join(", ") || "–" }) });
      onFertig(gespeichert);
    } catch (err) {
      setStand({ art: "fehler", text: err instanceof Error ? err.message : t("Unknown error.") });
    }
  }

  return (
    <details className={`${styles.glas} ${styles.abschluss}`} open={offen || undefined}>
      <summary><Icon name="folder" /> {t("Close a finished project")} <small>{t("our estimate + real final bill → history")}</small></summary>
      <form className={styles.abschlussForm} onSubmit={absenden}>
        <DateiWahl
          label={t("1 · Our estimate")}
          hint={t("report JSON or the BoQ")}
          accept=".json,.x83,.x84,.xlsx,.pdf"
          file={schaetzung}
          chooseLabel={t("Choose file")}
          onChange={setSchaetzung}
        />
        <DateiWahl
          label={t("2 · Real final bill")}
          hint={t("GAEB, Excel, PDF or JSON")}
          accept=".json,.x83,.x84,.x86,.xlsx,.pdf"
          file={rechnung}
          chooseLabel={t("Choose file")}
          onChange={setRechnung}
        />
        <label className={`${styles.feld} ${styles.datum}`}>
          <span>{t("Finished on")}</span>
          <input type="date" value={datum} onChange={(e) => setDatum(e.target.value)} />
        </label>
        <label className={`${styles.feld} ${styles.breit}`}>
          <span>{t("Note: why did it turn out this way?")} <i>{t("optional")}</i></span>
          <input value={notiz} onChange={(e) => setNotiz(e.target.value)} placeholder={t("e.g. ground water, extra formwork days")} />
        </label>
        <div className={styles.aktionen}>
          <button type="submit" className={styles.knopf} disabled={!schaetzung || !rechnung || stand.art === "laeuft"}>
            <Icon name="upload" /> {t("Save to history")}
          </button>
          {stand.text && <span className={stand.art === "fehler" ? styles.fehlerText : stand.art === "ok" ? styles.ok : styles.hinweis} role="status">{stand.text}</span>}
        </div>
        <p className={styles.hinweis}>{t("Items are matched by OZ. Each item within 10 % is marked confirmed, otherwise deviation; description and tags are generated by the AI step.")}</p>
      </form>
    </details>
  );
}
