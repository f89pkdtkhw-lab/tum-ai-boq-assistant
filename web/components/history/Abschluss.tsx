"use client";

import { type FormEvent, useState } from "react";
import {
  ABRECHNUNG_FORMATE, ABSCHLUSS_ROUTE, abschlussFehler, abschlussForm, BERICHT_FORMATE, pruefeAbschluss, vergleich,
  type AbschlussEingabe, type DbRecord,
} from "@/lib/abschluss";
import styles from "./history.module.css";
import eigene from "./abschluss.module.css";

const datum = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const LEER: AbschlussEingabe = { bericht: null, abrechnung: null, beschreibung: "", tags: "", notiz: "" };

async function senden(form: FormData): Promise<DbRecord> {
  const antwort = await fetch(ABSCHLUSS_ROUTE, { method: "POST", body: form });
  const body = await antwort.json().catch(() => ({}));
  if (!antwort.ok) {
    const text = typeof body.detail === "string" ? body.detail : `Request failed (HTTP ${antwort.status}).`;
    throw Object.assign(new Error(text), { status: antwort.status });
  }
  return body as DbRecord;
}

/** "Project finished": upload our report/estimate and the real final bill (issue #106). */
export function Abschluss() {
  const [e, setE] = useState<AbschlussEingabe>(LEER);
  const [gezeigt, setGezeigt] = useState(false);
  const [zustand, setZustand] = useState<{ art: "leer" | "laeuft" | "fertig" | "fehler"; text?: string; record?: DbRecord }>({ art: "leer" });
  const fehler = pruefeAbschluss(e);
  const busy = zustand.art === "laeuft";

  async function absenden(event: FormEvent) {
    event.preventDefault();
    setGezeigt(true);
    if (Object.keys(fehler).length > 0 || busy) return;
    setZustand({ art: "laeuft" });
    try {
      setZustand({ art: "fertig", record: await senden(abschlussForm(e)) });
    } catch (f) {
      setZustand({ art: "fehler", text: abschlussFehler(f, e).text });
    }
  }

  const r = zustand.record;
  const v = r ? vergleich(r) : null;
  return (
    <section className={`${styles.glas} ${eigene.abschluss}`} aria-labelledby="abschluss-titel">
      <h2 id="abschluss-titel">Project finished</h2>
      <p className={eigene.hinweis}>Upload our report or estimate and the real final bill. The server parses both and stores expected and actual values per item.</p>
      <form className={eigene.formular} onSubmit={absenden} noValidate>
        {([
          ["bericht", "Our report or estimate", BERICHT_FORMATE],
          ["abrechnung", "Real final bill", ABRECHNUNG_FORMATE],
        ] as const).map(([feld, name, formate]) => (
          <div key={feld} className={eigene.feld}>
            <label htmlFor={`abschluss-${feld}`}>{name}</label>
            <input id={`abschluss-${feld}`} type="file" accept={formate.join(",")} disabled={busy}
              aria-invalid={gezeigt && !!fehler[feld]} aria-describedby={`abschluss-${feld}-info`}
              onChange={(ev) => setE({ ...e, [feld]: ev.target.files?.[0] ?? null })} />
            <span id={`abschluss-${feld}-info`} className={gezeigt && fehler[feld] ? eigene.fehler : eigene.hinweis}>
              {gezeigt && fehler[feld] ? fehler[feld] : `${formate.map((f) => f.slice(1).toUpperCase()).join(", ")} · max. 10 MiB`}
            </span>
          </div>
        ))}
        <div className={eigene.feld}>
          <label htmlFor="abschluss-beschreibung">Description <span className={eigene.hinweis}>(optional, generated if empty)</span></label>
          <input id="abschluss-beschreibung" type="text" value={e.beschreibung} disabled={busy} onChange={(ev) => setE({ ...e, beschreibung: ev.target.value })} />
        </div>
        <div className={eigene.feld}>
          <label htmlFor="abschluss-tags">Tags <span className={eigene.hinweis}>(optional, comma-separated)</span></label>
          <input id="abschluss-tags" type="text" value={e.tags} disabled={busy} onChange={(ev) => setE({ ...e, tags: ev.target.value })} />
        </div>
        <div className={eigene.feld}>
          <label htmlFor="abschluss-notiz">Note / marks <span className={eigene.hinweis}>(optional)</span></label>
          <textarea id="abschluss-notiz" rows={2} value={e.notiz} disabled={busy} onChange={(ev) => setE({ ...e, notiz: ev.target.value })} />
        </div>
        <div>
          <button type="submit" className={styles.knopf} disabled={busy}>{busy ? "Uploading and parsing …" : "Save finished project"}</button>
        </div>
      </form>
      <div aria-live="polite">
        {zustand.art === "fehler" && <p className={eigene.fehler} role="alert">{zustand.text}</p>}
        {r && v && (
          <div className={eigene.ergebnis}>
            <p><strong>Saved as record {r.id}</strong> · {datum.format(new Date(r.date.replace(" ", "T")))}</p>
            <p>{r.description}</p>
            {r.tags.length > 0 && <p className={styles.tags}>{r.tags.map((t) => <span key={t}>{t}</span>)}</p>}
            <p className={eigene.hinweis}>{v.beide} items in both files · {v.nurSoll} only in our report · {v.nurIst} only in the final bill</p>
            {r.note && <p>Note: {r.note}</p>}
            {(r.warnungen ?? []).length > 0 && (
              <ul className={eigene.warnungen}>{r.warnungen!.map((w, i) => <li key={i}>{w}</li>)}</ul>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
