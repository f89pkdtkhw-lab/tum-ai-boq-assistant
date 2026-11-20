# LV-Schnittstelle v0.2

Verbindliche Implementierung: `api/app/modelle.py`; TypeScript-Spiegel: `web/lib/api.ts`. Besitzer-Tabelle bestätigt in `docs/case.md`. Änderungen an Routen oder Feldern vorab mit @all auf Board #1 ankündigen.

## HTTP

| Route | Eingabe | Erfolg | Fehler |
| --- | --- | --- | --- |
| `GET /health` | keine | `{ok:true, provider:"mock", model:"offline-lv-mock", mock:true, keys:{…false}}` | — |
| `GET /api/beispiele` | keine | `{items:[{id,titel,beschreibung,lv}]}` | — |
| `POST /api/lv/import` | multipart/form-data, Feld `datei`, max. 10 MiB | `LV` | 413 zu groß; 422 leer/ungültig/Format unbekannt; 501 bekannter Import noch Platzhalter |
| `POST /api/lv/pruefen` | `LV` als application/json | `Pruefbericht` | 422 falscher Vertrag |

Im Kickoff nur JSON-Import. X83/X84, XLSX und PDF sind explizite Platzhalter; jedes zugewiesene Format-Issue ersetzt ausschließlich sein Modul. Dateien werden nicht dauerhaft gespeichert. Fehlerantworten enthalten `detail` als verständlichen Text; FastAPI-Validierungsfehler verwenden die übliche Liste, die der Client als allgemeine Eingabemeldung anzeigt.

`GET /api/beispiele` liefert vollständige, typisierte synthetische LVs, keine Partnerdateien. `POST /api/ask` bleibt für die Starterseite kompatibel und antwortet erzwungen als Mock; die LV-Pipeline verwendet keinen Modellanbieter. `/health` meldet den tatsächlichen Offline-Modus der Produktpipeline, keine Schlüsselbestände.

## Daten und Bedeutung

`Position`: `oz`, `kurztext`, `langtext`, `menge`, `einheit`, `ep`, `gp`, `typ`, `titel_pfad`. `oz` ist ein nicht leerer Originalwert; weder neu nummerieren noch doppelte OZ entfernen. Mengen und Preise sind JSON-Zahlen oder `null`; `null` ist unbekannt, `0` ist eine bekannte Null. Negative Werte für Prüfregeln erhalten. Nicht endliche Zahlen werden abgelehnt. `titel_pfad` enthält geordnete Titelbezeichnungen; keine implizite Normalisierung von Einheiten. `typ`: `normal|bedarf|alternativ|zulage|pauschal|stundenlohn`; unbekannte Semantik nicht erfinden.

`LV`: `name`, `quelle`, `positionen`, `summen`. `quelle` beschreibt die Herkunft (Dateiname/Format), keine Datei-URL. `summen` enthält ausschließlich angegebene Titelsummen, Schlüssel Titelpfad verbunden mit ` / `. Beispiel: `{"01 Erdarbeiten": 1234.5}`. `{}` bedeutet keine vorliegenden Summen. Keine erfundenen oder aus fehlenden Preisen berechneten Summen.

`Finding`: `id`, `oz`, `kategorie` (`fehler|risiko|nachtrag`), `schwere` (`kritisch|hoch|mittel|niedrig`), `titel`, `begruendung`, `vorschlag`, `quelle` (`regel|modell`), `regel_id`, `euro_wirkung` (Zahl oder `null`). ID innerhalb des Berichts eindeutig und für gleiche Eingaben stabil; OZ muss aus dem LV stammen. Bei mehreren betroffenen Positionen pro OZ einen Befund erzeugen und Bezug im Text nennen. Befunde auf LV-/Titelebene an eine tatsächlich betroffene OZ hängen und den Geltungsbereich erklären. Keine erfundenen Normen oder Preise. Euro-Wirkung nur mit belegbarer Grundlage; Schätzungen im Text kennzeichnen.

`Pruefbericht`: `lv` unverändertes Eingabemodell, `findings`, `kennzahlen` mit `positionen`, `findings`, `kritisch`, `modell_mock`. `findings` zählt sämtliche angezeigten Einträge einschließlich des klar markierten Demonstrations-Mocks, keine behaupteten echten Fehler. Die Evaluation schließt `regel_id == "MOCK_LLM"` aus.

Beispiel-Eingabe: `data/beispiel_lv.json` (30 Positionen). POST `/api/lv/pruefen` liefert derzeit dieselben 30 Positionen und einen Eintrag `MOCK_LLM` an OZ `01.00.0001`, keine fachlich bestätigten Findings, `euro_wirkung:null`, `kennzahlen:{positionen:30,findings:1,kritisch:0,modell_mock:true}`. Fünf erwartete echte Regelbefunde für den Folgeauftrag: `data/beispiel_erwartung.json`.

## Verdrahtete Fachgrenzen

| Modul | Vertrag | Kickoff-Verhalten |
| --- | --- | --- |
| `lv/importer.py` | `importiere(dateiname, inhalt: bytes) -> LV` | JSON validieren, Formatdispatch |
| `lv/gaeb.py`, `lv/excel.py`, `lv/pdf.py` | jeweils `importiere(dateiname, inhalt: bytes) -> LV` | `NotImplementedError` → HTTP 501 |
| `pruefung/regeln.py` | `pruefe_regeln(lv) -> list[Finding]` | leere Liste |
| `pruefung/mengen.py` | `pruefe_mengen(lv) -> list[Finding]` | leere Liste |
| `pruefung/llm_pruefung.py` | `pruefe_mit_llm(lv) -> list[Finding]` | markierter Offline-Mock an erster echter OZ; leeres LV → [] |
| `risiko/scoring.py` | `bewerte(lv, findings) -> list[Finding]` | bestehende Findings erhalten |

`main.py` ruft alle Grenzen bereits auf. Jeder Logikauftrag besitzt eine eigene Testdatei. Importfehler sollen durch `ValueError` mit sicherer Nachricht gemeldet werden; Parser dürfen keinen vertraulichen Dateiinhalt in Fehlertexten ausgeben. Der feste Regelsatz nutzt `RECHENFEHLER`, `EINHEIT_FEHLT`, `MENGE_FEHLT`, `LANGTEXT_FEHLT`, `OZ_DUPLIKAT` für die fünf synthetischen Abnahmekriterien; zusätzliche Regeln brauchen eigene stabile IDs.
