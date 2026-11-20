# Working with coding agents

Everyone uses their own account and tool: Claude Code, Codex, Antigravity, or a First Mate managing a crew ([FirstMate](firstmate.md)). GitHub connects everything: issues are tasks, pinned issue #1 is the team board for handovers, and authors merge pull requests once checks are green. All tools read the same rules from [AGENTS.md](../AGENTS.md). Under FirstMate, the First Mate merges.

## Once per person

1. Accept the GitHub invitation, install the [GitHub CLI](https://cli.github.com) and run `gh auth login`.
2. Clone the repository and run `python tools/setup.py --kommentar 2`. This checks Python, Git, GitHub access, agents and tests, enables the push check, and reports in issue #2.
3. Sign in to your tool: Claude Code with a Claude account, Codex with a ChatGPT account, Antigravity or Gemini with a Google account.
4. Install the GitHub phone app, enable mention notifications and subscribe to issue #1.
5. Install a dictation app ([Handy](https://github.com/cjpais/Handy), free, or Wispr Flow). Speaking is faster than typing, especially late at night.
6. Mac users also set up FirstMate ([guide](firstmate.md)).

## What each tool reads

| Tool | Rules | Skills | Invoke a skill | Board |
| --- | --- | --- | --- | --- |
| Claude Code | `CLAUDE.md`, importing `AGENTS.md` | `.claude/skills/` (generated copy) | `/grill-me` | Automatically through hooks |
| Codex | `AGENTS.md` | `.agents/skills/` | `$grill-me` | `tools/board unread` as required by the rules |
| Antigravity | `AGENTS.md` | `.agents/skills/` | Mention the skill name in chat | `tools/board unread` as required by the rules |
| FirstMate | Own rules plus project `AGENTS.md` | Same as crew tool | – | First Mate monitors it |

Change rules only in `AGENTS.md`, skills only in `.agents/skills/`, then run `python tools/agents_sync.py`.

| Skill | Purpose |
| --- | --- |
| `kickoff` | From the case: dataset inspection, interface, owners, issues, start signal |
| `grill-me` | Question a plan until no gaps remain |
| `auftrag-schneiden` | Split a plan into parallel issues with separate scopes |
| `to-tickets` | Vertical-slice rules used by `auftrag-schneiden` |
| `prototype` | Throwaway version to test an idea or UI |
| `tdd` | First a failing test, then the smallest implementation |
| `diagnosing-bugs` | Diagnosis loop for persistent bugs |
| `handoff` | Handover note when context fills up |
| `pr-review` | Optional cross-review |
| `demo-vergleich` | Compare existing workflow with prototype on the same cases |
| `pitch-probe` | English three-minute pitch and Q&A |

`grill-me`, `grilling`, `to-tickets`, `prototype`, `tdd`, `diagnosing-bugs` and `handoff` come from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT license included with each).

## Start a task in one minute

```sh
python tools/aufgabe.py 7 --uebernehmen --werkzeug "Codex"
```

The script reads the issue, creates a separate folder (Git worktree) beside the repository with branch `7-<short-name>` from the correct target branch, writes `.auftrag.md`, assigns you, comments on the claim and posts on the board. Open that folder in your tool and say: “Read .auftrag.md and implement the task.” Once done and checks are green, the agent merges and removes the worktree; under FirstMate, the First Mate handles those steps.

## The board

Agents working for different people hand work over through issue #1 without anyone copying messages between terminals:

```text
[Raban · Claude] Interface merged. @Anatomik5 POST /api/lv/import now expects your importiere(dateiname, bytes) -> LV.
[Alisher · Codex] @f89pkdtkhw-lab GAEB X83 import is on main, 2,341 items from the example LV.
```

Claude Code sees new posts automatically and waits for mentions in the background. Codex and Antigravity read the board at task start, before every commit and after every merge, as required by `AGENTS.md`. To wake an agent on mentions, use a terminal loop:

```sh
while tools/board wait --nur-erwaehnungen; do codex exec "Read tools/board unread and handle what concerns you."; done
```

## Agent autonomy

| Level | When | How |
| --- | --- | --- |
| Supervised | Interfaces, unclear tasks | Agent asks before commands and changes. |
| Autonomous on laptop | Issue labelled `agent-bereit`, own worktree | Claude Code `claude --permission-mode acceptEdits`, Codex `codex --full-auto`, Antigravity: enable automatic terminal commands in agent settings. |
| Crew | Many parallel issues for one person | A First Mate dispatches and monitors workers ([FirstMate](firstmate.md)). |
| Cloud | Small issues while the laptop does other work | Label `claude`, comment `@codex implement this` or label `jules`. |

At every level, tests run before pushing, nobody pushes directly to `main`, and a PR is merged only after green checks.

## From your phone

Use `/remote-control` in Claude Code (including the First Mate) to control the running session from the Claude app's Code tab. When agents need you, they mention you on the board and the GitHub app sends a push notification.

## One-time cloud agent setup (optional)

Only the repository owner can install apps on a private repository. Afterwards everyone connects their own account.

| Agent | Setup | Trigger | Runs on the account of |
| --- | --- | --- | --- |
| Claude in GitHub Actions | Owner runs `/install-github-app` in Claude Code; installs Claude app and saves `CLAUDE_CODE_OAUTH_TOKEN`. Decline the offered workflow; `.github/workflows/claude.yml` already exists. | Label `claude` or `@claude` in an issue or PR | Person whose token is saved |
| Codex Cloud | Connect GitHub at chatgpt.com/codex, authorize repository, enable Code Review | `@codex review` on PR, `@codex implement this` on issue | Person commenting |
| Jules | Give the Jules app repository access at jules.google | Label `jules` on issue | Person who connected Jules |

## GitHub Actions minutes

A private repository on GitHub's free plan has 2,000 minutes per month. Windows counts double, macOS tenfold. PRs therefore test only on Linux; Windows and macOS run after merge. A Claude task in Actions takes about 5–20 minutes. Check usage at github.com/settings/billing.

## Cadence until submission

The schedule through Sunday 12:00 is in [team setup](teamstart.md#schedule-until-sunday-1200). Every two hours, the lead starts the demo from `main` on the presentation laptop; bugs become issues immediately.

## Graphify: mandatory code context

[Graphify](https://github.com/Graphify-Labs/graphify) reveals calls and dependencies for repository navigation. The PyPI package is `graphifyy`, the CLI is `graphify`, the assistant skill is `/graphify` (Codex: `$graphify`). Requires Python 3.11+ and uv or pipx.

`python tools/setup.py` installs the missing tool with uv, falling back to pipx, checks CLI startup and runs `graphify install`. If no installer exists, Graphify is not on PATH or registration fails, setup reports an error and exits unsuccessfully. Manual setup:

```sh
uv tool install graphifyy
# Without uv, use: pipx install graphifyy
graphify install
```

Create or update the graph before every task. Explicitly restrict the CLI run to code and skip semantic analysis:

```sh
graphify extract . --code-only
graphify query "How does an LV move from import to review report?"
graphify explain "importiere"
graphify path "importiere" "pruefe_mit_llm"
```

With an existing code-only graph, `graphify update .` is also possible. Always explicitly restrict `/graphify` to code without semantic extraction. Read/search specific files after querying the graph. Generated results stay local and ignored in `graphify-out/`; never reuse an old graph containing semantically analyzed documents.

**Confidentiality:** semantic PDF/document analysis uses a model, including through the running assistant. Use only the local code path; never send partner LVs or documents to Graphify/cloud services. Versioned `.graphifyignore` excludes `data/datensatz/`, `data/testfaelle/`, documents and local credentials. Do not bypass exclusions. Graphify is installed separately as a developer tool, not a product dependency. Setup and tests neither create a graph nor call a model.
