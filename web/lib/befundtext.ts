// Display texts for findings. The backend rules write English; German comes from phrase patterns here.
// Numbers, OZ and quoted names are kept. The technical ranking tail ("Priority view: …") is removed for reading.
import type { Finding } from "./api";
import type { Sprache } from "./i18n";

const SCHLUSS = /\s*(Priority view:|Review remainder:)[\s\S]*$/;

const BAUTEIL: Record<string, string> = {
  "floor slab": "Bodenplatte", "basement wall": "Kellerwand", roof: "Dach", wall: "Wand", ceiling: "Decke", foundation: "Fundament",
};

// [pattern, German replacement] applied in order; whole sentences first, then phrases.
const DE: [RegExp, string][] = [
  [/^Arithmetic error in total price$/, "Rechenfehler im Gesamtpreis"],
  [/^Missing unit$/, "Einheit fehlt"], [/^Missing quantity$/, "Menge fehlt"], [/^Missing detailed description$/, "Langtext fehlt"],
  [/^Duplicate item number$/, "Doppelte OZ"], [/^Demonstration \(Mock\) – no domain review$/, "Demonstration (Mock) – keine fachliche Prüfung"],
  [/^Optional work$/, "Bedarfsleistung"], [/^Alternative work$/, "Wahlleistung"], [/^Supplementary work$/, "Zulageleistung"],
  [/^Lump-sum scope$/, "Pauschaler Leistungsumfang"], [/^Hourly work$/, "Stundenlohnarbeiten"], [/^Unspecified demand$/, "Unbestimmter Bedarf"],
  [/^Unusual unit spelling$/, "Ungewöhnliche Schreibweise der Einheit"],
  [/^Unusual layer area for (.+)$/, "Ungewöhnliche Schichtfläche: $1"],
  [/^Correct the total price to quantity × unit price\.$/, "Gesamtpreis auf Menge × Einheitspreis korrigieren."],
  [/^Add the unit specified in the work description\.$/, "Die in der Leistungsbeschreibung genannte Einheit ergänzen."],
  [/^Ask the client for the quantity or determine it by measurement\.$/, "Menge beim Auftraggeber erfragen oder durch Aufmaß ermitteln."],
  [/^Add the complete work description\.$/, "Vollständige Leistungsbeschreibung ergänzen."],
  [/^Renumber one item to restore unique item numbers\.$/, "Eine Position umnummerieren, damit jede OZ eindeutig ist."],
  [/^Implement and validate fixed review rules; do not count the mock as a finding\.$/, "Feste Prüfregeln umsetzen und prüfen; den Mock nicht als Befund zählen."],
  [/^Check the area against measurements or plans; explain overhangs or partial areas in the detailed description\.$/,
    "Fläche mit Aufmaß oder Plänen abgleichen; Überstände oder Teilflächen im Langtext erläutern."],
  [/Under which conditions will this optional work be instructed, and what quantity is expected\?/, "Unter welchen Bedingungen wird diese Bedarfsleistung beauftragt, und welche Menge ist zu erwarten?"],
  [/Which alternative is to be selected, and which other OZ does it replace\?/, "Welche Alternative wird gewählt, und welche andere OZ ersetzt sie?"],
  [/To which base OZ and quantities does this supplement apply\?/, "Auf welche Grund-OZ und Mengen bezieht sich diese Zulage?"],
  [/Which services and scope boundaries are included in this lump sum\?/, "Welche Leistungen und Grenzen umfasst diese Pauschale?"],
  [/What hours are expected, and how will the instructed hours be recorded\?/, "Welche Stunden sind zu erwarten, und wie werden angeordnete Stunden erfasst?"],
  [/What measurable demand and instruction criteria define the required quantity\?/, "Welcher messbare Bedarf und welche Anordnungskriterien bestimmen die Menge?"],
  [/^(\S+) × (\S+) = (\S+), supplied total price (\S+)\.$/, "$1 × $2 = $3, angegebener Gesamtpreis $4."],
  [/^Missing unit\.$/, "Einheit fehlt."], [/^Quantity unknown; do not treat it as zero\.$/, "Menge unbekannt; nicht als null behandeln."],
  [/^Detailed description is empty\.$/, "Langtext ist leer."],
  [/^(\d+) items share OZ (\S+); distinct section paths preserved/, "$1 Positionen teilen die OZ $2; unterschiedliche Titelpfade bleiben erhalten"],
  [/^Demonstration: offline mock showing the report contract\. No actual finding or model request\.$/, "Demonstration: Offline-Mock zeigt das Berichtsformat. Kein echter Befund, keine Modellanfrage."],
  [/^Unit “(.+)” is a known variant spelling\.$/, "Die Einheit „$1“ ist eine bekannte Schreibvariante."],
  // Norm checks N1–N5 (api/app/pruefung/normen.py)
  [/^Outdated edition referenced: (.+)$/, "Veraltete Ausgabe zitiert: $1"],
  [/^Withdrawn standard referenced: (.+)$/, "Zurückgezogene Norm zitiert: $1"],
  [/^Withdrawn standard and its replacement both referenced: (.+)$/, "Zurückgezogene Norm und ihr Ersatz zugleich zitiert: $1"],
  [/^Bodenklassen without Homogenbereiche \(ATV DIN 18300\)$/, "Bodenklassen ohne Homogenbereiche (ATV DIN 18300)"],
  [/^Blanket standard reference without number in section (.+) \((\d+) items\)$/, "Pauschaler Normverweis ohne Nummer im Abschnitt $1 ($2 Positionen)"],
  [/The item refers to (.+?) edition (\S+); the current edition is (\S+)\. Which edition applies\? Please confirm\./, "Die Position verweist auf $1, Ausgabe $2; aktuell ist Ausgabe $3. Welche Ausgabe gilt? Bitte bestätigen."],
  [/The item refers to (.+?) edition (\S+); the norm register lists edition (\S+) as current\./, "Die Position verweist auf $1, Ausgabe $2; das Normregister führt Ausgabe $3 als aktuell."],
  [/The item refers to (.+?) \(withdrawn\)\. Does (.+?) apply instead\? Please confirm\./, "Die Position verweist auf $1 (zurückgezogen). Gilt stattdessen $2? Bitte bestätigen."],
  [/The item refers to (.+?); the norm register lists it as withdrawn\./, "Die Position verweist auf $1; das Normregister führt sie als zurückgezogen."],
  [/Register: (.+?) is replaced by (.+?)\./, "Register: $1 wird ersetzt durch $2."],
  [/The items refer to standards without a number \(e\.g\. "nach DIN"\)\. Which standards and editions apply\? Please name them\./, "Die Positionen verweisen auf Normen ohne Nummer (z. B. „nach DIN“). Welche Normen und Ausgaben gelten? Bitte benennen."],
  [/refer to standards in general terms \(e\.g\. "nach DIN"\) without naming a number or edition, so the agreed standard cannot be determined from the LV\./, "verweisen allgemein auf Normen (z. B. „nach DIN“) ohne Nummer oder Ausgabe; die vereinbarte Norm lässt sich dem LV nicht entnehmen."],
  [/The item describes the soil in Bodenklassen \(ATV DIN 18300\)\. Please provide the Homogenbereich description per current VOB\/C, or confirm which edition and classification apply\./, "Die Position beschreibt den Boden in Bodenklassen (ATV DIN 18300). Bitte Homogenbereiche nach aktueller VOB/C angeben oder bestätigen, welche Ausgabe und Einteilung gelten."],
  [/The LV refers to (.+?) \(withdrawn\) and elsewhere to (.+?)\. Which standard applies to these items\? Please confirm\./, "Das LV verweist auf $1 (zurückgezogen) und an anderer Stelle auf $2. Welche Norm gilt für diese Positionen? Bitte bestätigen."],
  [/Hint, not a standards expert opinion \(kein Normgutachten\); contractual validity is decided by a person \(VOB\/B § 1 \(2\)\)\./, "Hinweis, kein Normgutachten; über die vertragliche Geltung entscheidet ein Mensch (VOB/B § 1 (2))."],
  [/Source: norm register entry/, "Quelle: Normregister-Eintrag"], [/\(retrieved (\S+)\)/, "(abgerufen $1)"],
  [/Register note:/, "Registerhinweis:"],
  [/The item is explicitly optional \(bedarf\)/, "Die Position ist ausdrücklich als Bedarfsposition ausgeschrieben"],
  [/The item is explicitly alternative \(alternativ\)/, "Die Position ist ausdrücklich als Wahlposition ausgeschrieben"],
  [/The item is explicitly supplementary \(zulage\)/, "Die Position ist ausdrücklich als Zulage ausgeschrieben"],
  [/The item is explicitly lump-sum work \(pauschal\)/, "Die Position ist ausdrücklich pauschal ausgeschrieben"],
  [/The item is explicitly hourly work \(stundenlohn\)/, "Die Position ist ausdrücklich als Stundenlohn ausgeschrieben"],
  [/Scope or quantity needs clarification; this does not establish an entitlement to additional payment\./, "Umfang oder Menge sind zu klären; daraus folgt kein Anspruch auf Mehrvergütung."],
  [/Material\/work quantity context/, "Mengenkontext Material/Leistung"],
  [/identical descriptions, unit and work type (\w+); stated work quantities, not inferred material consumption/, "gleiche Beschreibung, Einheit und Positionsart $1; angegebene Leistungsmengen, kein abgeleiteter Materialverbrauch"],
  [/^(\S+ \S+) deviates (\S+) from the median (\S+ \S+) of the (.+?) layers in section (“[^”]+”)/, "$1 weicht $2 vom Median $3 der Schichten „$4“ im Abschnitt $5 ab"],
  [/Assumption: layers of the same component cover approximately the same area, tolerance ±10%; not a standard\./, "Annahme: Schichten desselben Bauteils haben etwa dieselbe Fläche, Toleranz ±10 %; keine Norm."],
];

function deutsch(text: string) {
  let s = text;
  for (const [re, ersatz] of DE) s = s.replace(re, ersatz);
  for (const [en, de] of Object.entries(BAUTEIL)) s = s.replace(new RegExp(`(Schichtfläche: |„)${en}(“|$)`, "g"), `$1${de}$2`);
  return s;
}

/** The finding as shown to the reader: technical tail removed, German when chosen. */
export function befundAnzeige(f: Finding, sprache: Sprache): Finding {
  const begruendung = f.begruendung.replace(SCHLUSS, "").trim();
  if (sprache !== "de") return { ...f, begruendung };
  return { ...f, titel: deutsch(f.titel), begruendung: deutsch(begruendung), vorschlag: deutsch(f.vorschlag) };
}
