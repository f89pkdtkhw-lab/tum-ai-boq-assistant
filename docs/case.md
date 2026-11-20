# Case-Brief · Challenge A: KI-Prüf- und Kalkulationsassistent für Leistungsverzeichnisse

TUM.ai Construction Hackathon, 20.–22. November 2026. **Abgabe Sonntag 12:00**, internes Ziel 11:30. Fachwissen und Teamnotizen: [Domäne](domaene.md).

## Die Challenge im Wortlaut (übersetzt)

**Problem.** Leistungsverzeichnisse (LV, engl. Bills of Quantities, BoQ) haben oft mehrere tausend Positionen über viele Kostengruppen, und Positionen hängen gewerkeübergreifend voneinander ab. Firmen fehlt Zeit und Personal, LVs im Detail zu prüfen, Risiken zu erkennen und systematisch aus früheren Projekten zu lernen. Typische Fehler sind Tippfehler, falsche Berechnungen und übersehenes Nachtragspotenzial; jeder kann große finanzielle Folgen haben.

**Ziel.** Ein Prototyp, der LVs analysiert und strukturiert:

1. Lange LVs automatisch importieren und parsen (PDF, GAEB, Excel)
2. **Fehlererkennung hat erste Priorität:** formale und inhaltliche Lücken wie fehlende Positionen, unklare Beschreibungen, Widersprüche, Tippfehler
3. Risikobewertung: typische Hochrisiko-Positionen markieren, z. B. vage Leistungsbeschreibung oder ungewöhnliche Mengen
4. Nachtragspotenzial und wahrscheinliche Streitpunkte während der Bauausführung erkennen
5. Optional: Einheitspreise oder Zuschläge aus historischen Projektdaten vorschlagen

**Datensatz:** [Beispiel-LVs auf Google Drive](https://drive.google.com/drive/folders/1wS4UMVghBL8T5opmZ2UBmBu0kr6U8zIB), lokal in `data/datensatz/`.

**Vorgesehene Meilensteine** (laut Challenge-Unterlagen): 1. LV-Parsing und strukturierte Datenextraktion · 2. Fehlerdetektion und Plausibilitätsprüfung · 3. Risikoscoring und Nachtragserkennung · 4. Integration historischer Projektdaten (optional) · 5. What-if-Analysen, z. B. Materialpreise oder Ausführungsalternativen.

**Erwartetes Ergebnis:** Web-App oder Assistenz-Tool mit Upload-Funktion · verständlicher Risiko- und Prüfbericht · Pitch aus Sicht eines Kalkulators.

## Was die Partner beim Pitch-Abend gesagt haben

Quelle: [Transkript](quellen/Challenge_A_Beyond_the_Line_Item_Transcription.pdf) (European Hackathon League, Fr. 20.11.).

- **Dominik, CFO einer Luxemburger Baufirma (Infrastruktur).** Bieter haben wenig Zeit; Preise kommen aus Nachunternehmer-Anfragen und eigener Erfahrung, zusammengeführt in der Kalkulationssoftware. Vergeben wird meist nach Preis: **zu hoch heißt, der Auftrag ist weg, zu niedrig (weil man etwas übersehen hat) heißt Verlust.** Reihenfolge: **erst Fehlererkennung**, dann Risiko, dann optional Preise und What-if.
- **Daten:** **9 anonymisierte LVs** (kleine Brückensanierung bis Großprojekt), für **2 davon echte Ausführungsdaten** (Ist-Stunden, Abrechnungsmengen, Nachtragsliste). **Vertraulich: nicht in öffentliche Repos.**
- **Christian, Kalkulator seit 10 Jahren („Excel ist mein bester Freund“):**
  - **Mengenverhältnisse:** 400 Stühle, aber nur 50 Tische → da stimmt was nicht.
  - **Aggregation:** „2 blaue, 2 rote, 88 grüne Tische“ zusammenfassen; „Beton ist Beton“: Gesamtmenge über alle Betonsorten, statt sie bei 9.000 Positionen von Hand zu summieren.
  - **Duplikate** erkennen.
  - **Knifflige Positionen:** wenig Detail, Spezialgewerk (Beispiel Audioanlage: 50.000 € oder 200.000 €?), oft klein irgendwo versteckt.
  - **„Die eigentliche Aufgabe ist nicht, 9.000 Positionen zu verarbeiten, sondern die 100 wichtigsten zu finden.“**
- **Gewünschte Demo:** ein LV hochladen und den Risiko-/Fehlerbericht zurückbekommen. **Pitch aus Sicht eines Kalkulators:** Wie verändert das Tool die Angebotsbearbeitung?

## Was daraus für das Produkt folgt (Priorität)

1. **Fehler** mit OZ und Begründung: Rechnung, fehlende Menge/Einheit, Kurztext ≠ Langtext, Tippfehler, Einheiten- und Maßfehler, veraltete Normen.
2. **Plausibilität über Positionen hinweg:** Mengenverhältnisse verwandter Positionen (Abdichtung ↔ Dämmung ↔ Folie, Schalung ↔ Beton, Beton ↔ Bewehrung kg/m³), Duplikate.
3. **Aggregation:** Summen nach Stoff/Gewerk (Beton m³, Stahl kg, Mauerwerk m²) als Kennzahlen-Kacheln.
4. **Top 100 statt 9.000:** Ranking nach €-Wirkung × Unsicherheit; knifflige Positionen (vage, Spezialgewerk, pauschal, Bedarf, Stundenlohn) nach oben.
5. **Nachtrags- und Streitpotenzial** und daraus formulierte **Bieterfragen**.
6. Optional: EP-Vorschläge aus den 2 Projekten mit Ist-Daten, What-if auf Materialpreise.

Dazu gilt aus der [Skill-Liste](quellen/Skills%20der%20KI.pdf): Die KI kennzeichnet jede Schätzung als Schätzung und gibt nie einen Preis ohne Freigabe des Kalkulators heraus.

## Testfälle

- `data/testfaelle/rohbau_efh/`: Muster-LV Rohbau Einfamilienhaus (PDF, 40 Seiten) mit **25 manuell gefundenen echten Befunden** in [erwartung.md](../data/testfaelle/rohbau_efh/erwartung.md). Ideal als Demo-LV und als Messlatte (Trefferquote, Fehlalarme).

## Entscheidungen des Teams

| Entscheidung | Antwort des Teams |
| --- | --- |
| Wer hat welches Problem? | Kalkulator/Angebotsbearbeiter in einem Bauunternehmen bekommt vom Bauherrn bzw. Architekten ein LV (oft GAEB) und hat wenige Tage bis zur Angebotsabgabe. Er kann nicht 3.000 Positionen lesen. |
| Woran erkennt der Partner eine gute Lösung? | Findet in Minuten echte Fehler und Risiken, die er sonst übersehen hätte, jeweils mit Positionsnummer und Begründung; weniger Fehlalarme als Treffer. |
| Erste echte Eingabe | Demo: `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf` (bekannte 25 Befunde). Format-Breite: `data/datensatz/501-24-01_GAEB-XML_sas.x83` (GAEB DA XML 3.1, 296 Positionen); im Kickoff bestätigen |
| Erwartete, überprüfbare Ausgabe | Strukturierte Positionsliste + Prüfbericht: Findings mit OZ, Kategorie (Fehler / Risiko / Nachtrag), Schweregrad, Begründung, Quelle (Regel oder Modell), €-Wirkung wo schätzbar |
| Daten, Werkzeuge, Abgabevorgaben | Datensatz vertraulich; LLM ausschließlich Offline-Mock ohne Schlüssel; Abgabeformat noch klären |
| Einfachster Vergleich und Messgröße | Testfälle mit **absichtlich eingebauten Fehlern** (`data/testfaelle/`): Trefferquote und Fehlalarme; dazu Zeit pro LV manuell vs. Tool |
| Was zeigen wir live in drei Minuten? | LV hochladen → Positionen → Prüfbericht mit echten Befunden, OZ und Begründung; keine erfundenen Anzahlen oder Euro-Werte. Klick zeigt Position und Bieterfrage. |
| Wer hebt bei einem Blocker die Hand? | Jeder sofort auf dem Board mit `@f89pkdtkhw-lab` |

## Was im Datensatz steckt

44 Dateien, ca. 25 MB, in `data/datensatz/` (Stand Fr. 20.11., anonymisiert mit Platzhaltern wie `[FIRMA_096]`):

| Format | Dateien | Hinweis |
| --- | --- | --- |
| GAEB DA XML (`.X83`/`.x83`) | 4: `501-24-01_GAEB-XML_sas.x83` (296 Pos.), `[NUMMER_001]_leer.X83` (248), `8209.003_Leistungsverzeichnis_leer.X83` (159), `GAEB-[PROJEKT_004].X83` (50) | Namespaces DA XML 3.1 (`200407`) und 3.2 (`DA83/3.2`), Langtexte als HTML-artiges Markup |
| GAEB 90 Flat-File (`.D83`/`.D84`/`.D86`) | 5, u. a. `Angebot AN24-0305.D84` **mit Preisen** und das passende `Angebot AN24-0305.pdf` | feste 80-Zeichen-Zeilen, Satzarten `00`–`99`, Codepage CP850 |
| PDF | 34, u. a. `LV_00` bis `LV_23` nach Gewerk, `HEM2301-2_Gesamt-LV.pdf` | Text-PDFs aus AVA-Programmen; prüfen, ob gescannte dabei sind |
| Word | `LV-Positionen.docx` | |

Paare aus GAEB-Datei und PDF desselben LVs (z. B. `GAEB-[PROJEKT_004].X83` + `LV-Ausdruck-[PROJEKT_004].pdf`) eignen sich, um den PDF-Import gegen den GAEB-Import zu testen. Die `.D84`/`.D86`-Dateien mit Preisen sind die Basis für EP-Vorschläge aus „historischen“ Daten.

## Kernablauf (Kickoff, 20.11.2026)

```text
Upload (GAEB .x83/.x84/.d83, .xlsx, .pdf)
  → Import: einheitliches Modell  LV → Lose/Titel → Positionen (OZ, Kurztext, Langtext, Menge, Einheit, EP, GP, Typ)
  → Prüf-Engine
       feste Regeln:  Menge × EP ≠ GP, Summen je Titel, doppelte/lückenhafte OZ, fehlende Einheit/Menge,
                      Einheit passt nicht zum Text (m² vs. m³), Ausreißer-Mengen, Tippfehler
       LLM (zunächst ausschließlich Mock):  vage/unklare Langtexte, Widersprüche zwischen Positionen, fehlende Positionen je Gewerk,
                      Bedarfs-/Eventualpositionen, „bauseits“, Pauschalen, Verweise auf nicht beigefügte Pläne
  → Risiko- und Nachtragsscoring je Position (Score 0–100, €-Wirkung)
  → Bericht: Web-Dashboard + Export (PDF/Excel) + Liste von Bieterfragen
  → optional: EP-Vorschlag aus Kalkulationsansatz (Lohn, Material, Gerät, Zuschläge) + What-if
```

## Rollen und erstes Ergebnis

| Person | Schwerpunkt | Erstes Ergebnis |
| --- | --- | --- |
| @f89pkdtkhw-lab | Integration, KI-Zugriff, Deploy, Demo | Schnittstelle + Datenmodell auf `main`, Demo startet auf dem Präsentationslaptop |
| @Anatomik5 | Import und Parsing | Ein echtes GAEB-LV aus dem Datensatz vollständig als JSON-Positionsliste |
| @Bartuan3600 | Prüf-Engine | Fünf feste Prüfregeln mit Tests, die auf dem Beispiel-LV echte Findings liefern |
| @Zukipany | Oberfläche | Upload, Positionstabelle, Findings-Liste mit Filter und Detailansicht |
| @Secret-Sebi | Risiko, Nachträge, Kalkulation, Pitch | Risiko-Katalog (Signalwörter, Positionstypen) + Testfälle mit eingebauten Fehlern + Pitch-Story aus Kalkulatorsicht |

## Offene Fragen

- Wie und wo wird abgegeben (Repo-Link, Video, Formular)? Pitch-Länge und Bewertungskriterien?
- Welche Formate enthält der Datensatz genau (GAEB-Version, Excel-Layout, gescannte PDFs)?
- Gibt es historische Preise im Datensatz für die optionale EP-Schätzung?
- Gestellte API-Zugänge und deren Limit?


## Verbindlicher Kickoff-Schnitt (20.11.2026)

Priorität: **1. Parsing/Import (GAEB X83/X84 → Excel → PDF), 2. feste Fehlerprüfung, 3. verständlicher Prüfbericht.** Risiko, Nachträge, Preise, What-if und Pitch folgen dem Kernablauf. Die Fachmodule stehen als Platzhalter bereit; ein erfolgreicher Schnittstellenaufruf ist noch keine fachliche Prüfung.

- Echtes GAEB für den ersten Import: `data/datensatz/501-24-01_GAEB-XML_sas.x83`, DA XML 3.1, **296 Positionen**, keine Preisfelder. Drei weitere X83 mit DA XML 3.2: 248, 159 und 50 Positionen. Kein X84 und kein Excel im Partnerbestand; X84 und Excel deshalb zusätzlich mit synthetischen Fixtures testen. GAEB 90 D83/D84/D86 später, keine vorgetäuschte Unterstützung.
- Ziel-Demo und Messlatte: `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`, 40 Seiten, 25 manuell dokumentierte echte Befunde in `erwartung.md`. Live nutzbar erst nach dem PDF-Import. Bis dahin echter GAEB-Import als erster Meilenstein und das synthetische JSON als Offline-Vertragsdemo.
- **Annahme (Board-Runde 1, Frist 19:36 CET):** `data/beispiel_lv.json` (30 Positionen, 3 Titel, 5 absichtliche Fehler) trägt die sofort startbare Schnittstelle; `data/beispiel_erwartung.json` ist die Abnahme für das Folge-Issue feste Regeln. Die Platzhalter melden diese fünf Fehler noch nicht.
- Bereits durch den Startauftrag entschieden: LLM bleibt Mock (`pruefe_mit_llm` ohne Schlüssel, Netzwerk oder Anbieter). Standard-Worker Codex, Claude nur für `modell:ui` und `modell:schwer`. Live-Freischaltung gehört in einen späteren ausdrücklich autorisierten Auftrag.
- Unbekannte Mengen/Preise bleiben `null`, leere Summen `{}`. Ein unbepreistes X83 ergibt keinen belastbaren Euro-Risikobetrag. Modell-Mocks zählen nicht als echte Treffer. Quellen und Original-OZ bleiben erhalten, auch doppelte OZ werden nicht beim Import entfernt.
- Drei-Minuten-Szene: Datei auswählen → Positionszahl und Importfehler sehen → feste Befunde nach Schwere filtern → eine Position mit Originaltext, Begründung und Handlungsvorschlag öffnen. Tatsächliche Messergebnisse erst nach dem Demo-/Vergleichs-Issue veröffentlichen.

Die Besitzer-Tabelle aus AGENTS.md §3 ist für diesen Schnitt bestätigt: @Anatomik5 `api/app/lv/`, @Bartuan3600 `api/app/pruefung/`, @Secret-Sebi `api/app/risiko/` und `pitch/`, @Zukipany `web/`, @f89pkdtkhw-lab Integration, KI-Zugriff, Daten und Dokumentation. Der einmalige Schnittstellen-PR legt `api/app/modelle.py`, `main.py`, `web/lib/api.ts` gemeinsam fest. Folge-Issues ändern getrennte Fachmodule und Testdateien; Vertragsänderungen vorher mit @all ankündigen.

Zeitplan: funktionierender Kernablauf vor optionalem Risiko/Pitch; Funktionsstopp Sonntag 22.11. **09:00 Europe/Berlin**, interne Abnahme 11:30, Abgabe 12:00. Offenes Abgabeformat bleibt eine Frage an den Lead und blockiert keine lokale Produktarbeit.
