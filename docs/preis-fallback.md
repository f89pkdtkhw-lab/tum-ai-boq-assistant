# Preis-Fallback: Indexpreis und Webrecherche (t237)

Findet die Kalkulation für eine Position keinen Preis, wird in dieser Reihenfolge nachgeschaut:

1. **Hochgeladene Preisliste**: OZ, Text, Ähnlichkeit ≥ 0,8, gleiche Einheit.
2. **Preisdatenbank**: dieselben Regeln.
3. **Indexpreis**, nur für rohstoffnahe Leistungen (`api/app/pruefung/preis_fallback.py`):
   - Der Kurztext wird per Stichwort einem Material zugeordnet: Bitumen, Bitumenbahnen, Dämmstoffe, WDVS, Beton/Zement, Betonstahl, Mauersteine, Bauholz, Baustahl, Kupfer/Titanzink oder Dachziegel.
   - Die Einheit muss passen.
   - EP-Spanne = Referenzspanne (Basisjahr 2021, netto) × Baupreisindex-Faktor des passenden Leistungsbereichs.
   - Der geschätzte EP ist die Mitte der Spanne.
4. **Webrecherche** für alle Positionen, die danach noch keinen Preis haben:
   - Nutzt denselben Helfer wie die Tiefenrecherche (`recherche.recherchiere_fehlende_preise`, Schritt `preise`).
   - Es zählen nur Quellen, deren URL in genau diesem Aufruf gefunden wurde.
   - Der EP ist die Mitte der recherchierten Marktspanne.
   - Läuft nur bei aktiver Tiefenrecherche (Claude mit Websuche). Im Mock-Modus läuft keine Recherche, das Ergebnis ist also deterministisch.
   - Timeout: `PREIS_RECHERCHE_TIMEOUT` (Standard 180 s).

Jede Schätzung ist so gekennzeichnet:
- `treffer` = `index` oder `recherche`
- `geschaetzt: true`
- `ep_von` und `ep_bis`
- `preis_quellen` und `schaetzung_hinweis`

Die Kalkulation trägt zusätzlich `enthaelt_schaetzungen` und `geschaetzt_anzahl`. In der UI erscheint das Badge „Geschätzt – Index“ bzw. „Geschätzt – Recherche“; ein Klick öffnet ein Popover mit den Quellen. Fehler bei einer Schätzung landen in `warnungen`, die Analyse läuft immer weiter.

## Quellen und Annahmen

- **Indexwerte**: Destatis, GENESIS-Tabelle 61261-0001 „Baupreisindizes“, Wohngebäude, Jahresdurchschnitt 2025, 2021 = 100.
  - Abdichtungsarbeiten 132,8
  - Wärmedämm-Verbundsysteme 136,5
  - Betonarbeiten 124,1
  - Mauerarbeiten 122,6
  - Zimmer- und Holzbauarbeiten 122,4
  - Stahlbauarbeiten 123,8
  - Klempnerarbeiten 138,9
  - Dachdeckungsarbeiten 140,9
  - Für Dämmstoffe ohne Putzsystem ist der WDVS-Index der nächstliegende veröffentlichte Index.
  - Neue Jahreswerte trägt man in `BAUPREISINDEX` und `INDEX_JAHR` ein.
- **Referenzspannen** (`REFERENZEN`) sind **grobe Richtwerte von LV Scout und keine amtlichen Zahlen**:
  - Sie gelten für Liefern und Einbauen, netto, ohne regionale oder projektbezogene Zuschläge.
  - Sie dienen nur als Platzhalter, bis eine Preisliste oder ein Angebot vorliegt.
  - Eine Erzeugerpreisindex-Reihe (Destatis 61241, z. B. Bitumen oder Betonstahl) kann später je Material eingetragen werden, ohne die Logik zu ändern.
- Positionen ohne klaren Rohstoffbezug, etwa Baustelleneinrichtung oder Stundenlohn, bekommen keinen Indexpreis und gehen direkt in die Webrecherche.
