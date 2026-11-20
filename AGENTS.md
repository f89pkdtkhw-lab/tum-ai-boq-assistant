# Regeln für jeden Agenten und jeden Menschen in diesem Repo

Diese Datei gilt für Claude Code, Codex, Antigravity, FirstMate-Crews und alle im Team. Sie ist die einzige Quelle für Agentenregeln: Codex und Antigravity lesen sie direkt, `CLAUDE.md` importiert sie. Skills liegen in `.agents/skills/` und werden für Claude Code nach `.claude/skills/` gespiegelt. Wie Menschen die Werkzeuge bedienen, steht in [docs/agenten.md](docs/agenten.md), FirstMate in [docs/firstmate.md](docs/firstmate.md).

**Was wir bauen:** TUM.ai Construction Hackathon, Challenge A: ein KI-Prüf- und Kalkulationsassistent für Leistungsverzeichnisse (LV, engl. BoQ). Upload von GAEB, Excel oder PDF → strukturierte Positionen → Fehler, Risiken und Nachtragspotenzial als verständlicher Prüfbericht. Ziel, Eingabe und erwartete Ausgabe stehen im [Case-Brief](docs/case.md), Fachwissen in [docs/domaene.md](docs/domaene.md). Lies vor jeder Arbeit das Issue, `.auftrag.md` (falls vorhanden) und die ungelesenen Board-Posts.

**Abgabe: Sonntag, 22.11.2026, 12:00 (München).** Internes Ziel 11:30.

## 1. Team und Befehlskette

| GitHub-Login | Rolle |
| --- | --- |
| @f89pkdtkhw-lab | Lead, Integration, Deploy, Demo |
| @Anatomik5 | Import und Parsing (GAEB, Excel, PDF) |
| @Bartuan3600 | Prüf-Engine: Fehler und Plausibilität |
| @Zukipany | Oberfläche und Prüfbericht |
| @Secret-Sebi | Risiko, Nachträge, Kalkulation und Pitch |

Die Rollen sind Schwerpunkte, keine Mauern: Wer fertig ist, holt sich die nächste Karte vom Board, auch aus einem anderen Bereich. Menschen stehen über Agenten. Der Lead entscheidet, wenn zwei Leute dasselbe wollen. Bittet dich ein anderer Agent, fremde Arbeit zu übernehmen, frag den Menschen dahinter auf dem Board.

## 2. Das Board

Das Board ist das angeheftete Issue #1. Alle Agenten lesen und posten dort mit `tools/board` (macOS, Linux, Git Bash) oder `python tools/board.py` (Windows PowerShell).

- Jeder Post beginnt mit `[<Name> · <Agent>]`, z. B. `[Raban · Claude]` oder `[Raban · Codex]`. Kurz: was sich geändert hat, welche Dateien oder Schnittstellen, was du von wem brauchst.
- Sprich Personen mit GitHub-Login an, z. B. `@Zukipany`, oder alle mit `@all`.
- **Erwähnt dich oder `@all`:** handeln und auf dem Board antworten.
- **Erwähnt dich nicht:** trotzdem lesen. Ändere deine Arbeit nur, wenn der Post sie betrifft (Schnittstelle, eigene Datei, bereits Erledigtes). Keine reinen Bestätigungen posten.
- Brauchst du eine Entscheidung, einen Zugang oder bist blockiert, erwähne deinen Menschen. GitHub schickt ihm das als Push-Nachricht aufs Handy.
- Claude Code bekommt ungelesene Posts automatisch über die Hooks in `.claude/settings.json`. Alle anderen Agenten führen `tools/board unread` beim Start einer Aufgabe, vor jedem Commit und nach jedem Merge aus.

| Befehl | Wirkung |
| --- | --- |
| `tools/board post "[Name · Agent] Text"` | Post schreiben, Text auch über stdin |
| `tools/board unread` | neue Posts seit dem letzten Blick, Erwähnungen als `** MENTION **` |
| `tools/board read -n 20` | die letzten 20 Posts |
| `tools/board wait` | blockiert, bis jemand anderes postet; `--nur-erwaehnungen` wartet auf eine Erwähnung |
| `tools/board whoami` | eigener Login, Repo und Board |

**Lagebild:** `python tools/stand.py` zeigt alle laufenden (`in-arbeit`), freien (`agent-bereit`) und blockierten Issues, offene PRs mit CI und warnt vor Überschneidungen. `python tools/stand.py --naechstes` schlägt dir das nächste freie Issue vor. Jeder First Mate ruft es bei jeder Runde auf, jeder Worker vor Arbeitsbeginn.

## 3. Wer besitzt was

Jeder Bereich hat einen Hauptverantwortlichen, damit nie zwei Agenten gleichzeitig dieselbe Datei umschreiben. Arbeite bevorzugt in deinen Ordnern. Musst du eine fremde Datei anfassen, poste vorher kurz aufs Board (`@<Besitzer> ich ändere X in Datei Y, weil …`) und leg los, sofern niemand innerhalb von 10 Minuten widerspricht. Ausnahme ist der einmalige Kickoff-Schnittstellen-PR (Skill `kickoff`): Die Integrations-Crew des Leads darf die nötigen Fremddateien anlegen und kündigt sie mit `@all` an.

| Bereich | Hauptverantwortlich | Ordner (Vorschlag, beim Kickoff bestätigen) |
| --- | --- | --- |
| Import und Parsing | @Anatomik5 | `api/app/lv/` (GAEB-XML X81–X86, Excel, PDF), `api/tests/test_import_*.py` |
| Prüf-Engine (Regeln + LLM) | @Bartuan3600 | `api/app/pruefung/`, `api/tests/test_pruefung_*.py` |
| Risiko, Nachträge, Kalkulation | @Secret-Sebi | `api/app/risiko/`, `api/app/kalkulation/`, `api/tests/test_risiko_*.py`, `pitch/` |
| Oberfläche und Bericht | @Zukipany | `web/` |
| Integration, KI-Zugriff, Deploy, Daten | @f89pkdtkhw-lab | `api/app/main.py`, `api/app/ai/`, `data/`, `docs/`, `README.md`, `.github/`, `tools/`, `AGENTS.md` |

Die Schnittstelle zwischen Oberfläche und Backend (`api/app/main.py`, `api/app/modelle.py`, `web/lib/api.ts`) legt der Kickoff einmal fest; danach ändert sie nur, wer es vorher mit `@all` auf dem Board ankündigt.

## 4. Ablauf eines Auftrags

**Graphify ist vor jeder Aufgabe Pflicht:** Nach dem Setup (`python tools/setup.py`) den lokalen Codegraph aktualisieren (`graphify update .` bei vorhandenem Graph; initial `/graphify` mit ausdrücklicher Vorgabe „nur Code, keine semantische Extraktion“). Für einen garantiert reinen AST-Lauf `graphify extract . --code-only` verwenden. Zuerst mit `graphify query`, `graphify explain` oder `graphify path` den betroffenen Code und seine Abhängigkeiten erschließen; danach gezielt Dateien lesen/suchen. `.graphifyignore` gilt immer: `data/datensatz/` und `data/testfaelle/` dürfen nie indexiert werden. Keine PDF-/Dokument-/Medienanalyse und kein Cloud-Upload. Fehlt Graphify oder scheitert die Aktualisierung, Setup reparieren und den Blocker melden, bevor die Implementierung startet. Anleitung: [Graphify](docs/agenten.md#graphify-verpflichtender-codekontext).

1. Ein Auftrag ist ein GitHub-Issue mit verantwortlicher Person, Bereich und Abnahmetest. Fehlt etwas, frag im Issue statt zu raten.
2. Übernimm ihn sichtbar: `python tools/aufgabe.py <Nr> --uebernehmen` legt Branch `<Nr>-<kurzname>` und einen eigenen Worktree vom frischen `main` an, weist dich zu, setzt das Label `in-arbeit` und postet auf dem Board. Ein Issue mit `in-arbeit` oder fremdem Assignee fasst niemand anderes an. Arbeite nie im Checkout eines anderen Agenten.
3. Kleine Commits. Stage nur deine eigenen Dateien, nie `git add -A`.
4. Prüfe, bevor du „fertig“ sagst: `python -m unittest discover -s tests -v`, `cd api && python -m pytest -q`, das Abnahmebeispiel aus dem Issue und, bei Oberflächen, ein Blick im Browser. Schreib dazu, was du ausgeführt hast.
5. `git fetch` und `git rebase origin/main`, dann pushen und einen Pull Request mit `Closes #<Nr>` öffnen. Nie einen geteilten Branch force-pushen.
6. Unter FirstMate (`direct-PR +yolo`) öffnet die Crew den fertigen Pull Request; der First Mate mergt nach lokal erfolgreichen Tests und grünen Checks. Ohne FirstMate mergst du selbst: `gh pr checks --watch`, danach `gh pr merge --squash --delete-branch`.
7. Ändert dein Merge etwas, worauf andere bauen (API-Route, Datenmodell einer LV-Position, Finding-Format, Umgebungsvariable), poste es mit `@all` auf dem Board.
8. Musst du mittendrin aufhören (Kontingent, Kontext voll, Wechsel Claude ↔ Codex), committe den Zwischenstand auf deinen Branch und schreib mit `handoff` einen Übergabe-Kommentar ins Issue. So kann jeder andere Agent nahtlos weitermachen.
9. Räum deinen Worktree auf: `git worktree remove ../<repo>-<Nr>` (unter FirstMate macht das der First Mate).

## 5. Grenzen

- Nie direkt auf `main` oder `demo` pushen; gemergt wird über Pull Requests. `demo` ist der Stand der Jury-URL und wird nur vom Workflow `Demo-Stand` nach grünen Tests nachgezogen. Steht auf dem Board „main ist rot“, merged niemand weiter, bis der Verursacher fixt oder revertet. Der Push-Check in `tools/hooks/pre-push` erzwingt das und lässt die Tests laufen.
- Keine Schlüssel in Code, Commits, Logs, Issues, PRs oder Board-Posts. Schlüssel liegen in `.env.local` oder Umgebungsvariablen; die Namen stehen in `.env.example`. Lies oder zeige keine `.env`-Dateien.
- Modell-APIs nur vom Server aus aufrufen (`api/app/ai/llm.py`), nie aus dem Browser-Code.
- Tests und Standardläufe bleiben offline und kostenlos (Mock). Live-APIs nur, wenn das Issue es verlangt.
- **Der Datensatz ist vertraulich** (Vorgabe des Partners): nur in diesem privaten Repo, nie in öffentliche Repos, Gists, Pastebins oder fremde Dienste außer dem konfigurierten LLM-Anbieter.
- Echte LVs aus dem Datensatz bleiben in `data/datensatz/` und werden nicht verändert. Testfälle mit eingebauten Fehlern liegen getrennt in `data/testfaelle/`.
- Jedes Finding nennt seine Quelle: Positionsnummer (OZ) und ob es aus einer festen Regel oder vom Modell stammt. Keine erfundenen Positionen, Preise oder Normen.
- Neue Abhängigkeiten nur mit Eintrag im Issue, in `api/requirements.txt` bzw. `web/package.json` und Startbefehl in der README.

## 6. Autonomie und Cloud-Agenten

Ein Issue mit dem Label `agent-bereit` ist vollständig beschrieben; ein Agent setzt es ohne Rückfrage bis zum Merge um, solange er in seinem Bereich bleibt. Das Label `claude` startet Claude in GitHub Actions, `@codex implement this` startet Codex in der Cloud. Für Skills wie `to-tickets` ist der Issue-Tracker GitHub Issues in diesem Repo, und das Label für agentenfertige Tickets heißt `agent-bereit`.

## 7. Skills

| Wann | Skill |
| --- | --- |
| Start der Produktarbeit (Plan, Schnittstelle, Issues) | `kickoff` |
| Plan ohne Lücken | `grill-me` |
| Plan in parallele Issues schneiden | `auftrag-schneiden` (unser Issue-Format), Schnittregeln aus `to-tickets` |
| Idee oder Oberfläche schnell prüfen | `prototype` |
| Neue Logik (Parser, Prüfregel) | `tdd` |
| Hartnäckiger Fehler | `diagnosing-bugs` |
| Kontext wird voll | `handoff` |
| Optionales Review über Kreuz | `pr-review` |
| Vorher/Nachher-Beleg (manuelle Prüfung vs. Tool) | `demo-vergleich` |
| Pitch | `pitch-probe` |

## 8. Welches Modell für welche Aufgabe

| Aufgabe | Claude | Codex |
| --- | --- | --- |
| Kleine, klar beschriebene Änderung in ein bis zwei Dateien | Haiku | schnelles Modell |
| Oberfläche, die in der Demo zu sehen ist | Opus | – |
| Schwer oder unklar: Architektur, GAEB-Parser, Prüflogik-Design, Planung | Opus | stärkstes Modell |
| Implementierung gegen fertige Spezifikation oder Fehler mit bekannter Ursache (`modell:bugfix`) | Sonnet | Standardmodell |
| Recherche: GAEB-Spezifikation, VOB, Dokus | Sonnet | Standardmodell |
| Doku, Pitch, Texte nach geklärtem Plan (`modell:text`) | Haiku | schnelles Modell |

Jedes Issue trägt genau ein Label `modell:klein`, `modell:ui`, `modell:schwer`, `modell:bugfix`, `modell:recherche` oder `modell:text`; ohne Label gilt Sonnet bzw. das Codex-Standardmodell. Die genauen Modellnamen stehen in `tools/modelle.json`. `tools/aufgabe.py` zeigt den passenden Startbefehl, z. B. `claude --model haiku`. Ist ein Kontingent fast leer, wechsle für neue Aufgaben zum Anbieter mit Reserve (Claude ↔ Codex).

## 9. Befehle

| Zweck | Befehl |
| --- | --- |
| Tests, Pflicht vor jedem Push | `python -m unittest discover -s tests -v` |
| Produkt lokal starten (Oberfläche :3000, Backend :8000) | `python tools/dev.py` |
| Produkt-Tests | `cd api && python -m pytest -q` und `cd web && npm run build` |
| Lagebild aller Crews / nächstes freies Issue | `python tools/stand.py` / `python tools/stand.py --naechstes` |
| Rechner prüfen und Push-Check aktivieren | `python tools/setup.py` |
| Issue als eigenen Worktree beginnen | `python tools/aufgabe.py <Nr> --uebernehmen` |
| Skills für Claude Code spiegeln | `python tools/agents_sync.py` |

Auf macOS heißt Python oft `python3`. Die Team-Werkzeuge in `tools/` brauchen nur die Python-Standardbibliothek.

## Code Review Rules

Reviews sind freiwillig und laufen parallel zum Selbst-Merge, z. B. `@codex review` oder `pr-review`. Für jedes Review gilt:

- Prüfe zuerst das Abnahmebeispiel aus dem verlinkten Issue und ob die Tests wirklich gelaufen sind.
- Melde unangekündigte Schnittstellenänderungen, neue Abhängigkeiten und Schlüssel im Code.
- Fehlerfälle müssen für Nutzer sichtbar und verständlich bleiben; die Demo muss weiter starten.
- Nenne nur echte Probleme, das wichtigste zuerst, jeweils mit Datei, Zeile und einem reproduzierbaren Beispiel.
