# Konkurrenz-PDF per KI einlesen

Auf der Seite *Marge* und im Vault-Tab *Wettbewerb / Marge* liest der Knopf **PDF per KI einlesen** ein Angebots- oder Preisspiegel-PDF ein.

1. Das PDF geht direkt an den eingestellten Anbieter (Claude oder Grok Bot), denselben Weg wie die KI-Auswertung und das Excel-KI-Parsing. Seitenbilder und die Textschicht werden mitgeschickt.
2. Die KI liefert OZ, Text, Menge, Einheit, Einheitspreis (EP), Angebotsbetrag (GP) und Bieter. Zahlen, die nicht in der Textschicht stehen, werden verworfen (bei gescannten Seiten ohne Text bleibt die Modellangabe).
3. Daraus entsteht eine Excel im Format der Margin-Seite (`Anbieter`, `Position`, `Einheit`, `Menge`, `Einheitspreis`, `Angebotsbetrag`, optional `Einzelkosten` / `Gemeinkosten %` / `Gewinnmarge %`). Eine Zeile `Our company` je Position nimmt Menge und, falls vorhanden, die Einzelkosten auf.
4. Die Excel kann heruntergeladen werden und landet automatisch als **neue Version** im Vault-Tab *Wettbewerb / Marge* (ohne Hash-Deduplizierung). Ein erneutes Einlesen desselben PDFs erzeugt eine weitere Version.
5. Im Vault-Tab kannst du ein PDF hochladen oder ein bereits gespeichertes PDF aus dem Vault wählen. Nach dem Einlesen gibt es den Download und optional **Im Margin-Vergleich öffnen**.

Ohne Claude- oder Grok-Bot-Anbieter antwortet die API mit einem Fehler; es gibt keinen stillen Rückfall auf den Mock und keinen Demo-Knopf in der Oberfläche.

Technisch: `POST /api/marge/pdf` (`api/app/marge_pdf.py`). Grenzen: 10 MiB, standardmäßig 20 Seiten. Keine Schlüssel oder Dateiinhalte werden geloggt.
