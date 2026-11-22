"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEinstellungen } from "@/lib/einstellungen";
import {
  DOKUMENT_TYPEN, FORMATE, TABS, TYP_LABEL, datumText, filtereVault, groesseText, gruppiereNachLv, tabAusQuery, tagsAusText, vaultApi,
  type VaultEintrag, type VaultTab, type VaultTyp,
} from "@/lib/vault";
import { SegmentedControl } from "../ui/SegmentedControl";
import { DateiWahl } from "../ui/DateiWahl";
import { MargePdfKi } from "../marge/MargePdfKi";
import { Preise } from "../preise/Preise";
import { HistoryView } from "../history/HistoryView";
import { Einreichen } from "../einreichen/Einreichen";
import seite from "../history/history.module.css";
import eigene from "../preise/preise.module.css";
import styles from "./vault.module.css";

// The wizard restores the open report from this key (LvUpload, sessionStorage).
const AKTUELL = "lv-aktuell-v1";

/** t243: one page for everything stored locally: bills, regulations, price lists, price database, research, history. */
export function Vault() {
  const { t } = useEinstellungen();
  const router = useRouter();
  // The tab lives in the URL (?tab=), so the old routes and "Final bill" → history land on the right tab.
  const tab = tabAusQuery(useSearchParams().get("tab"));
  const wechsle = (neu: VaultTab) => router.replace(`/vault?tab=${neu}`, { scroll: false });
  const info = TABS.find((x) => x.id === tab)!;

  return (
    <div className={seite.seite}>
      <section className={seite.einleitung}>
        <p className={seite.eyebrow}>{t("Vault")}</p>
        <h1>{t("All documents and results in one place.")}</h1>
        <p className={seite.lead}>{t("Bills, regulations, price lists and competitor bid files from your analyses are filed here automatically, together with every report and research run. Everything stays on this computer.")}</p>
      </section>
      <div className={styles.tabs}>
        <SegmentedControl ariaLabel={t("Vault")} value={tab} onChange={wechsle} options={TABS.map((x) => ({ value: x.id, label: t(x.label) }))} />
      </div>
      {tab === "preisdatenbank" ? <div className={styles.eingebettet}><Preise /></div>
        : tab === "historie" ? <div className={styles.eingebettet}><HistoryView /></div>
        : tab === "einreichen" ? <div className={styles.eingebettet}><Einreichen /></div>
        : tab === "recherchen" ? <Ergebnisse />
        : <Dokumente key={tab} typ={info.typen![0]} />}
    </div>
  );
}

function useListe(typen: VaultTyp[]) {
  const [liste, setListe] = useState<VaultEintrag[] | null>(null);
  const [fehler, setFehler] = useState("");
  const schluessel = typen.join(",");
  const laden = useCallback(async () => {
    try {
      setListe(await vaultApi.liste(schluessel.split(",") as VaultTyp[]));
      setFehler("");
    } catch (f) {
      setListe(null);
      setFehler(f instanceof Error ? f.message : String(f));
    }
  }, [schluessel]);
  useEffect(() => { void laden(); }, [laden]);
  return { liste, fehler, laden };
}

function Dokumente({ typ }: { typ: VaultTyp }) {
  const { t, e } = useEinstellungen();
  const router = useRouter();
  const { liste, fehler, laden } = useListe([typ]);
  const [datei, setDatei] = useState<File | null>(null);
  const [meldung, setMeldung] = useState<{ art: "ok" | "fehler" | "laeuft"; text: string } | null>(null);
  const [suche, setSuche] = useState("");
  const [bearbeite, setBearbeite] = useState<{ id: string; name: string; tags: string } | null>(null);
  const formate = FORMATE[typ] ?? [];

  async function hochladen(d: File | null) {
    setDatei(d);
    if (!d) return;
    setMeldung({ art: "laeuft", text: t("Saving {name} …", { name: d.name }) });
    try {
      const vorher = liste?.length ?? 0;
      await vaultApi.hochladen(d, typ);
      const neu = await vaultApi.liste([typ]);
      setMeldung({ art: "ok", text: neu.length > vorher ? t("{name} saved in the vault.", { name: d.name }) : t("{name} is already in the vault.", { name: d.name }) });
      setDatei(null);
      void laden();
    } catch (f) {
      setMeldung({ art: "fehler", text: f instanceof Error ? f.message : String(f) });
    }
  }

  async function speichern() {
    if (!bearbeite) return;
    try {
      await vaultApi.aendern(bearbeite.id, { dateiname: bearbeite.name.trim() || undefined, tags: tagsAusText(bearbeite.tags) });
      setBearbeite(null);
      void laden();
    } catch (f) {
      setMeldung({ art: "fehler", text: f instanceof Error ? f.message : String(f) });
    }
  }

  async function loeschen(x: VaultEintrag) {
    if (!window.confirm(t("Delete {name} from the vault?", { name: x.dateiname }))) return;
    try { await vaultApi.loeschen(x.id); void laden(); } catch (f) { setMeldung({ art: "fehler", text: f instanceof Error ? f.message : String(f) }); }
  }

  const gezeigt = liste ? filtereVault(liste, suche) : [];
  return (
    <>
      <section className={`${seite.glas} ${eigene.karte}`} aria-label={t("Add to vault")}>
        <h2>{t("Add to vault")}</h2>
        <div className={eigene.wahlen}>
          <DateiWahl id={`vault-${typ}`} label={t(TYP_LABEL[typ])} file={datei} accept={formate.join(",")}
            hint={`${formate.map((f) => f.slice(1).toUpperCase()).join(", ")} · max. 10 MiB`}
            disabled={meldung?.art === "laeuft"} invalid={meldung?.art === "fehler"} chooseLabel={t("Choose file")}
            onChange={(d) => void hochladen(d)} />
        </div>
        <p className={eigene.hinweis}>{t(typ === "wettbewerb" ? "Competitor bid files you load on the margin page are filed here automatically. The same file is stored only once." : "Files used in an analysis on the start page are filed here automatically. The same file is stored only once.")}</p>
        <div aria-live="polite">{meldung && <p className={meldung.art === "fehler" ? eigene.fehler : eigene.hinweis} role={meldung.art === "fehler" ? "alert" : undefined}>{meldung.text}</p>}</div>
      </section>
      {typ === "wettbewerb" && <MargePdfKi onFertig={() => void laden()} />}

      <section className={`${seite.glas} ${eigene.karte}`} aria-label={t("Stored documents")}>
        <h2>{t("Stored documents")} {liste && <span className={eigene.hinweis}>{t("{a} of {b}", { a: gezeigt.length, b: liste.length })}</span>}</h2>
        {fehler ? <p className={eigene.hinweis} role="note">{t("The vault is unreachable: {fehler}", { fehler })}</p>
          : liste === null ? <p className={eigene.hinweis}>{t("Loading …")}</p>
          : (
            <>
              <div className={eigene.suche} role="search">
                <label>{t("Search")} <input type="search" value={suche} onChange={(ev) => setSuche(ev.target.value)} /></label>
              </div>
              {gezeigt.length === 0 ? <p className={eigene.hinweis}>{t(liste.length === 0 ? "Nothing stored yet." : "No documents match.")}</p> : (
                <div className={eigene.rahmen}>
                  <table className={eigene.tabelle}>
                    <thead><tr><th scope="col">{t("File")}</th><th scope="col">{t("Tags")}</th><th scope="col" className={eigene.rechts}>{t("Size")}</th><th scope="col">{t("Stored")}</th><th scope="col">{t("Owner")}</th><th scope="col"><span className={styles.versteckt}>{t("Actions")}</span></th></tr></thead>
                    <tbody>
                      {gezeigt.map((x) => (
                        <tr key={x.id}>
                          <td className={styles.name}>
                            {bearbeite?.id === x.id
                              ? <input aria-label={t("File name")} className={styles.eingabe} value={bearbeite.name} onChange={(ev) => setBearbeite({ ...bearbeite, name: ev.target.value })} />
                              : <>{x.dateiname}{x.lv_name && x.lv_name !== x.dateiname && <small className={styles.unter}>{x.lv_name}</small>}</>}
                          </td>
                          <td>
                            {bearbeite?.id === x.id
                              ? <input aria-label={t("Tags")} className={styles.eingabe} placeholder={t("comma separated")} value={bearbeite.tags} onChange={(ev) => setBearbeite({ ...bearbeite, tags: ev.target.value })} />
                              : <span className={seite.tags}>{x.tags.map((tag) => <span key={tag}>{tag}</span>)}</span>}
                          </td>
                          <td className={eigene.rechts}>{groesseText(x.groesse)}</td>
                          <td className={styles.datum}>{datumText(x.hochgeladen_am, e.sprache)}</td>
                          <td className={styles.datum}>{x.besitzer ?? "–"}</td>
                          <td className={styles.aktionen}>
                            {bearbeite?.id === x.id ? (
                              <>
                                <button type="button" className={seite.knopfZweit} onClick={() => void speichern()}>{t("Save")}</button>
                                <button type="button" className={seite.knopfZweit} onClick={() => setBearbeite(null)}>{t("Cancel")}</button>
                              </>
                            ) : (
                              <>
                                {x.typ === "wettbewerb" && !x.dateiname.toLowerCase().endsWith(".pdf") ? <button type="button" className={seite.knopfZweit} onClick={() => router.push(`/marge?vault=${encodeURIComponent(x.id)}`)}>{t("Use on the margin page")}</button> : ["lv", "regelwerk", "preisliste"].includes(x.typ) && <button type="button" className={seite.knopfZweit} onClick={() => router.push(`/?vault=${encodeURIComponent(x.id)}`)}>{t("Use in analysis")}</button>}
                                <a className={seite.knopfZweit + " " + styles.link} href={vaultApi.dateiUrl(x.id)} download={x.dateiname}>{t("Download")}</a>
                                <button type="button" className={seite.knopfZweit} onClick={() => setBearbeite({ id: x.id, name: x.dateiname, tags: x.tags.join(", ") })}>{t("Edit")}</button>
                                <button type="button" className={`${seite.knopfZweit} ${styles.gefahr}`} onClick={() => void loeschen(x)}>{t("Delete")}</button>
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
      </section>
    </>
  );
}

/** t248: every report and research run as its own version, grouped per bill; nothing is reused or cached. */
function Ergebnisse() {
  const { t, e } = useEinstellungen();
  const router = useRouter();
  const { liste, fehler, laden } = useListe(["bericht", "recherche", "preisrecherche", "auswertung"]);
  const [suche, setSuche] = useState("");
  const [meldung, setMeldung] = useState("");

  async function oeffnen(x: VaultEintrag) {
    if (x.typ !== "bericht") { window.open(vaultApi.dateiUrl(x.id), "_blank", "noopener"); return; }
    try {
      const bericht = await vaultApi.json<{ lv?: { name?: string } }>(x);
      window.sessionStorage.setItem(AKTUELL, JSON.stringify({ titel: bericht.lv?.name ?? x.dateiname, beispielId: null, bericht }));
      router.push("/");
    } catch (f) {
      setMeldung(f instanceof Error ? f.message : String(f));
    }
  }
  async function loeschen(x: VaultEintrag) {
    if (!window.confirm(t("Delete {name} from the vault?", { name: x.dateiname }))) return;
    try { await vaultApi.loeschen(x.id); void laden(); } catch (f) { setMeldung(f instanceof Error ? f.message : String(f)); }
  }

  const gruppen = liste ? gruppiereNachLv(filtereVault(liste, suche)) : [];
  return (
    <section className={`${seite.glas} ${eigene.karte}`} aria-label={t("Research")}>
      <h2>{t("Reports and research")} {liste && <span className={eigene.hinweis}>{t(liste.length === 1 ? "{n} version" : "{n} versions", { n: liste.length })}</span>}</h2>
      <p className={eigene.hinweis}>{t("Each analysis, web research, price research and AI evaluation is stored as a new version with a timestamp. Running it again researches anew; older versions stay here.")}</p>
      {meldung && <p className={eigene.fehler} role="alert">{meldung}</p>}
      {fehler ? <p className={eigene.hinweis} role="note">{t("The vault is unreachable: {fehler}", { fehler })}</p>
        : liste === null ? <p className={eigene.hinweis}>{t("Loading …")}</p>
        : (
          <>
            <div className={eigene.suche} role="search"><label>{t("Search")} <input type="search" value={suche} onChange={(ev) => setSuche(ev.target.value)} /></label></div>
            {gruppen.length === 0 ? <p className={eigene.hinweis}>{t(liste.length === 0 ? "No reports yet. Run an analysis on the start page." : "No documents match.")}</p>
              : gruppen.map((g) => (
                <details key={g.schluessel} className={styles.gruppe} open={gruppen.length <= 3}>
                  <summary><strong>{g.name === "Without bill" ? t(g.name) : g.name}</strong> <span className={eigene.hinweis}>{t(g.eintraege.length === 1 ? "{n} version" : "{n} versions", { n: g.eintraege.length })} · {datumText(g.eintraege[0].hochgeladen_am, e.sprache)}</span></summary>
                  <ul className={styles.versionen}>
                    {g.eintraege.map((x) => (
                      <li key={x.id}>
                        <span className={styles.typ}>{t(TYP_LABEL[x.typ])}{x.version ? ` · v${x.version}` : ""}</span>
                        <span className={styles.datum}>{datumText(x.hochgeladen_am, e.sprache)}</span>
                        <span className={styles.aktionen}>
                          <button type="button" className={seite.knopfZweit} onClick={() => void oeffnen(x)}>{t("Open")}</button>
                          <a className={seite.knopfZweit + " " + styles.link} href={vaultApi.dateiUrl(x.id)} download={x.dateiname}>{t("Download")}</a>
                          <button type="button" className={`${seite.knopfZweit} ${styles.gefahr}`} onClick={() => void loeschen(x)}>{t("Delete")}</button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
          </>
        )}
    </section>
  );
}
