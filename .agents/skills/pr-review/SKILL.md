---
name: pr-review
description: Prüft einen Pull Request im Team-Repo gegen sein Issue, die Tests und die Code Review Rules aus AGENTS.md und schreibt ein knappes Review als Kommentar. Freiwilliges Review über Kreuz neben dem Selbst-Merge.
---

Bekommst du eine PR-Nummer, lies den PR mit `gh pr view <Nr>` und `gh pr diff <Nr>` und das verlinkte Issue mit `gh issue view <Nr>`. Ohne Nummer nimm den PR des aktuellen Branches.

1. Hole den Stand in einem eigenen Worktree und führe `python -m unittest discover -s tests -v` aus. Sieh mit `gh pr checks <Nr>` nach, ob die GitHub-Checks grün sind.
2. Spiele das Abnahmebeispiel aus dem Issue selbst durch, bei einer Oberfläche im Browser. Notiere Eingabe, erwartetes und beobachtetes Ergebnis.
3. Prüfe nach den Code Review Rules in `AGENTS.md`: nur Dateien im Bereich des Besitzers, keine unangekündigte Schnittstellenänderung, keine Schlüssel, keine neuen Abhängigkeiten, verständliche Fehlerfälle, Demo startet weiter.
4. Schreib das Ergebnis als einen Kommentar mit `gh pr review <Nr> --comment --body-file review.md`: zuerst ein Satz zum Gesamturteil, dann höchstens fünf Befunde mit Datei, Zeile und Beispiel, zuletzt die ausgeführten Prüfungen. Ist der PR schon gemergt und du findest einen echten Fehler, leg ein Issue mit dem Fehler-Formular an und erwähne den Besitzer auf dem Board.

Merge nie den PR eines anderen und gib keine Freigabe im Namen einer Person. Sag ausdrücklich, was du nicht prüfen konntest.
