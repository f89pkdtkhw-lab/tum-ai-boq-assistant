# LV-Prüfassistent · TUM.ai Construction Hackathon 2026

**Challenge A: AI Estimation and Bid Assistant for Bills of Quantities.** Ein Kalkulator lädt ein Leistungsverzeichnis (GAEB, Excel oder PDF) hoch und bekommt in Minuten einen Prüfbericht: Rechen- und Formfehler, unklare oder widersprüchliche Positionen, Risiken und Nachtragspotenzial, jeweils mit Positionsnummer und Begründung.

- Case, Ziel und Kernablauf: [docs/case.md](docs/case.md)
- Fachwissen LV, GAEB, Kalkulation und unsere Notizen: [docs/domaene.md](docs/domaene.md)
- Wie fünf Laptops zusammenarbeiten: [docs/teamstart.md](docs/teamstart.md)
- Regeln für Menschen und Agenten: [AGENTS.md](AGENTS.md)

**Abgabe: Sonntag, 22.11.2026, 12:00.** Internes Ziel 11:30, Funktionsstopp 09:00.

## Schnellstart

Git, Python 3.11+, Node 20+ und die GitHub CLI installieren, Einladung annehmen, dann:

```sh
gh auth login
git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git
cd tum-ai-boq-assistant
python tools/setup.py --kommentar 2   # Rechner prüfen, Push-Check aktivieren, Ergebnis in Issue #2
# Kein Schlüssel nötig: LV-Prüfung und Starterroute laufen im Offline-Mock
python tools/dev.py --install         # Oberfläche http://localhost:3000, Backend http://localhost:8000/health
```

Auf macOS `python3` statt `python`.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `web/` | Next.js-Oberfläche: Upload, Positionstabelle, Prüfbericht |
| `api/` | FastAPI-Backend; `api/app/ai/llm.py` kapselt Anthropic, OpenAI, Azure, Gemini und einen Offline-Mock |
| `data/datensatz/` | Beispiel-LVs der Challenge (unverändert) |
| `data/testfaelle/` | LVs mit absichtlich eingebauten Fehlern für die Messung |
| `docs/` | Case, Domäne, Team- und Agenten-Anleitungen |
| `tools/` | Board, Aufgaben-Worktrees, Setup-Check, Dashboard, FirstMate |
| `.agents/skills/` | Skills für Claude Code und Codex (`kickoff`, `grill-me`, `tdd`, `pitch-probe` …) |

## Wo ihr arbeitet

| Ort | Wofür |
| --- | --- |
| [Team-Board (Issue #1)](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues/1) | Funk zwischen allen Menschen und Agenten: `tools/board post "[Name · Agent] …"` |
| [Issues](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues) | Aufträge mit verantwortlicher Person, Bereich und Abnahmetest; `agent-bereit` = ein Agent kann sofort loslegen |
| [Mit Coding-Agenten arbeiten](docs/agenten.md) | Claude Code, Codex, Autonomie-Stufen, Cloud-Agenten |
| [FirstMate](docs/firstmate.md) | Eine Person führt eine ganze Agenten-Crew |
| [Zugänge](docs/zugaenge.md) | API-Schlüssel für Agenten und Produkt |

Jede Änderung läuft über einen eigenen Branch und Pull Request; unter FirstMate mergt ausschließlich der First Mate nach grünen Checks (sonst der Autor selbst). Die CI nutzt den Testbefehl `python -m unittest discover -s tests -v` für das Team-Setup, dazu `cd api && python -m pytest -q` und den Web-Build. Nur grüne Stände von `main` wandern auf den Branch `demo`.


## Kickoff-Schnittstelle lokal prüfen

Der Kickoff liefert den Vertrag und Fachplatzhalter. Das synthetische JSON importiert bereits; echte GAEB-/Excel-/PDF-Parser, Fachregeln und Berichtsoberfläche folgen in den zugewiesenen Issues. Die fünf eingebauten Fehler sind Abnahmeziele, noch keine erkannten Befunde. Vertrag und Modulbesitz: [docs/schnittstelle.md](docs/schnittstelle.md).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt -r api/requirements-dev.txt
(cd web && npm ci --no-audit --no-fund)
(cd api && ../.venv/bin/python -m pytest -q)
(cd web && npm run build)
python3 -m unittest discover -s tests -v
python3 tools/dev.py
```

Unter Windows `.venv/Scripts/python.exe` verwenden. `python-multipart` aus `api/requirements.txt` ermöglicht Datei-Uploads mit multipart/form-data; neue Abhängigkeit im Kickoff-Issue dokumentiert. `.venv/`, `node_modules/` und Buildprodukte werden nicht committet.

```sh
curl -F 'datei=@data/beispiel_lv.json' http://localhost:8000/api/lv/import
curl -H 'Content-Type: application/json' --data-binary @data/beispiel_lv.json http://localhost:8000/api/lv/pruefen
```

Die vorhandene Startseite bleibt bis zum UI-Issue eine Mock-Starterseite; `/api/beispiele` liefert die echten synthetischen LV-Strukturen für die neue Oberfläche. Modell-Mock und fehlende Euro-Werte sind sichtbar zu kennzeichnen. Partnerdateien bleiben unverändert in `data/datensatz/`.


Graphify ist vor Agentenaufgaben Pflicht (Entwicklerwerkzeug, Python 3.11+): `python tools/setup.py` installiert `graphifyy` mit uv oder pipx und registriert den Skill. Manueller Start: `uv tool install graphifyy`, `graphify install`, dann `graphify extract . --code-only`. Details und vertrauliche Ausschlüsse: [Graphify-Anleitung](docs/agenten.md#graphify-verpflichtender-codekontext).
