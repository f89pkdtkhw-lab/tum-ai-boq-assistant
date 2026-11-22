# Beispieldateien

## `margin-demo.xlsx`

Synthetische Demodatei für das Margin-Modul (Wettbewerbsvergleich). Keine echten Firmen, Angebote oder Preise.

- **Projekt:** Kindertagesstätte Nord, 22 Positionen (Rohbau und Ausbau).
- **Blätter:** `Angebote` (wird von der App gelesen) und `Hinweise`.
- **Spalten:** Anbieter, Position, Einheit, Menge, Einheitspreis, Angebotsbetrag, Einzelkosten, Gemeinkosten %, Gewinnmarge %.
- **Unsere Zeilen:** Anbieter `Our company`, mit Menge, Einzelkosten, 10 % Gemeinkosten und 2 % Mindestmarge.
- **Wettbewerber (fiktiv):** Nordlicht Bau GmbH, Mainbrücke Hochbau KG und Alpenkamm Bau AG (mit Kostenaufteilung), Förde Tiefbau GmbH, Havelgrund Bau GmbH, sowie Blitzofferte Bau UG als IQR-Ausreißer (ca. 75–82 % Zuschlag).
- **Absichtlich eingebaut:** Innentüren nur vier Gebote (geringe Datenbasis) und schiefe Verteilung (Förde Tiefbau deutlich höher).

Die kanonische Kopie für die App liegt unter [`data/defaults/margin-demo.xlsx`](../../data/defaults/margin-demo.xlsx). Bei einem frischen Klon oder einem leeren Vault wird sie einmal als Standard-Vergleichsdatei in den Vault gelegt und auf der Seite *Marge* automatisch geladen. Zusätzlich bleibt die Datei unter `/workspace/margin-demo.xlsx` zum manuellen Hochladen verfügbar.
