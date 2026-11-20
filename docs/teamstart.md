# Teamstart: fünf Laptops, ein Repo

Wir arbeiten zu fünft in [einem privaten Repo](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant): zwei Macs, drei Windows-Laptops. Alles Gemeinsame läuft über GitHub, nie über USB-Sticks oder kopierte Ordner: Issues sind Aufträge, das [Team-Board (Issue #1)](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues/1) ist der Funk zwischen Menschen und Agenten, Pull Requests bringen Code nach `main`.

## So arbeiten fünf Laptops gleichzeitig, ohne sich zu stören

1. **Jeder klont das Repo selbst** und arbeitet nur in eigenen Branches. Niemand pusht auf `main`; der Push-Check blockiert das.
2. **Ein Issue = ein Branch = ein eigener Ordner (Worktree).** `python tools/aufgabe.py <Nr> --uebernehmen` legt ihn an. So können auf einem Laptop auch mehrere Agenten parallel laufen.
3. **Getrennte Ordner pro Schwerpunkt** (Tabelle in [AGENTS.md](../AGENTS.md#3-wer-besitzt-was)): Parser, Prüf-Engine, Risiko, Oberfläche, Integration. Dadurch gibt es kaum Merge-Konflikte.
4. **Kleine PRs, schnell mergen.** Lieber zehn PRs à 30 Minuten als einer à fünf Stunden. Nach jedem Merge ziehen alle mit `git fetch && git rebase origin/main` nach.
5. **Die Schnittstelle zuerst.** Der Kickoff legt Datenmodell und API-Routen mit Beispieldaten fest. Danach können Oberfläche und Backend parallel bauen, ohne aufeinander zu warten.
6. **Ein Präsentationslaptop** (Lead) startet alle zwei Stunden die Demo von `main`.

## Einmal pro Person (15 Minuten)

Voraussetzungen: Git, Python 3.11+, Node 20+, [GitHub CLI](https://cli.github.com).

| | macOS | Windows |
| --- | --- | --- |
| Werkzeuge | `brew install git gh node python@3.12` | `winget install Git.Git GitHub.cli OpenJS.NodeJS.LTS Python.Python.3.12` |
| Terminal | Terminal oder Ghostty | PowerShell oder Git Bash (Windows Terminal) |
| Python-Befehl | `python3` | `python` |
| Board-Befehl | `tools/board …` | `python tools/board.py …` (PowerShell) oder `tools/board …` (Git Bash) |

```sh
gh auth login                                   # GitHub-Einladung vorher annehmen
git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git
cd tum-ai-boq-assistant
python tools/setup.py --kommentar 2             # prüft alles, aktiviert den Push-Check, meldet sich in Issue #2
python tools/dev.py --install                   # Produkt: Oberfläche :3000, Backend :8000
```

Dann den eigenen Coding-Agenten anmelden (ein Agent pro Person reicht, beide gehen auch):

- **Claude Code:** `claude` im Repo-Ordner starten, `/login`. Liest `CLAUDE.md` → `AGENTS.md`, Skills mit `/kickoff`, `/grill-me` usw.
- **Codex:** `npm install -g @openai/codex`, dann `codex` und mit dem ChatGPT-Konto anmelden. Liest `AGENTS.md` direkt, Skills mit `$kickoff`, `$grill-me` usw. Codex sieht das Board nicht automatisch: am Anfang jeder Aufgabe „Lies `tools/board unread`“.
- **Codex Cloud (optional):** chatgpt.com/codex → GitHub verbinden → Repo freigeben. Danach startet `@codex implement this` in einem Issue einen Cloud-Agenten, `@codex review` reviewt einen PR.
- Wer mehrere Agenten gleichzeitig führen will (Mac oder Windows mit WSL): [FirstMate](firstmate.md).

GitHub-App aufs Handy, Push-Nachrichten für Erwähnungen an, Issue #1 abonnieren.

## Ein Auftrag in einer Minute

```sh
python tools/aufgabe.py 7 --uebernehmen --werkzeug "Codex"
```

Ordner im Agenten öffnen und schreiben: „Lies .auftrag.md und setze den Auftrag um.“ Fertig = Tests grün, PR offen, bei grünen Checks selbst gemergt, wichtige Änderungen mit `@all` aufs Board.

## Zeitplan bis Sonntag 12:00

| Wann | Was |
| --- | --- |
| Fr Abend | Setup auf allen fünf Laptops, Datensatz sichten, `kickoff` mit dem Case: Schnittstelle + Issues |
| Fr Nacht | Parser für ein echtes LV, erste Prüfregeln, Upload-Seite; Ende: erster Durchstich Upload → Findings |
| Sa Vormittag | Durchstich auf dem Präsentationslaptop; LLM-Prüfungen, Risikoscoring, Bericht |
| Sa Nachmittag | Testfälle mit eingebauten Fehlern, Vergleich manuell vs. Tool (`demo-vergleich`), Feinschliff UI |
| Sa Abend | Optional: EP-Vorschläge / What-if; Pitch-Story (`pitch-probe`) |
| So 09:00 | **Funktionsstopp**, nur noch Fehler beheben |
| So 10:00 | Ersatzvideo der Demo aufnehmen, Pitch proben |
| So 11:30 | Internes Abgabeziel |
| **So 12:00** | **Abgabe** |
