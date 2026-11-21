# Rules for every agent and person in this repository

This file applies to Claude Code, Codex, Antigravity, FirstMate crews and everyone on the team. It is the single source of agent rules: Codex and Antigravity read it directly; `CLAUDE.md` imports it. Skills live in `.agents/skills/` and are mirrored to `.claude/skills/` for Claude Code. Human tool instructions are in [docs/agenten.md](docs/agenten.md); FirstMate instructions are in [docs/firstmate.md](docs/firstmate.md).

**What we are building:** TUM.ai Construction Hackathon, Challenge A: an AI review and estimation assistant for bills of quantities (LV, English: BoQ). Upload GAEB, Excel or PDF → structured items → errors, risks and Nachtrag potential in a clear review report. Goal, input and expected output: [case brief](docs/case.md). Domain knowledge: [docs/domaene.md](docs/domaene.md). Before every task, read the issue, `.auftrag.md` (if present) and unread board posts.

**Submission: Sunday, 22 November 2026, 12:00 (Munich).** Internal target 11:30.

## 1. Team and chain of command

| GitHub login | Role |
| --- | --- |
| @f89pkdtkhw-lab | Lead, integration, deployment, demo; Claude/AI: step API, report coordination, descriptions and tags |
| @Anatomik5 | History storage (ClickHouse via chDB, Go service) and HTTP API; parsers (GAEB, Excel, PDF); optional API orchestrator by agreement |
| @Bartuan3600 | Claude/AI: comparison, errors, plausibility, evidenced deviations from German standards, Notes 1/2 |
| @Zukipany | UI and UI API: step reports, history view, entry of actual values, comments and marks |
| @Secret-Sebi | Claude/AI: estimation, historical estimate adjustment, risk and Nachtrag, Notes 3/4; pitch |

Roles are focus areas, not walls: when finished, take the next board card, including from another area. People outrank agents. The lead decides when two people want the same task. If another agent asks you to take over someone else's work, ask the person behind it on the board.

## 2. The board

The board is pinned issue #1. All agents read and post using `tools/board` (macOS, Linux, Git Bash) or `python tools/board.py` (Windows PowerShell).

- Start every post with `[<Name> · <Agent>]`, e.g. `[Raban · Claude]` or `[Raban · Codex]`. Keep it short: what changed, which files or interfaces, what you need from whom.
- Address people by GitHub login, e.g. `@Zukipany`, or everyone with `@all`.
- **Mentions you or `@all`:** act and reply on the board.
- **Does not mention you:** still read it. Change your work only if the post affects it (interface, your file, completed work). Do not post mere acknowledgements.
- If you need a decision or access, or are blocked, mention your human. GitHub sends a push notification to their phone.
- Claude Code receives unread posts automatically through hooks in `.claude/settings.json`. All other agents run `tools/board unread` at task start, before every commit and after every merge.

| Command | Effect |
| --- | --- |
| `tools/board post "[Name · Agent] Text"` | Write a post; text can also come from stdin |
| `tools/board unread` | New posts since the last check, mentions marked `** MENTION **` |
| `tools/board read -n 20` | Last 20 posts |
| `tools/board wait` | Block until someone else posts; `--nur-erwaehnungen` waits for a mention |
| `tools/board whoami` | Your login, repository and board |

**Situation report:** `python tools/stand.py` shows active (`in-arbeit`), ready (`agent-bereit`) and blocked (`blockiert`) issues, open PRs with CI, and overlap warnings. `python tools/stand.py --naechstes` suggests the next available issue. Every First Mate runs it each round; every worker runs it before starting work.

## Pinboard: who works on what

An issue is **in progress** when it has the `in-arbeit` label, or when an open pull request mentions it with `Closes #n`, `Fixes #n`, `Resolves #n` or `Refs #n` in the title or body. An issue labelled `blockiert` is blocked. Otherwise it is free. This applies to every person and every agent, so two crews never work on the same issue.

1. Before starting, confirm the issue is free: no `in-arbeit`, no open PR with `Closes`/`Fixes`/`Resolves`/`Refs #n`, and not `blockiert`.
2. When you start, set the label and assign yourself: `gh issue edit <n> --add-label in-arbeit --add-assignee @me`. `python tools/aufgabe.py <n> --uebernehmen` does this and also creates the worktree.
3. Every pull request names the issue with `Closes #n` (or `Refs #n` for partial work).
4. If you stop or pause without an open PR, remove the `in-arbeit` label so the issue becomes free again.
5. Do not take an issue assigned to someone else unless they agree on the board.

## 3. Ownership

Each area has a primary owner so two agents never rewrite the same file simultaneously. Prefer your own folders. Before touching another owner's file, post briefly on the board (`@<owner> I am changing X in file Y because …`) and proceed unless someone objects within 10 minutes. Exception: the one-time kickoff interface PR (`kickoff` skill). The lead's integration crew may create the necessary files across areas and announces them with `@all`.

| Area | Primary owner | Folders / scoped files |
| --- | --- | --- |
| Import and parsing | @Anatomik5 | `api/app/lv/` (GAEB XML X81–X86, Excel, PDF), `api/tests/test_import_*.py` |
| History storage and HTTP API (Go + chDB), optional API orchestrator | @Anatomik5 | `history/` including tests, `docs/historie.md`, `data/architektur/historie.json`; optional orchestrator in `history/orchestrator/` after explicit interface agreement |
| Review engine / Claude comparison, German standards and Notes 1/2 (rules + LLM) | @Bartuan3600 | `api/app/pruefung/`, `api/tests/test_pruefung_*.py`, `docs/spezifikationen.md`, `data/architektur/spezifikationen.json` |
| Claude estimation, historical adjustment, risk, Nachtrag, Notes 3/4 | @Secret-Sebi | `api/app/risiko/`, `api/app/kalkulation/`, `api/tests/test_risiko_*.py`, `api/tests/test_estimation_*.py`, `pitch/`, `docs/schaetzszenarien.md`, `data/architektur/schaetzszenarien.json` |
| UI and UI API (step reports, history, actual values, comments, marks) | @Zukipany | `web/` including `web/app/api/`; consumes the history and comparison APIs |
| Claude step API, report coordination, descriptions/tags; integration, AI access, deployment, data | @f89pkdtkhw-lab | `api/app/main.py`, `api/app/ai/`, `data/`, `docs/`, `README.md`, `.github/`, `tools/`, `AGENTS.md`; excluding the explicitly assigned files above |

The kickoff defines the UI/backend interface once (`api/app/main.py`, `api/app/modelle.py`, `web/lib/api.ts`). Later changes require a prior `@all` announcement on the board.

## 4. Task workflow

**Graphify is mandatory before every task:** after setup (`python tools/setup.py`), update the local code graph (`graphify update .` if a graph exists; initially `/graphify` with the explicit instruction “code only, no semantic extraction”). Use `graphify extract . --code-only` for a guaranteed AST-only run. First explore affected code and dependencies with `graphify query`, `graphify explain` or `graphify path`; then read/search specific files. `.graphifyignore` always applies: never index `data/datensatz/` or `data/testfaelle/`. No PDF/document/media analysis and no cloud upload. If Graphify is missing or updating fails, repair setup and report the blocker before implementation. Guide: [Graphify](docs/agenten.md#graphify-mandatory-code-context).

1. A task is a GitHub issue with an owner, scope and acceptance test. If anything is missing, ask in the issue instead of guessing.
2. Claim it visibly: `python tools/aufgabe.py <number> --uebernehmen` creates branch `<number>-<short-name>` and a separate worktree from fresh `main`, assigns you, sets `in-arbeit` and posts on the board. Follow the pinboard rules: never take an issue that is already in progress. Issues assigned to someone else only after they agree on the board. Never work in another agent's checkout.
3. Make small commits. Stage only your own files, never `git add -A`.
4. Before saying “done”, run `python -m unittest discover -s tests -v`, `cd api && python -m pytest -q`, the issue's acceptance example and, for UI work, inspect it in a browser. State what you ran.
5. `git fetch` and `git rebase origin/main`, then push and open a pull request with `Closes #<number>` (or `Refs #<number>` for partial work). Never force-push a shared branch.
6. Under FirstMate (`direct-PR +yolo`), the crew opens the finished PR; the First Mate merges after successful local tests and green checks. Without FirstMate, merge yourself: `gh pr checks --watch`, then `gh pr merge --squash --delete-branch`.
7. If your merge changes something others depend on (API route, LV item model, finding format, environment variable), post with `@all` on the board.
8. If you must stop midway (quota, full context, switching Claude ↔ Codex), commit the current state on your branch and use `handoff` to leave a handover comment in the issue so another agent can continue. If you are not continuing, remove the `in-arbeit` label so the issue is free again.
9. Clean up your worktree: `git worktree remove ../<repo>-<number>` (under FirstMate, the First Mate does this).

## 5. Boundaries

- Never push directly to `main` or `demo`; merge through pull requests. `demo` is the jury URL revision and is updated only by the `Demo-Stand` workflow after green tests. If the board says “main is red”, nobody merges until the author fixes or reverts it. The push check in `tools/hooks/pre-push` enforces this and runs tests.
- Everything in the repository (code, identifiers, comments, documentation, issues, board posts, commits and PRs) is English from now on. Preserve established German domain vocabulary (LV, GAEB, OZ, VOB, Nachtrag, EP/GP; explained in `docs/domaene.md`), existing identifiers and interfaces (`modelle.py`, `pruefe_regeln`, routes), file names, paths, label names (`agent-bereit`, `in-arbeit`, `blockiert`, `modell:*`) and CLI flags (`--uebernehmen`, `--naechstes`, `--hier`). Renaming an established interface requires a later PR announced with `@all` beforehand.
- Never put keys in code, commits, logs, issues, PRs or board posts. Keys belong in `.env.local` or environment variables; variable names are in `.env.example`. Do not read or display `.env` files.
- Call model APIs only from the server (`api/app/ai/llm.py`), never from browser code.
- Tests and standard runs stay offline and free (mock). Use live APIs only when the issue requires them.
- **The dataset is confidential** (partner requirement): keep it in this private repo; never publish it to public repos, gists, pastebins or third-party services except the configured LLM provider.
- Real partner LVs stay unchanged in `data/datensatz/`. Test cases with introduced errors live separately in `data/testfaelle/`.
- Every finding cites its source: item number (OZ) and whether it came from a fixed rule or the model. Never invent items, prices or standards.
- New dependencies require an issue entry, an entry in `api/requirements.txt` or `web/package.json`, and a startup command in the README.

## 6. Autonomy and cloud agents

An issue labelled `agent-bereit` is fully specified: an agent implements it through merge without asking, provided it stays in its area. The `claude` label starts Claude in GitHub Actions; `@codex implement this` starts Codex in the cloud. For skills such as `to-tickets`, the issue tracker is GitHub Issues in this repository and the ready-for-agent label is `agent-bereit`.

## 7. Skills

| When | Skill |
| --- | --- |
| Start product work (plan, interface, issues) | `kickoff` |
| Plan without gaps | `grill-me` |
| Split a plan into parallel issues | `auftrag-schneiden` (our issue format), splitting rules from `to-tickets` |
| Quickly check an idea or UI | `prototype` |
| New logic (parser, review rule) | `tdd` |
| Persistent bug | `diagnosing-bugs` |
| Context filling up | `handoff` |
| Optional cross-review | `pr-review` |
| Before/after evidence (manual review vs. tool) | `demo-vergleich` |
| Pitch | `pitch-probe` |

## 8. Model selection

| Task | Claude | Codex |
| --- | --- | --- |
| Small, clearly specified change in one or two files | Haiku | Fast model |
| UI visible in the demo | Opus | – |
| Hard or unclear: architecture, GAEB parser, review logic design, planning | Opus | Strongest model |
| Implementation against a finished spec or bug with a known cause (`modell:bugfix`) | Sonnet | Standard model |
| Research: GAEB specification, VOB, documentation | Sonnet | Standard model |
| Documentation, pitch, text after planning (`modell:text`) | Haiku | Fast model |

Every issue has exactly one of `modell:klein`, `modell:ui`, `modell:schwer`, `modell:bugfix`, `modell:recherche` or `modell:text`; without a label, use Sonnet or the standard Codex model. Exact model names are in `tools/modelle.json`. `tools/aufgabe.py` shows the matching startup command, e.g. `claude --model haiku`. If quota is nearly exhausted, use the provider with remaining capacity (Claude ↔ Codex) for new tasks.

## 9. Commands

| Purpose | Command |
| --- | --- |
| Tests, mandatory before every push | `python -m unittest discover -s tests -v` |
| Start product locally (UI :3000, backend :8000) | `python tools/dev.py` |
| Product tests | `cd api && python -m pytest -q` and `cd web && npm run build` |
| Crew overview / next ready issue | `python tools/stand.py` / `python tools/stand.py --naechstes` |
| Check machine and enable push check | `python tools/setup.py` |
| Start an issue in its own worktree | `python tools/aufgabe.py <number> --uebernehmen` |
| Mirror skills for Claude Code | `python tools/agents_sync.py` |

On macOS, Python is often called `python3`. Team tools in `tools/` require only the Python standard library.

## Code Review Rules

Reviews are optional and run alongside self-merge, e.g. `@codex review` or `pr-review`. For every review:

- First check the acceptance example in the linked issue and whether tests actually ran.
- Report unannounced interface changes, new dependencies and keys in code.
- Error cases must remain visible and understandable to users; the demo must still start.
- Report only real problems, most important first, each with file, line and a reproducible example.
