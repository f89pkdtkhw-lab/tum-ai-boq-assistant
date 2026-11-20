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

## Entscheidungen des Teams

| Entscheidung | Antwort des Teams |
| --- | --- |
| Wer hat welches Problem? | Kalkulator/Angebotsbearbeiter in einem Bauunternehmen bekommt vom Bauherrn bzw. Architekten ein LV (oft GAEB) und hat wenige Tage bis zur Angebotsabgabe. Er kann nicht 3.000 Positionen lesen. |
| Woran erkennt der Partner eine gute Lösung? | Findet in Minuten echte Fehler und Risiken, die er sonst übersehen hätte, jeweils mit Positionsnummer und Begründung; weniger Fehlalarme als Treffer. |
| Erste echte Eingabe | Vorschlag: `data/datensatz/501-24-01_GAEB-XML_sas.x83` (GAEB DA XML 3.1, 296 Positionen); im Kickoff bestätigen |
| Erwartete, überprüfbare Ausgabe | Strukturierte Positionsliste + Prüfbericht: Findings mit OZ, Kategorie (Fehler / Risiko / Nachtrag), Schweregrad, Begründung, Quelle (Regel oder Modell), €-Wirkung wo schätzbar |
| Daten, Werkzeuge, Abgabevorgaben | Datensatz der Challenge; Claude-API (Anthropic-Key); Abgabeformat noch klären |
| Einfachster Vergleich und Messgröße | Testfälle mit **absichtlich eingebauten Fehlern** (`data/testfaelle/`): Trefferquote und Fehlalarme; dazu Zeit pro LV manuell vs. Tool |
| Was zeigen wir live in drei Minuten? | LV hochladen → Fortschritt → Dashboard: „17 Auffälligkeiten, 3 kritisch, ~42.000 € Risiko“ → Klick auf eine Position → Begründung + Vorschlag für Bieterfrage/Nachtrag |
| Wer hebt bei einem Blocker die Hand? | Jeder sofort auf dem Board mit `@f89pkdtkhw-lab` |

## Was im Datensatz steckt

44 Dateien, 25 MB, in `data/datensatz/` (Stand Fr. 20.11., anonymisiert mit Platzhaltern wie `[FIRMA_096]`):

| Format | Dateien | Hinweis |
| --- | --- | --- |
| GAEB DA XML (`.X83`/`.x83`) | 4: `501-24-01_GAEB-XML_sas.x83` (296 Pos.), `[NUMMER_001]_leer.X83` (248), `8209.003_Leistungsverzeichnis_leer.X83` (159), `GAEB-[PROJEKT_004].X83` (50) | Namespace `http://www.gaeb.de/GAEB_DA_XML/200407`, Langtexte als HTML-artiges Markup |
| GAEB 90 Flat-File (`.D83`/`.D84`/`.D86`) | 5, u. a. `Angebot AN24-0305.D84` **mit Preisen** und das passende `Angebot AN24-0305.pdf` | feste 80-Zeichen-Zeilen, Satzarten `00`–`99`, Codepage CP850 |
| PDF | 33, u. a. `LV_00` bis `LV_23` nach Gewerk, `HEM2301-2_Gesamt-LV.pdf` | Text-PDFs aus AVA-Programmen; prüfen, ob gescannte dabei sind |
| Word | `LV-Positionen.docx` | |

Paare aus GAEB-Datei und PDF desselben LVs (z. B. `GAEB-[PROJEKT_004].X83` + `LV-Ausdruck-[PROJEKT_004].pdf`) eignen sich, um den PDF-Import gegen den GAEB-Import zu testen. Die `.D84`/`.D86`-Dateien mit Preisen sind die Basis für EP-Vorschläge aus „historischen“ Daten.

## Kernablauf (Vorschlag, im Kickoff bestätigen)

```text
Upload (GAEB .x83/.x84/.d83, .xlsx, .pdf)
  → Import: einheitliches Modell  LV → Lose/Titel → Positionen (OZ, Kurztext, Langtext, Menge, Einheit, EP, GP, Typ)
  → Prüf-Engine
       feste Regeln:  Menge × EP ≠ GP, Summen je Titel, doppelte/lückenhafte OZ, fehlende Einheit/Menge,
                      Einheit passt nicht zum Text (m² vs. m³), Ausreißer-Mengen, Tippfehler
       LLM (Claude):  vage/unklare Langtexte, Widersprüche zwischen Positionen, fehlende Positionen je Gewerk,
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
