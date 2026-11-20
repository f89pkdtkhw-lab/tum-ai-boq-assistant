# Testfall: LV Rohbauarbeiten Einfamilienhaus (Goldstandard)

Quelle: `lv_rohbau_efh.pdf`, ein Muster-LV eines Ingenieurbüros (29.05.2020), 40 Seiten, 9 Titel, ~95 Positionen, ohne Preise. Kein Teil des Partner-Datensatzes.

Diese Liste stammt aus einer manuellen Durchsicht vom 20.11. Jede Zeile ist ein **echter Befund im Original**, also nichts nachträglich Eingebautes. Damit messen wir Trefferquote (wie viele davon das Tool findet) und Fehlalarme. Kategorie: F = Fehler, R = Risiko, N = Nachtragspotenzial, P = Plausibilität. Spalte „Regel?“ = mit fester Regel ohne LLM auffindbar.

| # | OZ | Kat. | Befund | Regel? |
|---|---|---|---|---|
| 1 | 8...3 | F | Menge `7,000` **ohne Einheit** (Wiederverfüllung Arbeitsräume) | ja |
| 2 | 9...1 | F | Prüfprotokoll Erdung: **keine Menge, keine Einheit, kein Langtext** | ja |
| 3 | 9...3 | F | Druckprüfung Leitungen: keine Menge/Einheit; „EN 1601“ statt DIN EN 1610 (vgl. Titel 2); „35mim“ | ja / LLM |
| 4 | 6...39 | F | **Kurztext „BETA 3/400-B“ ≠ Langtext „BETA 2/400-B“** (Zuganker) | ja (Kurz/Lang-Abgleich) |
| 5 | 6...40 | F | Kurztext „Betonmattenstahl BSt 500 **M** (A)“ ≠ Langtext „BSt 500 **S** (A) als Lagermatten“ | ja |
| 6 | 5...15, 5...16 | F | „Wanddicke **0,115cm**“: Einheitenfehler, gemeint 11,5 cm | ja (Plausibilität Maß) |
| 7 | 6...21 | F | Expositionsklassen „XC2/XF1**//**WF“: Tippfehler | ja |
| 8 | 4...3 | F | Fabrikat „Sto-Sockelplatte … oder gleichwertig. **Brillux**“: widersprüchliche Herstellerangabe | LLM |
| 9 | 4...1–4...4 | F | XPS-Perimeterdämmung „nach DIN EN **13162**“ (= Mineralwolle-Norm); für XPS gilt DIN EN 13164 | LLM |
| 10 | 4...4 | P | WLG 035, alle anderen Perimeterdämmungen WLG 032: Abweichung prüfen | ja |
| 11 | 3...1 / 3...2 / 4...4 / 4...5 | P | Flächen Bodenplatte inkonsistent: Voranstrich 205 m², Schweißbahn 150 m², Dämmung 120 m², PE-Folie 130 m² (vgl. „400 Stühle, 50 Tische“) | ja (Mengenverhältnis) |
| 12 | 4...2 | P | Perimeterdämmung Garage **1,000 m²**: auffällig kleine Menge, vermutlich Platzhalter | ja |
| 13 | 6...1 / 6...2 | P | Fundamenterder 52 m **und** Ringerder V4A 55 m: doppelte Erdung? (Ringerder ersetzt i. d. R. Fundamenterder bei Perimeterdämmung) | LLM |
| 14 | 3...2, 3...4, 3...5 | R | **DIN 18195-4 zurückgezogen** (seit 2017 DIN 18533); veraltete Norm im LV von 2020 | LLM/Katalog |
| 15 | Vorbem. S. 1 | F | „Ausführungsbeginn: **März 2020**“, LV datiert **29.05.2020**: Termin liegt vor der Ausschreibung | LLM |
| 16 | 5...3, 6...22 | R | Bedarfspositionen (Sichtmauerwerk 40 m², Sichtbeton 10 m²) mit *NEP*: nicht in der Summe, Spekulations- und Streitpunkt | ja (Positionstyp) |
| 17 | Titel 7 | R | Stundenlohnarbeiten: 60 Lohnstunden + 40 Gerätestunden ohne Bezug: offenes Budget | ja (Positionstyp) |
| 18 | 1...1 | R | Baustelleneinrichtung **pauschal** inkl. Turmdrehkran „Anzahl und Größe entsprechend der Baustellengröße“: unbestimmt | LLM |
| 19 | 6...14 | N | „Genaue Abmessungen nach Vergabe Tiefbauarbeiten, ca. Ø 78 cm“: Leistung zum Angebotszeitpunkt unbestimmt | LLM |
| 20 | 6...43 | R | Sichtbetonfertigteil „ca. 3,55 × 1,175 × 0,25 m“, Einbau nach Fenstermontage: Maße ungefähr, Schnittstelle zu anderem Gewerk | LLM |
| 21 | Vorbem. S. 2 | R | AG darf Leistungen entfallen lassen „ohne Änderung sämtlicher Einheitspreise“: Abweichung von VOB/B § 2 Abs. 3 / § 8 | LLM |
| 22 | Vorbem. S. 3 | R | Festpreise ohne Preisgleitung über die gesamte Ausführungszeit | LLM |
| 23 | Vorbem. S. 3 | R | „Hilfsmittel und Hilfskonstruktionen … werden nicht vergütet“; Bieter muss Vollständigkeit des LV selbst prüfen (S. 40): Risikoverlagerung | LLM |
| 24 | Titel 8 | N | Erdarbeiten nur Frostschürze/Einzelfundamente: **kein Aushub/Abtrag für die Bodenplatte, kein Oberboden, keine Entsorgung**: fehlende Positionen | LLM |
| 25 | div. | F | Tippfehler: „erfoderlichen“ (1...1), „Reingen“, „Bitumvoranstrich“ (3...1), „Nachunternegner“ (Vorbem.), „Maschienenführer“ (7), „keinerelei“ (6...43), „Nebengebäue“ (6...28), „einschließliche“ (5...13 ff.) | ja (Rechtschreibung) |

**Zusatz-Kennzahl für die Demo (Aggregation, Wunsch des Partners):** Beton gesamt ≈ 78,85 m³ (6...7, 6...8, 6...13, 6...14, 6...16, 6...18, 6...21, 6...24, 6...29, 6...30, 6...35) plus 12,2 m³ Sauberkeitsschicht C12/15; Betonstahl 5.400 kg + 265 kg Unterstützungskörbe ≈ 72 kg/m³ (plausibel für EFH).
