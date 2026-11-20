---
name: kickoff
description: Startet die Produktarbeit für Challenge A (LV-Prüfassistent) in rund 30 Minuten - Datensatz sichten, Case-Brief schärfen, Datenmodell und Schnittstelle mit Beispieldaten auf main, Besitzer-Tabelle, parallele Issues mit agent-bereit und Board-Post, sodass alle fünf Personen sofort loslegen. Nutzen, sobald jemand "Kickoff" schreibt, optional mit zusätzlichem Kontext.
---

<!-- Generiert aus .agents/skills/kickoff/SKILL.md mit python tools/agents_sync.py. Hier nicht bearbeiten. -->

Du bist die Integrations-Crew von @f89pkdtkhw-lab. Der Aufruf ist der Startauftrag: Führe den Kickoff bis zu den startbereiten Issues ohne weitere Freigabe aus. Ziel: Nach rund 30 Minuten arbeiten fünf Personen auf fünf Laptops parallel an Issues, die nicht kollidieren. Starte eine Uhr und nenne bei jedem Schritt die verstrichene Zeit. Schlüssel nie ausgeben oder committen.

**Abgabe Sonntag, 22.11.2026, 12:00 (München)**, internes Ziel 11:30, Funktionsstopp 09:00.

## 1. Case und Daten erfassen (5 Minuten)

Lies `docs/case.md`, `docs/domaene.md` und zusätzlichen Kontext aus dem Aufruf. Sichte `data/datensatz/`: welche Dateiformate (GAEB `.x83/.x84/.d83/.p83`, `.xlsx`, `.pdf`), wie viele Positionen, gibt es Preise. Wähle **ein** mittelgroßes LV als „erste echte Eingabe“ und trage es im Case-Brief ein. Fehlt der Datensatz, bitte den Lead auf dem Board, ihn nach `data/datensatz/` zu legen, und arbeite mit einer kleinen selbst gebauten Nachbildung in `data/beispiel_lv.json` weiter.

## 2. Demo-Szene festlegen (5 Minuten)

Ein Kernablauf, den die Jury in drei Minuten live sieht: LV hochladen → strukturierte Positionen → Prüfbericht mit Findings (Fehler / Risiko / Nachtrag), Schweregrad, €-Wirkung, Klick auf eine Position zeigt Begründung und Vorschlag für eine Bieterfrage. Der überzeugende Moment: ein echter Fehler im echten LV, den ein Mensch übersehen hätte. Alles andere (EP-Vorschläge, What-if, OCR) ist später.

## 3. Plan ohne Lücken (höchstens 10 Minuten)

Schärfe `docs/case.md`. Nutze `grilling` mit der Kickoff-Ausnahme: höchstens zwei Fragerunden auf dem Board, keine zusätzliche Planfreigabe. Jede Runde folgt diesem Format (Ja übernimmt die Empfehlung):

```text
[Raban · Claude] @f89pkdtkhw-lab Kickoff · Runde 1
Q1: <Entscheidung als Ja/Nein-Frage>
Empfehlung: <konkrete Wahl und kurzer Grund>
Ohne Antwort bis <HH:MM mit Zeitzone>: **Annahme** <Empfehlung>.
```

Die Frist liegt zehn Minuten nach Beginn von Schritt 3. Übernimm bei Fristablauf die unbeantworteten Empfehlungen, markiere sie im Case-Brief als **Annahme** und poste sie auf dem Board.

## 4. Schnittstelle zuerst (10 Minuten, Branch `kickoff-schnittstelle`)

Lege fest, worauf alle bauen:

- `api/app/modelle.py`: Pydantic-Modelle `Position` (oz, kurztext, langtext, menge, einheit, ep, gp, typ, titel_pfad), `LV` (name, quelle, positionen, summen), `Finding` (id, oz, kategorie `fehler|risiko|nachtrag`, schwere `kritisch|hoch|mittel|niedrig`, titel, begruendung, vorschlag, quelle `regel|modell`, regel_id, euro_wirkung optional), `Pruefbericht` (lv, findings, kennzahlen)
- `api/app/main.py`: `POST /api/lv/import` (Datei-Upload → `LV`), `POST /api/lv/pruefen` (`LV` → `Pruefbericht`), `GET /api/beispiele` (Beispiel-LVs aus `data/`), `GET /health`
- je ein Platzhalter-Modul pro Logik-Issue mit festem Vertrag und Beispieldaten: `api/app/lv/importer.py` (`importiere(dateiname, bytes) -> LV`), `api/app/pruefung/regeln.py` (`pruefe_regeln(lv) -> list[Finding]`), `api/app/pruefung/llm_pruefung.py` (`pruefe_mit_llm(lv) -> list[Finding]`, Mock ohne Schlüssel), `api/app/risiko/scoring.py` (`bewerte(lv, findings) -> list[Finding]`), optional `api/app/kalkulation/preise.py`; `main.py` ruft sie bereits auf
- `web/lib/api.ts`: dieselben Typen und Aufrufe
- `data/beispiel_lv.json`: realistisches kleines LV (ca. 30 Positionen, 3 Titel) mit 5 eingebauten Fehlern; erwartete Findings in `data/beispiel_erwartung.json`
- je eine Testdatei pro Modul, z. B. `api/tests/test_import_gaeb.py`, `api/tests/test_pruefung_regeln.py`, `api/tests/test_risiko_scoring.py`, `api/tests/test_schnittstelle.py`

Für diesen einmaligen PR darf die Integrations-Crew Dateien in fremden Bereichen anlegen; kündige sie vorher mit `@all` an. `cd api && python -m pytest -q`, `cd web && npm run build` und `python -m unittest discover -s tests -v` müssen grün sein. PR öffnen, bei grünen Checks mergen, mit `@all` aufs Board. Erst danach starten die Folge-Issues.

## 5. Besitzer und Issues (5 Minuten)

Bestätige die Tabelle in `AGENTS.md` Abschnitt 3. Schneide mit `auftrag-schneiden` acht bis zwölf Issues: senkrechte Scheiben, jede mit einem Hauptverantwortlichen, Abnahmetest, Zielbranch `main`, genau einem Modell-Label und Zuweisung. Plane mindestens:

- @Anatomik5: GAEB-XML-Import (X83/X84) für das gewählte echte LV; danach Excel-Import; danach PDF-Import (Text + Tabellen, OCR nur wenn nötig)
- @Bartuan3600: feste Prüfregeln (Rechnung, Summen, OZ, Einheit, Menge, Platzhaltertexte); danach LLM-Prüfung für vage Texte und Widersprüche in Batches mit strukturiertem JSON-Output
- @Secret-Sebi: Risiko-/Nachtragsscoring mit Signalwortkatalog und Positionstypen (Bedarf, Pauschale, Stundenlohn); Testfälle mit eingebauten Fehlern in `data/testfaelle/`; Pitch aus Kalkulatorsicht in `pitch/`
- @Zukipany: Upload-Seite mit Fortschritt; Prüfbericht-Dashboard (Kennzahlen, Findings-Liste mit Filter, Positionsdetail); Export als PDF/Excel
- @f89pkdtkhw-lab: LLM-Zugriff und Kostenbremse (Batching, Caching), Deploy und Demo-Skript in `docs/demo.md`, Vergleich manuell vs. Tool in `data/vergleich.md`

Jeder Verweis auf eine erst entstehende Datei nennt das liefernde Issue als Blocker. Nur Issues ohne offene Blocker erhalten sofort `agent-bereit`.

## 6. Startschuss

Poste auf dem Board mit `@all`: den Kernablauf in einem Satz, die Issue-Nummern pro Person, offene Blocker und: „Arbeitet alle euch zugewiesenen agent-bereit-Issues ab; gebt Folge-Issues nach dem Merge ihrer Blocker frei.“ Berichte dem Lead die verstrichene Zeit und die getroffenen Annahmen.
