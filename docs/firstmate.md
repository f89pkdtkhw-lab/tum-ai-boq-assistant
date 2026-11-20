# FirstMate: ein Agent als Manager einer ganzen Crew

Jede Person spricht nur noch mit einem Agenten, dem First Mate. Er zerlegt die Arbeit, startet für jede Aufgabe einen eigenen Coding-Agenten in einem eigenen Git-Worktree, überwacht ihn bis zum Merge und meldet sich nur, wenn eine Entscheidung nötig ist. Dieses Setup hat bei Knight Hacks und Cal Hacks Preise gewonnen, mit 72 und 252 Worker-Agenten auf einer Seite eines Viererteams. Die Werkzeuge sind Open Source: [FirstMate](https://github.com/kunchenguid/firstmate) und quota-axi von Kun Chen, [Herdr](https://github.com/herdrdev/herdr) von herdrdev, [Handy](https://github.com/cjpais/Handy) von CJ Pais.

So greift es bei uns ineinander:

| Baustein | Aufgabe |
| --- | --- |
| First Mate pro Person | Arbeitet die Issues seines Menschen ab, nur in dessen Ordnern laut Besitzer-Tabelle in `AGENTS.md` |
| Crew | Claude Code und Codex als Worker, Modell je nach Aufgabe aus `tools/firstmate/crew-dispatch.json` |
| Herdr | Ein Fenster pro Agent; man sieht, wer arbeitet und wer wartet |
| quota-axi | Neue Arbeit geht zum Abo mit dem meisten Restkontingent |
| Team-Board, Issue #1 | Die First Mates und Agenten verschiedener Personen geben sich darüber Arbeit weiter |
| Handy | Claude-App mit Remote Control zum Reden, GitHub-App für Erwähnungen auf dem Board |

## Maximal autonom: jede Person spricht nur mit ihrem First Mate

```text
 Laptop 1..5: Mensch ──► First Mate (Claude ODER Codex) ──► 3–5 Worker (Claude/Codex je nach Aufgabe)
                               │  liest/schreibt                    │ eigener Worktree + Branch pro Issue
                               ▼                                    ▼
            GitHub = einziger gemeinsamer Stand:  Issues (Queue) · Label in-arbeit (Sperre) · Board #1 (Funk) · PRs + CI
                               ▲
                     python3 tools/stand.py  →  Lagebild aller fünf Crews + Überschneidungs-Warnung
```

1. **Ein Gesprächspartner.** Du redest nur mit deinem First Mate, am Laptop oder per `/remote-control` vom Handy. Er zerlegt, startet Worker, überwacht, mergt.
2. **Ziehen statt zuteilen.** Ist ein Worker-Platz frei, holt sich der First Mate mit `python3 tools/stand.py --naechstes` das nächste freie `agent-bereit`-Issue (erst deine, dann unverteilte) und übernimmt es mit `python3 tools/aufgabe.py <Nr> --uebernehmen`. Das setzt dich als Assignee und das Label `in-arbeit`: Für alle anderen First Mates ist das Issue damit gesperrt.
3. **Keine Überlappung.** Jedes Issue nennt seinen *Bereich* (Dateien/Ordner). `tools/stand.py` warnt, wenn zwei laufende Issues denselben Bereich oder zwei offene PRs dieselbe Datei anfassen. Der First Mate pausiert dann den späteren und klärt es auf dem Board.
4. **Alle sehen alles.** Jeder First Mate ruft bei jeder Runde `tools/stand.py` und `tools/board unread` auf; Merges, die andere betreffen, gehen mit `@all` aufs Board.
5. **Queue leer?** Der First Mate schneidet in seinem Bereich selbst neue Issues aus `docs/case.md` (Skill `auftrag-schneiden`) und kündigt sie an. Der Lead-First-Mate (@f89pkdtkhw-lab) hält die Gesamt-Queue gefüllt.
6. **Claude ↔ Codex ohne Verlust.** Der Stand einer Aufgabe liegt nie nur in einer Session, sondern im Issue, im Branch, in `.auftrag.md` und im Übergabe-Kommentar (Skill `handoff`). Darum kann ein Codex-Worker fortsetzen, was ein Claude-Worker begonnen hat. Der First Mate wählt pro Aufgabe nach `crew-dispatch.json` und weicht bei leerem Kontingent (`quota-axi`) automatisch auf den anderen Anbieter aus. Auch der First Mate selbst ist austauschbar: Session beenden, in `~/firstmate` `codex` statt `claude` starten; Backlog und Captain-Vorlieben liegen in `~/firstmate/data/` und gelten weiter.

Die Regeln dafür stehen in [tools/firstmate/captain.md](../tools/firstmate/captain.md); `bash tools/firstmate/setup.sh "Vorname"` schreibt sie in deinen FirstMate (eine alte Fassung wird vorher gesichert).

**Wer keinen FirstMate hat** (z. B. Windows ohne WSL), arbeitet genauso, nur von Hand: `python tools/stand.py --naechstes`, dann `python tools/aufgabe.py <Nr> --uebernehmen` und den Ordner in Claude Code oder Codex öffnen.

## Installation auf dem Mac

In dieser Reihenfolge, Befehle von oben nach unten:

```sh
brew install --cask ghostty                  # Terminal
curl -fsSL https://claude.ai/install.sh | bash
npm install -g @openai/codex                 # oder: brew install --cask codex
brew install herdr gh jq tmux node
npm install -g quota-axi
brew install --cask handy                    # Diktieren, kostenlos und offline; Alternative: Wispr Flow
```

Danach `claude` und `codex` je einmal starten und anmelden, `gh auth login` ausführen und im Team-Repo:

```sh
bash tools/firstmate/setup.sh "Dein Vorname"
```

Das Skript prüft alle Werkzeuge, klont FirstMate nach `~/firstmate` und schreibt dort die lokalen Einstellungen: Herdr als Fensterverwaltung, unsere Modellwahl und deine Captain-Vorlieben mit Board, Besitzer-Tabelle und Merge durch den First Mate.

## Installation unter Windows (WSL)

FirstMate und Herdr brauchen macOS oder Linux. Unter Windows läuft beides in WSL, einem Linux direkt in Windows.

1. PowerShell **als Administrator** öffnen, `wsl --install -d Ubuntu` ausführen und Windows neu starten. Danach Ubuntu aus dem Startmenü öffnen und einen Linux-Benutzer anlegen.
2. In Ubuntu die Grundwerkzeuge installieren:

   ```sh
   sudo apt update && sudo apt install -y git jq tmux python3 python3-venv nodejs npm curl
   curl -fsSL https://claude.ai/install.sh | bash
   sudo npm install -g @openai/codex quota-axi
   curl -fsSL https://herdr.dev/install.sh | sh
   ```

   Die GitHub CLI nach der [Linux-Anleitung](https://github.com/cli/cli/blob/trunk/docs/install_linux.md) installieren, dann `gh auth login`.
3. Claude Code und Codex in Ubuntu je einmal starten und anmelden. Die Anmeldung unter Windows gilt in WSL nicht.
4. Das Team-Repo **im Linux-Dateisystem** klonen, nicht unter `/mnt/c`, sonst sind Git und die Agenten langsam:

   ```sh
   git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git ~/tum-ai-boq-assistant
   cd ~/tum-ai-boq-assistant && python3 tools/setup.py
   bash tools/firstmate/setup.sh "Raban"
   ```

Als Terminal dient Windows Terminal mit dem Ubuntu-Profil statt Ghostty. Handy oder Wispr Flow gibt es auch für Windows.

## Eine Session starten

1. Terminal öffnen und `herdr` starten.
2. In einem Herdr-Fenster: `cd ~/firstmate` und `claude`.
3. Beim ersten Mal: „Füge https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant als Projekt im Modus direct-PR +yolo hinzu.“ `direct-PR` heißt, die Crew öffnet fertige Pull Requests; mit `+yolo` mergt der First Mate nach erfolgreichen lokalen Tests und grünen GitHub-Checks. Die Worker mergen nicht selbst. Ohne FirstMate gilt der Selbst-Merge aus `AGENTS.md`.
4. Dann sagst du, was gebaut werden soll, z. B. „Arbeite alle Issues mit Label agent-bereit ab, die mir zugewiesen sind.“ Der First Mate öffnet pro Worker ein Herdr-Fenster; du kannst in jedes hineinklicken.

Bleibt ein Worker an einer Rückfrage hängen, kann der First Mate sie selbst beantworten, indem er in dessen Fenster tippt. Läuft ein Abo leer, wählt er über quota-axi für neue Aufgaben den Anbieter mit Reserve.

## Leitstelle: alles in einem Fenster

```sh
bash tools/leitstelle.sh
```

Öffnet ein Fenster mit drei Bereichen: links Herdr mit First Mate und allen Worker-Fenstern (dort `claude` eingeben), rechts oben `quota-axi` mit dem Restkontingent jedes Abos, rechts unten die letzten Posts vom Team-Board. Klicken wechselt den Bereich, ebenso Strg+B und eine Pfeiltaste. Strg+B, dann D schließt das Fenster, ohne etwas zu beenden; derselbe Befehl holt die Leitstelle zurück. Unter Windows startet eine Desktop-Verknüpfung `Leitstelle.cmd` das Gleiche in Ubuntu:

```bat
@echo off
wt.exe wsl.exe -d Ubuntu --cd ~ -- bash -lc "~/tum-ai-boq-assistant/tools/leitstelle.sh"
```

## Kommandozentrale im Browser

Die Leitstelle startet nebenbei `python3 tools/dashboard.py`; unter Windows öffnet die Desktop-Verknüpfung `Dashboard.cmd` es direkt. Im Browser unter http://localhost:8770:

- **First-Mate-Konsole** in Farbe mit Eingabefeld (Enter sendet) und Knöpfen für Enter, Esc, Pfeile, 1–3, y/n und Strg+C.
- **Live-Kachel pro Worker**; wer auf dich wartet, steht gelb leuchtend ganz vorn. Klick öffnet die Konsole des Workers, dort beantwortest du Rückfragen direkt.
- **Team-Board** mit Eingabefeld, Erwähnungen hervorgehoben; Posts ohne Präfix bekommen `[<login> · Leitstelle]`.
- Kontingent-Ringe, Countdown bis Sonntag 11:30 (internes Ziel), Issues pro Person, PRs mit CI-Ampel.
- **Alarme** (Glocke oben rechts): Ton und Windows-Benachrichtigung, wenn ein Agent wartet oder du erwähnt wirst.

Die Seite steuert echte Agenten. Sie lauscht nur auf 127.0.0.1, und jeder steuernde Aufruf braucht das Sitzungs-Token der Seite und denselben Origin.

## Vom Handy aus steuern

- **Reden:** Im First-Mate-Fenster `/remote-control` eingeben oder die Session gleich mit `claude remote-control` starten. In der Claude-App auf dem Handy unter Code erscheint die Session; dort schreibst oder diktierst du wie am Laptop. Der Laptop muss an und online bleiben.
- **Gerufen werden:** Agenten erwähnen dich auf dem Board mit deinem GitHub-Login, wenn sie eine Entscheidung, einen Zugang oder Hilfe brauchen. Installiere die GitHub-App, aktiviere Push-Nachrichten für Erwähnungen und abonniere Issue #1. Jede Erwähnung kommt dann als Nachricht aufs Handy.
- **Auf dem Laufenden bleiben:** Jeder fertige Merge, der andere betrifft, steht mit `@all` auf dem Board; die GitHub-App zeigt das Board als Verlauf.

## Modellwahl

`tools/firstmate/crew-dispatch.json` wird bei der Einrichtung nach `~/firstmate/config/` kopiert. FirstMate liest die Regeln in normaler Sprache und wählt pro Aufgabe:

| Aufgabe | Claude | Codex | Google |
| --- | --- | --- | --- |
| Kleine Änderung in ein bis zwei Dateien | haiku | gpt-6-luna | – |
| Oberfläche, die die Jury sieht | opus | – | – |
| Schwer oder unklar, Schnittstelle, Planung | opus | gpt-6.1-sol | – |
| Implementierung gegen fertige Spezifikation oder Fehler mit bekannter Ursache (`modell:bugfix`) | sonnet | gpt-6.1-sol | – |
| Recherche und Lesen | – | gpt-6.1-sol | – |
| Doku, Pitch, Texte nach geklärtem Plan (`modell:text`) | haiku | gpt-6-luna | – |
| Alles andere | sonnet | gpt-6.1-sol | – |

`modell:bugfix` behält seinen Namen für spezifizierte Implementierung und bekannte Fehlerursachen. Modellnamen ändern sich oft. Vergleiche sie vor dem Wochenende mit der Modellauswahl in Claude Code und Codex und passe die Datei an. `quota-axi --tui` zeigt das Restkontingent jedes Abos live. Nach Änderungen an den Repo-Vorlagen die Einrichtung erneut ausführen, damit die Modellregeln aktualisiert werden. Bestehende Captain-Vorlieben bleiben dabei erhalten; Änderungen aus `tools/firstmate/captain.md` lässt du deinen First Mate vor dem Kickoff übernehmen.

## Wer FirstMate nutzt

Empfehlung: Die beiden Mac-Nutzer richten FirstMate ein; die Windows-Laptops arbeiten direkt mit Claude Code oder Codex und `tools/aufgabe.py`. Wer unter Windows eine Crew will, nimmt den WSL-Weg oben.

## Grenzen

- Jede Crew arbeitet in den Ordnern ihres Menschen. Die Integrations-Crew des Leads darf einmalig die minimal nötigen Fremddateien für die Kickoff-Schnittstelle anpassen, nach Ankündigung mit `@all` und mit späterer Besitzer-Zuordnung einschließlich eigener Modul-Tests. Die Besitzer-Tabelle muss vor dem Code stehen. Danach starten die First Mates die auf dem Board angekündigten `agent-bereit`-Issues ohne weitere Bestätigung; Folge-Issues geben sie nach dem Merge der benannten Blocker frei.
- Viele Worker auf einem GitHub-Konto teilen sich 5.000 API-Aufrufe pro Stunde. Deshalb beobachtet nur der First Mate das Board; Worker lesen es vor Commits. Sind FirstMate-Variablen (`FM_…`) gesetzt, schalten die Claude-Hooks die Warte-Schleife von selbst ab; sonst vor dem Start `export BOARD_WAIT=off` setzen.
- Herdr, Ghostty und Homebrew-Befehle oben gelten für den Mac; unter Windows nur über WSL.

Gemini CLI nimmt keine privaten Google-Konten mehr an. Das Google-Abo nutzt ihr über Antigravity in der IDE.
