# LV Review Assistant · TUM.ai Construction Hackathon 2026

**Challenge A: AI Estimation and Bid Assistant for Bills of Quantities.** An estimator uploads a bill of quantities (GAEB, Excel or PDF) and receives a review report in minutes: arithmetic and formatting errors, unclear or contradictory items, risks and Nachtrag potential, each with an item number and explanation.

- Case, goal and core flow: [docs/case.md](docs/case.md)
- LV, GAEB, estimation terminology and team notes: [docs/domaene.md](docs/domaene.md)
- Working together on five laptops: [docs/teamstart.md](docs/teamstart.md)
- Rules for people and agents: [AGENTS.md](AGENTS.md)

**Submission: Sunday, 22 November 2026, 12:00 Munich time.** Internal target 11:30, feature freeze 09:00.

## Quick start

Install Git, Python 3.11+, Node 20+ and the GitHub CLI, accept the invitation, then:

```sh
gh auth login
git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git
cd tum-ai-boq-assistant
python tools/setup.py --kommentar 2   # Check the machine, enable the push check, report in issue #2
# No key needed: LV review and the starter route run with the offline mock
python tools/dev.py --install         # UI http://localhost:3000, backend http://localhost:8000/health
```

On macOS, use `python3` instead of `python`.

## Structure

| Folder | Contents |
| --- | --- |
| `web/` | Next.js UI: upload, item table, review report |
| `api/` | FastAPI backend; `api/app/ai/llm.py` wraps Anthropic, OpenAI, Azure, Gemini and an offline mock |
| `data/datensatz/` | Challenge example LVs (unchanged) |
| `data/testfaelle/` | LVs with deliberately introduced errors for evaluation |
| `docs/` | Case, domain, team and agent guides |
| `tools/` | Board, task worktrees, setup check, dashboard, FirstMate |
| `.agents/skills/` | Skills for Claude Code and Codex (`kickoff`, `grill-me`, `tdd`, `pitch-probe` …) |

## Where to work

| Place | Purpose |
| --- | --- |
| [Team board (issue #1)](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues/1) | Communication between all people and agents: `tools/board post "[Name · Agent] …"` |
| [Issues](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues) | Tasks with an owner, scope and acceptance test; `agent-bereit` means an agent can start immediately |
| [Working with coding agents](docs/agenten.md) | Claude Code, Codex, autonomy levels, cloud agents |
| [FirstMate](docs/firstmate.md) | One person manages an entire agent crew |
| [Access](docs/zugaenge.md) | API keys for agents and the product |

Every change goes through a separate branch and pull request. Under FirstMate, only the First Mate merges after green checks; otherwise the author merges. CI runs `python -m unittest discover -s tests -v` for team tooling, plus `cd api && python -m pytest -q` and the web build. Only green revisions of `main` reach the `demo` branch.

## Check the kickoff interface locally

The kickoff provides the contract and domain placeholders. Synthetic JSON already imports; real GAEB/Excel/PDF parsers, domain rules and the report UI follow in their assigned issues. The five deliberately introduced errors are acceptance targets, not findings detected by the kickoff placeholders. Contract and module ownership: [docs/schnittstelle.md](docs/schnittstelle.md).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt -r api/requirements-dev.txt
(cd web && npm ci --no-audit --no-fund)
(cd api && ../.venv/bin/python -m pytest -q)
(cd web && npm run build)
python3 -m unittest discover -s tests -v
python3 tools/dev.py
```

For local PDF document classification and page-addressable text extraction, `pypdf` is included in `api/requirements.txt`; install with `.venv/bin/python -m pip install -r api/requirements.txt`. This does not implement PDF table imports. Typed JSON export usage and coverage: [import schemas](docs/import-schemas.md).

On Windows use `.venv/Scripts/python.exe`. `python-multipart` in `api/requirements.txt` enables multipart/form-data uploads; this dependency is documented in the kickoff issue. Do not commit `.venv/`, `node_modules/` or build artifacts.

```sh
curl -F 'datei=@data/beispiel_lv.json' http://localhost:8000/api/lv/import
curl -H 'Content-Type: application/json' --data-binary @data/beispiel_lv.json http://localhost:8000/api/lv/pruefen
```

At kickoff, the existing home page remains a mock starter until the UI issue; `/api/beispiele` supplies complete synthetic LV structures for the new UI. Clearly mark model mocks and missing euro values. Partner files remain unchanged in `data/datensatz/`.

Graphify is mandatory before agent tasks (developer tool, Python 3.11+). `python tools/setup.py` installs `graphifyy` with uv or pipx and registers the skill. Manual setup: `uv tool install graphifyy`, `graphify install`, then `graphify extract . --code-only`. Details and confidential exclusions: [Graphify guide](docs/agenten.md#graphify-mandatory-code-context).
