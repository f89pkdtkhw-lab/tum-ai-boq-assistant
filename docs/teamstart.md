# Team setup: five laptops, one repository

Five people work in [one private repository](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant): two Macs and three Windows laptops. All shared work goes through GitHub, never USB drives or copied folders. Issues are tasks; the [team board (issue #1)](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues/1) connects people and agents; pull requests bring code to `main`.

## Five laptops working together without collisions

1. **Everyone clones the repository** and works only on their own branches. Nobody pushes to `main`; the push check blocks it.
2. **One issue = one branch = one separate folder (worktree).** `python tools/aufgabe.py <number> --uebernehmen` creates it. Multiple agents can then run on one laptop.
3. **Separate folders by focus area** (table in [AGENTS.md](../AGENTS.md#3-ownership)): parsers, review engine, risk, UI, integration. This keeps merge conflicts rare.
4. **Small PRs, quick merges.** Prefer ten 30-minute PRs over one five-hour PR. After merges, update with `git fetch && git rebase origin/main`.
5. **Interface first.** Kickoff defines data models, API routes and example data. UI and backend can then progress in parallel.
6. **One presentation laptop** (lead) runs the demo from `main` every two hours.

## Once per person (15 minutes)

Requirements: Git, Python 3.11+, Node 20+, [GitHub CLI](https://cli.github.com).

| | macOS | Windows |
| --- | --- | --- |
| Tools | `brew install git gh node python@3.12` | `winget install Git.Git GitHub.cli OpenJS.NodeJS.LTS Python.Python.3.12` |
| Terminal | Terminal or Ghostty | PowerShell or Git Bash (Windows Terminal) |
| Python command | `python3` | `python` |
| Board command | `tools/board …` | `python tools/board.py …` (PowerShell) or `tools/board …` (Git Bash) |

```sh
gh auth login                                   # Accept the GitHub invitation first
git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git
cd tum-ai-boq-assistant
python tools/setup.py --kommentar 2             # Check everything, enable push check, report in issue #2
python tools/dev.py --install                   # Product: UI :3000, backend :8000
```

Then sign in to your coding agent (one per person is enough; using both also works):

- **Claude Code:** start `claude` in the repository, then `/login`. Reads `CLAUDE.md` → `AGENTS.md`; skills via `/kickoff`, `/grill-me`, etc.
- **Codex:** `npm install -g @openai/codex`, then `codex` and sign in with your ChatGPT account. Reads `AGENTS.md` directly; skills via `$kickoff`, `$grill-me`, etc. Codex does not receive board posts automatically: start each task with “Read `tools/board unread`.”
- **Codex Cloud (optional):** chatgpt.com/codex → connect GitHub → authorize the repository. Then `@codex implement this` in an issue starts a cloud agent; `@codex review` reviews a PR.
- To manage several agents at once (Mac or Windows with WSL), see [FirstMate](firstmate.md).

Install the GitHub phone app, enable mention notifications and subscribe to issue #1.

## A task in one minute

```sh
python tools/aufgabe.py 7 --uebernehmen --werkzeug "Codex"
```

Open the folder in your agent and say: “Read .auftrag.md and implement the task.” Done means tests green, PR opened and merged after green checks; important changes announced with `@all` on the board. Under FirstMate, the First Mate merges.

## Schedule until Sunday 12:00

| When | What |
| --- | --- |
| Friday evening | Setup on all five laptops, inspect dataset, `kickoff` with the case: interface + issues |
| Friday night | Parser for one real LV, first rules, upload page; finish with upload → findings |
| Saturday morning | End-to-end flow on presentation laptop; LLM checks, risk scoring, report |
| Saturday afternoon | Seeded-error test cases, manual vs. tool comparison (`demo-vergleich`), UI polish |
| Saturday evening | Optional EP suggestions / what-if; pitch story (`pitch-probe`) |
| Sunday 09:00 | **Feature freeze**, bug fixes only |
| Sunday 10:00 | Record fallback demo video, rehearse pitch |
| Sunday 11:30 | Internal submission target |
| **Sunday 12:00** | **Submission** |
