"use client";

import Link from "next/link";
import { useEinstellungen } from "@/lib/einstellungen";
import styles from "./anleitung.module.css";

type Schritt = { titel: string; text: string[]; link?: { href: string; text: string } };
type Text = { kicker: string; titel: string; lead: string; farben: string; stufen: [string, string][]; schritte: Schritt[]; tipps: string; tippListe: string[] };

const KLEIN = "/?beispiel=synthetisch-rohbau";
const GROSS = "/?beispiel=synthetisch-gross";

// Kept here rather than in the i18n dictionary: long prose reads better as whole paragraphs per language.
const TEXT: Record<"en" | "de", Text> = {
  en: {
    kicker: "Tutorial", titel: "Review a BoQ in five minutes",
    lead: "Follow the steps in order. Each one has a link that opens the right screen with example data, so you can try it while you read.",
    farben: "The colour code used everywhere",
    stufen: [["kritisch", "Critical – fix before bidding"], ["hoch", "High – likely costs money"], ["mittel", "Medium – check it"], ["niedrig", "Low – minor"], ["ok", "No findings – fine"]],
    schritte: [
      { titel: "Load a BoQ", text: ["On Upload & report, drop a GAEB, Excel, PDF or LV-JSON file onto the card and press Review file.", "No file at hand? Pick the small example (30 items) or the large one (about 2,500 items). Only the progress is shown while it runs."], link: { href: KLEIN, text: "Load the small example" } },
      { titel: "Read the overview", text: ["The tiles show how many items and findings there are, how many are critical and the euro impact the review could prove.", "The bar shows every item coloured by its worst finding. Click a colour to jump straight to those findings.", "Look at these first lists the items to check before anything else."], link: { href: GROSS, text: "See the overview of the large example" } },
      { titel: "Work through the findings", text: ["Open the Findings tab. Filters are folded away; open Filter findings to narrow by category, severity or your own review status.", "Click a finding to see its explanation, suggestion and source on the right. Set it to Confirmed or Dismissed and add a comment; this is saved in your browser."] },
      { titel: "Check items and their history", text: ["The Items tab lists every item with a coloured stripe. Use Title structure or the search (press /) to find a section or an OZ.", "In the details of an item, open History from past projects: it shows similar items from earlier jobs with estimate, actual and deviation, green to red."] },
      { titel: "Ask the client and export", text: ["Bidder questions turns risks and change-order findings into questions you can copy in one click.", "Quantities sums contract quantities per unit; click a unit to filter the items.", "Export report creates PDF or Excel for your team; Download JSON keeps the full report."] },
      { titel: "Close the project and learn from it", text: ["After the job, open Submit → Final bill in the menu and upload our estimate and the real final bill. Every item is compared and marked confirmed or deviation.", "History keeps these cases; the next evaluation uses them for the ± estimate and the advice on which trades to price carefully."], link: { href: "/einreichen#schluss", text: "Close a project" } },
      { titel: "Make it yours", text: ["In Settings choose English or Deutsch, a light, dark or automatic theme (dark from 19:00 to 07:00) and a compact density that fits more rows on screen.", "You can also clear past loads and saved review statuses there."], link: { href: "/einstellungen", text: "Open settings" } },
    ],
    tipps: "Good to know", tippListe: [
      "Every finding names its OZ and whether a fixed rule or the model produced it. Entries marked Demonstration come from the offline mock and are not real findings.",
      "Uploaded files are read for the review only and are not stored. Your statuses and comments stay in this browser.",
      "History is synthetic mock data until the team's history service is connected.",
    ],
  },
  de: {
    kicker: "Anleitung", titel: "Ein LV in fünf Minuten prüfen",
    lead: "Gehe die Schritte der Reihe nach durch. Jeder Schritt hat einen Link, der die passende Ansicht mit Beispieldaten öffnet, damit du beim Lesen gleich ausprobieren kannst.",
    farben: "Der Farbcode, der überall gilt",
    stufen: [["kritisch", "Kritisch – vor der Abgabe beheben"], ["hoch", "Hoch – kostet wahrscheinlich Geld"], ["mittel", "Mittel – prüfen"], ["niedrig", "Niedrig – geringfügig"], ["ok", "Ohne Befund – in Ordnung"]],
    schritte: [
      { titel: "LV laden", text: ["Unter Hochladen & Bericht eine GAEB-, Excel-, PDF- oder LV-JSON-Datei auf die Karte ziehen und Datei prüfen drücken.", "Keine Datei zur Hand? Wähle das kleine Beispiel (30 Positionen) oder das große (rund 2.500 Positionen). Während der Prüfung siehst du nur den Fortschritt."], link: { href: KLEIN, text: "Kleines Beispiel laden" } },
      { titel: "Überblick lesen", text: ["Die Kacheln zeigen Positionen, Befunde, kritische Befunde und die belegte Euro-Wirkung.", "Der Balken zeigt jede Position in der Farbe ihres schwersten Befunds. Ein Klick auf eine Farbe springt direkt zu diesen Befunden.", "Zuerst ansehen listet die Positionen, die du vor allem anderen prüfen solltest."], link: { href: GROSS, text: "Überblick des großen Beispiels ansehen" } },
      { titel: "Befunde abarbeiten", text: ["Öffne den Reiter Befunde. Die Filter sind eingeklappt; öffne Befunde filtern, um nach Kategorie, Schwere oder deinem Prüfstatus einzugrenzen.", "Klicke einen Befund an, um rechts Begründung, Vorschlag und Quelle zu sehen. Setze ihn auf Bestätigt oder Verworfen und ergänze einen Kommentar; das wird in deinem Browser gespeichert."] },
      { titel: "Positionen und ihre Historie prüfen", text: ["Der Reiter Positionen zeigt jede Position mit farbigem Streifen. Mit Titelstruktur oder der Suche (Taste /) findest du einen Abschnitt oder eine OZ.", "In den Details einer Position öffnest du Historie aus früheren Projekten: ähnliche Positionen früherer Aufträge mit Schätzung, Ist-Wert und Abweichung, von grün bis rot."] },
      { titel: "Bieterfragen stellen und exportieren", text: ["Bieterfragen macht aus Risiko- und Nachtragsbefunden Fragen, die du mit einem Klick kopierst.", "Mengen summiert die Vertragsmengen je Einheit; ein Klick auf eine Einheit filtert die Positionen.", "Bericht exportieren erzeugt PDF oder Excel für dein Team; JSON herunterladen sichert den vollständigen Bericht."] },
      { titel: "Projekt abschließen und daraus lernen", text: ["Nach dem Auftrag im Menü Einreichen → Schlussrechnung öffnen und unsere Schätzung sowie die echte Schlussrechnung hochladen. Jede Position wird verglichen und als bestätigt oder Abweichung markiert.", "Die Historie speichert diese Fälle; die nächste Auswertung nutzt sie für die ±-Schätzung und den Hinweis, welche Gewerke vorsichtig zu kalkulieren sind."], link: { href: "/einreichen#schluss", text: "Projekt abschließen" } },
      { titel: "Nach deinen Wünschen einstellen", text: ["Unter Einstellungen wählst du English oder Deutsch, eine helle, dunkle oder automatische Darstellung (dunkel von 19:00 bis 07:00) und eine kompakte Dichte für mehr Zeilen.", "Dort kannst du auch frühere Ladevorgänge und gespeicherte Prüfstatus löschen."], link: { href: "/einstellungen", text: "Einstellungen öffnen" } },
    ],
    tipps: "Gut zu wissen", tippListe: [
      "Jeder Befund nennt seine OZ und ob eine feste Regel oder das Modell ihn erzeugt hat. Einträge mit Demonstration stammen aus dem Offline-Mock und sind keine echten Befunde.",
      "Hochgeladene Dateien werden nur für die Prüfung gelesen und nicht gespeichert. Prüfstatus und Kommentare bleiben in diesem Browser.",
      "Die Historie besteht aus synthetischen Mock-Daten, bis der Historie-Dienst des Teams angebunden ist.",
    ],
  },
};

export function Anleitung() {
  const { e } = useEinstellungen();
  const x = TEXT[e.sprache];
  return (
    <main className={styles.seite}>
      <header>
        <p className={styles.kicker}>{x.kicker}</p>
        <h1 className={styles.titel}>{x.titel}</h1>
        <p className={styles.lead}>{x.lead}</p>
      </header>

      <section className={styles.karte} aria-labelledby="farben-titel">
        <h2 id="farben-titel" className={styles.abschnitt}>{x.farben}</h2>
        <div className={styles.skala} aria-hidden="true">{x.stufen.map(([s]) => <span key={s} style={{ background: `var(--sev-${s})` }} />)}</div>
        <ul className={styles.stufen}>
          {x.stufen.map(([s, name]) => <li key={s}><span className={styles.punkt} style={{ background: `var(--sev-${s})` }} />{name}</li>)}
        </ul>
      </section>

      <ol className={styles.schritte}>
        {x.schritte.map((s, i) => (
          <li key={s.titel} className={styles.karte}>
            <div className={styles.nummer} aria-hidden="true">{i + 1}</div>
            <div className={styles.inhalt}>
              <h2 className={styles.abschnitt}>{s.titel}</h2>
              {s.text.map((p) => <p key={p}>{p}</p>)}
              {s.link && <Link className={styles.knopf} href={s.link.href}>{s.link.text} →</Link>}
            </div>
          </li>
        ))}
      </ol>

      <section className={styles.karte} aria-labelledby="tipps-titel">
        <h2 id="tipps-titel" className={styles.abschnitt}>{x.tipps}</h2>
        <ul className={styles.tipps}>{x.tippListe.map((tp) => <li key={tp}>{tp}</li>)}</ul>
      </section>
    </main>
  );
}
