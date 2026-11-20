---
name: auftrag-schneiden
description: Zerlegt den Case-Brief oder einen Plan in parallele GitHub-Issues in unserem Format, mit Besitzer aus der Besitzer-Tabelle, getrenntem Datei-Bereich, Abnahmetest, Zielbranch und Abhängigkeiten, sodass viele Agenten gleichzeitig arbeiten, ohne sich zu stören.
---

<!-- Generiert aus .agents/skills/auftrag-schneiden/SKILL.md mit python tools/agents_sync.py. Hier nicht bearbeiten. -->

Lies `docs/case.md`, die Besitzer-Tabelle in `AGENTS.md` (Abschnitt 3), die offenen Issues (`gh issue list --state open`) und die Ordnerstruktur. Kläre das Ziel der nächsten Demo in einem Satz, bevor du schneidest. Ist der Plan noch unscharf, schlage zuerst `grill-me` vor.

1. Schneide nach den Regeln aus dem Skill `to-tickets`: senkrechte Scheiben, die einen schmalen, aber vollständigen Weg durch alle Schichten bauen und für sich vorführbar sind. Jede Scheibe passt in ein frisches Kontextfenster.
2. Jeder Auftrag liegt im Bereich genau eines Besitzers aus der Besitzer-Tabelle. Zwei offene Aufträge teilen sich keine Datei. Wo das nicht geht, kommt zuerst ein kurzer Auftrag für die gemeinsame Schnittstelle mit festen Beispieldaten, damit Oberfläche und Logik danach parallel starten.
3. Lege die Schnittstelle ausdrücklich fest: Funktionsnamen oder Route, Felder, eine Beispiel-Eingabe und die erwartete Ausgabe.
4. Schreib jeden Abnahmetest als konkrete Eingabe und überprüfbares Ergebnis, nicht als Absicht.
5. Zeig die Liste als Tabelle (Titel, Besitzer, Bereich, blockiert durch, Werkzeug). Im Kickoff ist der Case-Startauftrag die Zustimmung: Lege die Issues sofort an, Blocker zuerst; die Freigaberunde aus `to-tickets` entfällt. Außerhalb des Kickoffs lege sie erst nach Zustimmung an. Nutze genau diese Überschriften, damit `tools/aufgabe.py` sie lesen kann:

```markdown
### Verantwortliche Person

github-login

### Ergebnis und Abnahmetest

Für die Eingabe … zeigt die Oberfläche …

### Bereich

web/src/suche/, tests/test_suche.py

### Zielbranch

main

### Werkzeug

egal

### Schnittstellen und Abhängigkeiten

Blockiert durch #12 (Datenformat).
```

```sh
gh issue create --title "Aufgabe · …" --body-file auftrag.md --label agent-bereit --label modell:ui --assignee github-login
```

Gib jedem Issue genau ein Modell-Label nach Aufgabe: `modell:klein` (kleine, klar beschriebene Änderung), `modell:ui` (Oberfläche für die Demo), `modell:schwer` (Schnittstelle, Architektur, unklar), `modell:bugfix` (Implementierung gegen fertige Spezifikation oder Fehler mit bekannter Ursache), `modell:recherche` (nur lesen und berichten) oder `modell:text` (Doku, Pitch, Texte nach geklärtem Plan, günstiges Modell). Unklare Produktentscheidungen bleiben `modell:schwer`. Der First Mate und `tools/aufgabe.py` wählen danach das Modell.

Nennt ein Issue eine Datei, die erst ein anderes Issue liefert, trage dessen Nummer und die Datei unter „Schnittstellen und Abhängigkeiten“ als Blocker ein. Prüfe das besonders für Pitch-Verweise auf `docs/demo.md` und `data/vergleich.md`. Jedes Logik-Issue bekommt sein eigenes bereits verdrahtetes Platzhalter-Modul mit festem Vertrag und eine eigene Testdatei; `api/app/main.py` bleibt im vorgeschalteten Schnittstellen-PR.

Setze `agent-bereit` (auch beim obigen `gh issue create`) nur, wenn Bereich, Abnahmetest und Zielbranch vollständig sind und kein Blocker offen ist. Der zuständige First Mate ergänzt das Label nach dem Merge der Blocker. Poste am Ende auf dem Board, welche Issues sofort starten können, und erwähne die Besitzer mit ihrem GitHub-Login.
