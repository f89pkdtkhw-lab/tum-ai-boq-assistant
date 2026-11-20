---
name: demo-vergleich
description: Vergleicht beim Hackathon die aktuelle Lösung und eine nachvollziehbare Ausgangslösung an denselben Beispielen und macht Verbesserungen und Rückschritte für den Pitch sichtbar.
---

<!-- Generiert aus .agents/skills/demo-vergleich/SKILL.md mit python tools/agents_sync.py. Hier nicht bearbeiten. -->

Lies den Case-Brief und die Abnahmebeispiele. Kläre zuerst, welche Entscheidung für den Nutzer zählt. Als Ausgangslösung eignet sich der heutige Ablauf des Partners oder eine einfache, fachlich plausible Regel. Dokumentiere, welche davon ihr tatsächlich verwendet.

**Ein Durchlauf:** QA legt Eingaben, Soll-Ergebnisse und Messgröße vor dem Lauf fest. Nutzt möglichst einen alltäglichen Fall, einen schwierigen Fall und eine unvollständige Eingabe. Führt beide Varianten unter denselben Bedingungen aus. Vergleicht bei der nächsten Änderung wieder dieselben Fälle. Ein zusätzliches unbenutztes Beispiel vom Partner eignet sich für eine letzte Kontrolle.

Für diskrete Ergebnisse kann dieses Hilfsprogramm zwei beobachtete Ausgaben mit dem Soll vergleichen. Es liest eine UTF-8-JSON-Datei mit einer Liste von Fällen. Beispiel für das Format:

```json
[{"fall":"Gruppe mit fünf Personen","soll":"raum:isar","bisher":"raum:isar","prototyp":"raum:isar"}]
```

```sh
python .agents/skills/demo-vergleich/scripts/vergleich.py ergebnisse.json
```

`null` steht bei einer Variante für einen ausgeführten Versuch ohne Ergebnis. Fehlt der Lauf selbst, kennzeichne ihn separat als offen. Für eine Zeit-, Kosten- oder Simulationsmetrik nutze die Originaleinheit und dieselben Eingaben für beide Varianten.

Halte im Issue Eingaben, Messgröße, Vergleichsmethode, Commit und Ergebnis fest. Berichte Treffer mit Nenner, neue Erfolge und Rückschritte. Liefert ein neuer Versuch keinen Vorteil, behalte den besser vorführbaren Stand. Übernimm nur reproduzierte Zahlen in den Pitch. Bei wenigen Beispielen bezieht sich die Aussage genau auf diese Fälle.
