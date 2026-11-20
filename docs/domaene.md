# Domänenwissen: LV, GAEB, Kalkulation

Kurzreferenz für Menschen und Agenten. Unsicheres ist markiert; im Zweifel am Datensatz prüfen statt raten.

## Teamnotizen vom Freitag (Gespräche mit Praktikern)

Abgeschrieben von zwei Notizblatt-Fotos, sinngemäß:

- **Öffentliche Ausschreibungen** sind die Hauptquelle für LVs; Plattformen wie cosuno.de sammeln Ausschreibungen → mögliche Datenbank-Quelle.
- **Plausibilitätsprüfung ist sehr wichtig.** Viele Fehler entstehen schon beim Bauherrn bzw. Planer, der das LV aufstellt.
- **Variable Ressourcen-Kalkulation mit Indexpreisen** (Materialpreise schwanken; Preisindizes, z. B. vom Statistischen Bundesamt).
- **Handschrift-OCR** zur Erkennung, z. B. für Aufträge / Aufmaße.
- **Datenfluss:** Architekt erstellt die GAEB-Datei → geht an den Bauunternehmer. Dazu oft ein PDF (Leistungsbeschreibung) mit **Kurztext** und **Langtext** je Position.
- **Datenbank X** mit Maschinennutzung (Geräteliste) → **Mengenermittlung** → **Mannstunden-Schätzung**.
- **Beispielrechnung Beton:** ca. **150 € pro m³ Beton** (Material). Lohn: **Mittellohn 25–30 €/h + ca. 80 % Lohnnebenkosten + allgemeine Geschäftskosten (X %)**.
- **Adaptive Learning** über echte Daten: der Ansatz lernt aus abgerechneten Projekten.
- **Baukalkulations-PDF** (Lehrbuch/Leitfaden) als Wissensquelle zum Lernen.

Ausführlicher, strukturiert und mit **12 % AGK** als Richtwert: [Notizen-Kontext](quellen/Challenge_A_Notizen_Kontext.pdf). Weitere Datenquelle neben cosuno: Ausschreibungen der Deutschen Bahn. Ein Ziel aus den Notizen: ähnliche Positionen automatisch zusammenfassen (z. B. verschiedene Betonsorten) und sich auf die ~100 wichtigsten statt aller 9.000 Zeilen konzentrieren.

## 20 Fähigkeiten einer Kalkulations-KI (Kurzfassung)

Volltext: [Skills der KI](quellen/Skills%20der%20KI.pdf). Fett = für unseren Prototyp relevant.

- **Unterlagen verstehen:** **LV auswerten (Positionstypen: Bedarf, Alternative, Wahl)** · **Vertragsbedingungen prüfen** (VOB/B, ZTV, Vertragsstrafen, Sicherheiten, Fristen) · **Widersprüche und Lücken als Rückfragen formulieren** · **Mengen plausibilisieren**
- **Kalkulieren:** Aufwandswerte · Lohn (Mittellohn + Lohnnebenkosten) · Material (Preisgleitung, Verschnitt) · Geräte (BGL) · Nachunternehmer · Baustellengemeinkosten · Zuschläge AGK, W+G
- **Risiko und Strategie:** **Risiken mit Eintrittswahrscheinlichkeit × Schadenshöhe** · **Wagnis in € statt pauschal** · Bauzeit · **Nachtragspotenzial (und wo man selbst gefährdet ist)** · Angebotsstrategie (konservativ, marktgerecht, aggressiv)
- **Ergebnis und Qualität:** Angebot erstellen · **Plausibilitätschecks €/m², €/m³, Rechenfehler** · Lernen aus Nachkalkulation
- **Leitplanken:** Schätzungen immer kennzeichnen; Preis nie ohne Freigabe des Kalkulators herausgeben.

## Begriffe

| Begriff | Bedeutung |
| --- | --- |
| LV (Leistungsverzeichnis) | Liste aller Leistungen einer Ausschreibung, gegliedert in Lose, Titel/Abschnitte und Positionen |
| OZ (Ordnungszahl) | Positionsnummer, z. B. `01.02.0030`. Gliederung steht im LV-Kopf (z. B. `11PPPPI`) |
| Kurztext / Langtext | Kurztext = Überschrift (max. ~70 Zeichen), Langtext = vollständige Leistungsbeschreibung, rechtlich maßgeblich |
| Menge, Einheit (ME) | z. B. `125,500 m³`; typische Einheiten: m, m², m³, St, kg, t, h, psch (pauschal) |
| EP / GP | Einheitspreis / Gesamtpreis; **GP = Menge × EP** (gerundet auf 2 Nachkommastellen) |
| Normalposition (NP) | wird normal ausgeführt und abgerechnet |
| Bedarfs-/Eventualposition (EP/BedP) | nur bei Bedarf ausgeführt, oft ohne GP in der Summe → klassischer Streit- und Spekulationspunkt |
| Alternativ-/Wahlposition | Alternative zu einer Grundposition, Auftraggeber wählt |
| Zulageposition | Zuschlag auf eine andere Position (z. B. „Zulage für Sichtbeton“) |
| Pauschalposition (psch) | Menge 1, Risiko liegt beim Bieter |
| Nachtrag | Mehrvergütung bei geänderten oder zusätzlichen Leistungen (VOB/B § 2 Abs. 5, 6, 8); Ursache meist lückenhafte oder unklare LVs |
| Bieterfrage | Rückfrage an den Auftraggeber während der Angebotsphase; günstigste Art, Unklarheiten zu klären |
| DIN 276 | Kostengruppen (KG 300 Bauwerk – Baukonstruktion, KG 400 Technische Anlagen …) |
| STLB-Bau / StLB | standardisierte Leistungstexte; Abweichungen davon sind ein Prüfsignal |
| DIN 18195 → DIN 18533 | Abdichtungsnorm DIN 18195 wurde 2017 durch DIN 18531–18535 ersetzt; ein LV, das noch DIN 18195-4 nennt, ist veraltet |
| VOB/A § 7 | Leistung ist **eindeutig und erschöpfend** zu beschreiben; ungewöhnliche Wagnisse dürfen dem Bieter nicht aufgebürdet werden |

## GAEB-Formate

GAEB DA XML (aktuell 3.x) ist der Austauschstandard. Datenaustauschphasen (DA):

| Endung | Phase | Inhalt |
| --- | --- | --- |
| `.x81` | LV-Übernahme | Leistungsbeschreibung |
| `.x83` | Angebotsaufforderung | LV mit Mengen, **ohne Preise** – typische Eingabe für den Kalkulator |
| `.x84` | Angebotsabgabe | LV mit Preisen des Bieters |
| `.x85` | Nebenangebot | |
| `.x86` | Auftragserteilung | |
| `.d83` / `.p83` | GAEB 90 / 2000 | ältere Flat-File-Formate (feste Spalten, `.d8x`) bzw. Tag-Format (`.p8x`) |

XML-Struktur (vereinfacht, Namespace beachten): `GAEB > Award > BoQ > BoQBody > BoQCtgy (Titel, rekursiv) > BoQBody > Itemlist > Item` mit `Qty`, `QU` (Einheit), `UP` (EP), `IT` (GP), `Description > CompleteText > OutlineText` (Kurztext) und `DetailTxt` (Langtext). Python: eigener Parser mit `xml.etree`/`lxml` ist meist robuster als Bibliotheken; Langtexte enthalten oft eingebettetes HTML-ähnliches Markup.

## Fehler- und Risikokatalog (Startpunkt für Prüfregeln)

**Formal / rechnerisch (feste Regeln, kein LLM nötig)**
- GP ≠ Menge × EP; Titelsumme ≠ Summe der Positionen
- doppelte OZ, Lücken oder Sprünge in der Nummerierung, falsche OZ-Maske
- Menge 0 oder leer bei Normalposition; fehlende Einheit; ungewöhnliche Einheit für den Text (Beton in m², Fläche in St)
- Mengen-Ausreißer im Vergleich zu verwandten Positionen (z. B. Schalung vs. Betonvolumen)
- Tippfehler im Kurztext, Kurztext passt nicht zum Langtext
- leere Langtexte, Platzhalter wie „xxx“, „siehe Plan“, „nach Angabe AG“

**Inhaltlich (LLM + Heuristik)**
- vage Leistungsbeschreibung: „nach Erfordernis“, „ca.“, „bauseits“, „gem. Absprache“, „inkl. aller Nebenleistungen“, „nach Wahl des AN“
- Verweise auf nicht beigefügte Pläne, Gutachten (Baugrund!), Normen
- Widersprüche zwischen Positionen (Betongüte C25/30 vs. C30/37, verschiedene Dämmstärken)
- **fehlende Positionen** je Gewerk: z. B. Beton ohne Bewehrung, Schalung oder Nachbehandlung; Erdarbeiten ohne Entsorgung; Abbruch ohne Schadstoffuntersuchung
- Bedarfspositionen mit großen Mengen, Pauschalen mit großem Umfang, Stundenlohnarbeiten
- Risikoverlagerung auf den Bieter: Bodenklassen/Homogenbereiche fehlen, Wasserhaltung offen, Entsorgung „nach Anfall“

**Nachtragspotenzial** (Sicht Bieter): unvollständige oder mehrdeutige Positionen, zu niedrige Mengen (Spekulation: Mengenmehrung nach VOB/B § 2 Abs. 3 bei >10 %), fehlende Nebenleistungen, Erschwernisse nicht ausgeschrieben.

## Kalkulation (für optionale EP-Vorschläge)

```text
EP = Lohn + Material + Gerät + Nachunternehmer, darauf Zuschläge
Lohn       = Aufwandswert [h/ME] × Mittellohn
Mittellohn ≈ 25–30 €/h  (+ ~80 % Lohnnebenkosten → kalkulatorisch ~45–55 €/h)
Zuschläge  = Baustellengemeinkosten + Allgemeine Geschäftskosten (AGK, oft 8–12 %) + Wagnis und Gewinn (oft 3–6 %)
Beispiel Beton: Material ~150 €/m³ + Einbau (Aufwandswert × Lohn) + Gerät (Pumpe) + Zuschläge
```

Die Prozentwerte für AGK und W+G sind übliche Größenordnungen, keine belegten Werte aus unserem Datensatz; im Produkt als einstellbare Parameter führen (What-if).
