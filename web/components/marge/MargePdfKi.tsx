"use client";

// t271: "Read PDF with AI" for the vault tab (and any other caller). Same endpoint as the margin page.
import { useEffect, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { TYP_LABEL, datumText, vaultApi, type VaultEintrag } from "@/lib/vault";
import { api, type MargePdfAntwort } from "@/lib/api";
import { filtereVaultPdfs, istPdfName, margeVergleichHref, xlsxAusMargeAntwort } from "@/lib/marge-pdf";
import { AuswahlMenue } from "../ui/AuswahlMenue";
import { DateiWahl } from "../ui/DateiWahl";
import seite from "../history/history.module.css";
import eigene from "../preise/preise.module.css";
import styles from "../vault/vault.module.css";

export function MargePdfKi({ onFertig }: { onFertig?: (xlsx: File, antwort: MargePdfAntwort) => void }) {
  const { t, e } = useEinstellungen();
  const [pdf, setPdf] = useState<File | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [hinweis, setHinweis] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [download, setDownload] = useState<{ name: string; url: string; href?: string } | null>(null);
  const [vaultListe, setVaultListe] = useState<VaultEintrag[] | null>(null);

  useEffect(() => () => { if (download) URL.revokeObjectURL(download.url); }, [download]);

  async function starten(file: File | null) {
    if (!file) return;
    if (!istPdfName(file.name)) {
      setFehler(t("Please choose a PDF file."));
      return;
    }
    setPdf(file);
    setFehler(null);
    setHinweis(null);
    setOk(null);
    setLaeuft(true);
    try {
      const antwort = await api.margePdf(file);
      const xlsx = xlsxAusMargeAntwort(antwort);
      setDownload((alt) => {
        if (alt) URL.revokeObjectURL(alt.url);
        return {
          name: antwort.dateiname,
          url: URL.createObjectURL(xlsx),
          href: antwort.vault?.id ? margeVergleichHref(antwort.vault.id) : undefined,
        };
      });
      setOk(t("The Excel was saved in the vault as a new version."));
      if (antwort.hinweis) setHinweis(antwort.hinweis);
      onFertig?.(xlsx, antwort);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : String(err));
    } finally {
      setLaeuft(false);
    }
  }

  async function vaultOeffnen() {
    try {
      setFehler(null);
      setVaultListe(filtereVaultPdfs(await vaultApi.liste()));
    } catch {
      setFehler(t("The vault is unreachable."));
    }
  }

  return (
    <section className={`${seite.glas} ${eigene.karte}`} aria-label={t("Read PDF with AI")}>
      <h2>{t("Read PDF with AI")}</h2>
      <p className={eigene.hinweis}>{t("A competitor or offer PDF. The configured AI (Claude or Grok Bot) reads item numbers, texts, quantities, units, unit prices, totals and bidder names and builds the Excel the margin page uses. The file is stored in the vault as a new version.")}</p>
      <div className={eigene.wahlen}>
        <DateiWahl id="vault-marge-pdf-ki" label={t("Read PDF with AI")} file={pdf} accept=".pdf,application/pdf"
          hint={t("PDF · max. 10 MiB")} disabled={laeuft} invalid={!!fehler}
          chooseLabel={laeuft ? t("Reading the PDF with the AI … this can take a few minutes.") : t("Choose PDF")}
          onChange={(d) => { void starten(d); }} />
      </div>
      <div className={styles.kiAktionen}>
        <AuswahlMenue knopfKlasse={seite.knopfZweit} disabled={laeuft} label={t("Choose PDF from vault")}
          knopfInhalt={t("Choose PDF from vault")} leerText={t("The vault has no PDF files yet.")}
          onOeffnen={() => void vaultOeffnen()} onSchliessen={() => setVaultListe(null)}
          eintraege={vaultListe && vaultListe.slice(0, 30).map((x) => ({
            key: x.id,
            label: `${x.dateiname} · ${t(TYP_LABEL[x.typ])} · ${datumText(x.hochgeladen_am, e.sprache)}`,
            onClick: () => { setVaultListe(null); void vaultApi.alsDatei(x).then((d) => starten(d)); },
          }))} />
        {download && (
          <a className={seite.knopfZweit + " " + styles.link} href={download.url} download={download.name}>{t("Download Excel")}</a>
        )}
        {download?.href && (
          <a className={seite.knopfZweit + " " + styles.link} href={download.href}>{t("Open in margin comparison")}</a>
        )}
      </div>
      <div aria-live="polite">
        {ok && <p className={eigene.hinweis}>{ok}</p>}
        {hinweis && <p className={eigene.hinweis}>{t(hinweis)}</p>}
        {fehler && <p className={eigene.fehler} role="alert">{fehler}</p>}
      </div>
    </section>
  );
}
