# Mit Coding-Agenten arbeiten

Jede Person arbeitet mit ihrem eigenen Konto und Werkzeug: Claude Code, Codex, Antigravity oder einem First Mate, der eine ganze Crew führt ([FirstMate](firstmate.md)). Verbunden ist alles über GitHub: Issues sind Aufträge, das angeheftete Issue #1 ist das Team-Board, auf dem sich Agenten Arbeit übergeben, und Pull Requests mergen die Autoren selbst, sobald die Checks grün sind. Alle Werkzeuge lesen dieselben Regeln aus [AGENTS.md](../AGENTS.md).

## Einmal pro Person

1. GitHub-Einladung annehmen, [GitHub CLI](https://cli.github.com) installieren und `gh auth login` ausführen.
2. Repo klonen und `python tools/setup.py --kommentar 2` ausführen. Das prüft Python, Git, GitHub-Zugang, Agenten und Tests, aktiviert den Push-Check und schreibt das Ergebnis in Issue #2.
3. Im eigenen Werkzeug anmelden: Claude Code mit Claude-Konto, Codex mit ChatGPT-Konto, Antigravity oder Gemini mit Google-Konto.
4. GitHub-App aufs Handy, Push-Nachrichten für Erwähnungen einschalten und Issue #1 abonnieren.
5. Diktier-App installieren ([Handy](https://github.com/cjpais/Handy) kostenlos oder Wispr Flow). Sprechen ist schneller als Tippen, vor allem nachts.
6. Mac-Nutzer richten zusätzlich FirstMate ein ([Anleitung](firstmate.md)).

## Was welches Werkzeug liest

| Werkzeug | Regeln | Skills | Skill aufrufen | Board |
| --- | --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`, importiert `AGENTS.md` | `.claude/skills/` (generierte Kopie) | `/grill-me` | automatisch über Hooks |
| Codex | `AGENTS.md` | `.agents/skills/` | `$grill-me` | `tools/board unread` laut Regeln |
| Antigravity | `AGENTS.md` | `.agents/skills/` | Skill-Namen im Chat nennen | `tools/board unread` laut Regeln |
| FirstMate | eigene Regeln plus `AGENTS.md` des Projekts | wie das Werkzeug der Crew | – | der First Mate beobachtet es |

Regeln ändert ihr nur in `AGENTS.md`, Skills nur in `.agents/skills/`, danach `python tools/agents_sync.py`.

| Skill | Wofür |
| --- | --- |
| `kickoff` | Aus dem Case: Datensatz sichten, Schnittstelle, Besitzer, Issues, Startschuss |
| `grill-me` | Plan so lange befragen, bis keine Lücke bleibt |
| `auftrag-schneiden` | Plan in parallele Issues mit getrennten Bereichen zerlegen |
| `to-tickets` | Regeln für senkrechte Scheiben, die `auftrag-schneiden` nutzt |
| `prototype` | Wegwerf-Version, um eine Idee oder Oberfläche zu prüfen |
| `tdd` | Erst ein fehlschlagender Test, dann der kleinste Code |
| `diagnosing-bugs` | Schleife für hartnäckige Fehler |
| `handoff` | Übergabe-Notiz, wenn ein Kontext voll ist |
| `pr-review` | Freiwilliges Review über Kreuz |
| `demo-vergleich` | Bisheriger Ablauf gegen Prototyp an denselben Fällen |
| `pitch-probe` | Englischer Drei-Minuten-Pitch und Fragerunde |

`grill-me`, `grilling`, `to-tickets`, `prototype`, `tdd`, `diagnosing-bugs` und `handoff` stammen aus [Matt Pococks Skills](https://github.com/mattpocock/skills) (MIT-Lizenz, liegt jeweils bei).

## Eine Aufgabe in einer Minute starten

```sh
python tools/aufgabe.py 7 --uebernehmen --werkzeug "Codex"
```

Das Skript liest das Issue, legt neben dem Repo einen eigenen Ordner (Git-Worktree) mit Branch `7-<kurzname>` vom richtigen Zielbranch an, schreibt den Auftrag nach `.auftrag.md`, weist dich zu, kommentiert die Übernahme und postet sie auf dem Board. Danach den Ordner im Werkzeug öffnen und schreiben: „Lies .auftrag.md und setze den Auftrag um.“ Ist er fertig und die Checks sind grün, mergt der Agent selbst und räumt den Worktree weg.

## Das Board

Agenten verschiedener Personen geben sich Arbeit über Issue #1, ohne dass jemand Nachrichten zwischen Terminals kopiert:

```text
[Raban · Claude] Schnittstelle ist gemergt. @Anatomik5 POST /api/lv/import erwartet jetzt dein importiere(dateiname, bytes) -> LV.
[Alisher · Codex] @f89pkdtkhw-lab GAEB-X83-Import ist auf main, 2.341 Positionen aus dem Beispiel-LV.
```

Claude Code sieht neue Posts von selbst und wartet im Hintergrund auf Erwähnungen. Codex und Antigravity lesen das Board laut `AGENTS.md` beim Start einer Aufgabe, vor jedem Commit und nach jedem Merge. Soll ein Agent von selbst aufwachen, wenn er erwähnt wird, startet ihn eine Schleife im Terminal neu:

```sh
while tools/board wait --nur-erwaehnungen; do codex exec "Lies tools/board unread und erledige, was dich betrifft."; done
```

## Wie selbstständig ein Agent arbeitet

| Stufe | Wann | Wie |
| --- | --- | --- |
| Begleitet | Schnittstellen, unklare Aufgaben | Der Agent fragt vor Befehlen und Änderungen. |
| Selbstständig auf dem Laptop | Issue mit Label `agent-bereit`, eigener Worktree | Claude Code `claude --permission-mode acceptEdits`, Codex `codex --full-auto`, Antigravity: Terminal-Befehle in den Agent-Einstellungen automatisch ausführen lassen. |
| Crew | Viele parallele Issues einer Person | Ein First Mate verteilt sie an Worker und überwacht sie ([FirstMate](firstmate.md)). |
| Cloud | Kleine Issues, während der Laptop anderes tut | Label `claude`, Kommentar `@codex implement this` oder Label `jules`. |

Auf jeder Stufe laufen die Tests vor dem Push, niemand pusht direkt auf `main`, und der Autor mergt seinen PR erst bei grünen Checks.

## Vom Handy aus

So steuert ihr eure Agenten vom Handy: Mit `/remote-control` in Claude Code (auch im First Mate) steuerst du die laufende Session aus der Claude-App unter Code. Brauchen Agenten dich, erwähnen sie dich auf dem Board, und die GitHub-App schickt dir eine Push-Nachricht.

## Cloud-Agenten einmalig einrichten (optional)

Apps an einem privaten Repo installieren kann nur der Repo-Owner. Danach verbindet jede Person ihr eigenes Konto.

| Agent | Einrichtung | Auslöser | Läuft auf dem Konto von |
| --- | --- | --- | --- |
| Claude in GitHub Actions | Owner führt in Claude Code `/install-github-app` aus; das installiert die Claude-App und hinterlegt das Secret `CLAUDE_CODE_OAUTH_TOKEN`. Den angebotenen Workflow braucht ihr nicht, er liegt schon in `.github/workflows/claude.yml`. | Label `claude` oder `@claude` in Issue oder PR | der Person, deren Token hinterlegt ist |
| Codex Cloud | Unter chatgpt.com/codex GitHub verbinden, das Repo freigeben und Code Review einschalten | `@codex review` im PR, `@codex implement this` im Issue | der Person, die kommentiert |
| Jules | Unter jules.google der Jules-App Zugriff auf das Repo geben | Label `jules` am Issue | der Person, die Jules verbunden hat |

## GitHub-Actions-Minuten

Ein privates Repo hat im kostenlosen GitHub-Plan 2.000 Minuten im Monat. Windows zählt doppelt, macOS zehnfach. Pull Requests testen deshalb nur unter Linux, Windows und macOS laufen nach dem Merge. Ein Claude-Auftrag in Actions braucht etwa 5 bis 20 Minuten. Den Verbrauch zeigt github.com/settings/billing.

## Takt bis zur Abgabe

Der Zeitplan bis Sonntag 12:00 steht im [Teamstart](teamstart.md#zeitplan-bis-sonntag-1200). Alle zwei Stunden startet der Lead die Demo von `main` auf dem Präsentationslaptop; Fehler werden sofort Issues.
