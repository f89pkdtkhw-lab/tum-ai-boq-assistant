# FirstMate: one agent manages a whole crew

Each person talks to a single agent, the First Mate. It splits work, launches each task in a separate coding agent and Git worktree, monitors it through merge, and asks only when a decision is needed. This setup won prizes at Knight Hacks and Cal Hacks, with 72 and 252 worker agents on one side of a four-person team. The tools are open source: [FirstMate](https://github.com/kunchenguid/firstmate) and quota-axi by Kun Chen, [Herdr](https://github.com/herdrdev/herdr) by herdrdev, [Handy](https://github.com/cjpais/Handy) by CJ Pais.

How our pieces fit together:

| Component | Purpose |
| --- | --- |
| First Mate per person | Processes their human's issues, only in their folders according to `AGENTS.md` ownership |
| Crew | Claude Code and Codex workers, model selected per task from `tools/firstmate/crew-dispatch.json` |
| Herdr | One window per agent, showing who is working and waiting |
| quota-axi | New work goes to the subscription with the most remaining quota |
| Team board, issue #1 | First Mates and agents working for different people hand over work here |
| Phone | Claude app with Remote Control for conversation, GitHub app for board mentions |

## Maximum autonomy: everyone talks only to their First Mate

```text
 Laptops 1..5: Human ──► First Mate (Claude OR Codex) ──► 3–5 workers (Claude/Codex per task)
                               │ reads/writes                  │ separate worktree + branch per issue
                               ▼                               ▼
               GitHub = only shared state: Issues (queue) · in-arbeit (lock) · board #1 (communication) · PRs + CI
                               ▲
                     python3 tools/stand.py → all five crews + overlap warnings
```

1. **One contact.** Talk only to your First Mate, on the laptop or via `/remote-control` on your phone. It splits work, launches workers, monitors and merges.
2. **Pull work.** When a worker slot is free, the First Mate uses `python3 tools/stand.py --naechstes` to find the next available `agent-bereit` issue (yours first, then unassigned), and claims it with `python3 tools/aufgabe.py <number> --uebernehmen`. This assigns you and sets `in-arbeit`, locking the issue for other First Mates.
3. **No overlap.** Every issue states its scope (files/folders). `tools/stand.py` warns if two active issues overlap or two open PRs change the same file. The First Mate pauses the later task and resolves it on the board.
4. **Everyone sees everything.** Every First Mate runs `tools/stand.py` and `tools/board unread` each round; merges affecting others get an `@all` board post.
5. **Queue empty?** The First Mate creates more scoped issues from `docs/case.md` (`auftrag-schneiden` skill) and announces them. The lead's First Mate (@f89pkdtkhw-lab) keeps the overall queue filled.
6. **Claude ↔ Codex without losing progress.** Task state lives in the issue, branch, `.auftrag.md` and handover comment (`handoff` skill), never only in a session. A Codex worker can continue a Claude worker's task. The First Mate selects per `crew-dispatch.json` and switches provider when quota runs out (`quota-axi`). The First Mate itself is replaceable: end the session, start `codex` instead of `claude` in `~/firstmate`; backlog and captain preferences persist in `~/firstmate/data/`.

Rules are in [tools/firstmate/captain.md](../tools/firstmate/captain.md). `bash tools/firstmate/setup.sh "First name"` writes them into your FirstMate (backing up an older version first).

**Without FirstMate** (e.g. Windows without WSL), follow the same process manually: `python tools/stand.py --naechstes`, then `python tools/aufgabe.py <number> --uebernehmen`, then open the folder in Claude Code or Codex.

## Install on Mac

Run commands in this order:

```sh
brew install --cask ghostty                  # Terminal
curl -fsSL https://claude.ai/install.sh | bash
npm install -g @openai/codex                 # Or: brew install --cask codex
brew install herdr gh jq tmux node
npm install -g quota-axi
brew install --cask handy                    # Free offline dictation; alternative: Wispr Flow
```

Start `claude` and `codex` once each and sign in, run `gh auth login`, then in the team repository:

```sh
bash tools/firstmate/setup.sh "Your first name"
```

The script checks all tools, clones FirstMate into `~/firstmate` and writes local settings: Herdr window management, our model selection, and your captain preferences including board, ownership and First Mate merges.

## Install on Windows (WSL)

FirstMate and Herdr require macOS or Linux. On Windows, both run in WSL, Linux inside Windows.

1. Open PowerShell **as Administrator**, run `wsl --install -d Ubuntu`, restart Windows. Open Ubuntu from Start and create a Linux user.
2. Install basic tools in Ubuntu:

   ```sh
   sudo apt update && sudo apt install -y git jq tmux python3 python3-venv nodejs npm curl
   curl -fsSL https://claude.ai/install.sh | bash
   sudo npm install -g @openai/codex quota-axi
   curl -fsSL https://herdr.dev/install.sh | sh
   ```

   Install GitHub CLI using the [Linux instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md), then `gh auth login`.
3. Start Claude Code and Codex once each in Ubuntu and sign in. Windows sign-in does not carry over to WSL.
4. Clone the team repo **inside the Linux filesystem**, not `/mnt/c`, which slows Git and agents:

   ```sh
   git clone https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.git ~/tum-ai-boq-assistant
   cd ~/tum-ai-boq-assistant && python3 tools/setup.py
   bash tools/firstmate/setup.sh "Raban"
   ```

Use Windows Terminal's Ubuntu profile instead of Ghostty. Handy and Wispr Flow are also available for Windows.

## Start a session

1. Open a terminal and start `herdr`.
2. In a Herdr window: `cd ~/firstmate`, then `claude`.
3. First time: “Add https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant as a project in direct-PR +yolo mode.” `direct-PR` means the crew opens finished PRs; `+yolo` means the First Mate merges after successful local tests and green GitHub checks. Workers do not merge. Without FirstMate, use self-merge from `AGENTS.md`.
4. State what to build, e.g. “Process all agent-bereit issues assigned to me.” The First Mate opens a Herdr window per worker; click any window to inspect it.

If a worker is waiting for clarification, the First Mate can answer in its window. When a subscription runs out, it uses quota-axi to select a provider with remaining capacity for new tasks.

## Control station: everything in one window

```sh
bash tools/leitstelle.sh
```

Opens three panes: Herdr with First Mate and worker windows on the left (type `claude` there), `quota-axi` with subscription quotas at upper right, and recent board posts at lower right. Click to switch panes, or Ctrl+B then an arrow. Ctrl+B then D detaches without stopping anything; the same command reattaches. On Windows, a desktop shortcut `Leitstelle.cmd` opens the same view in Ubuntu:

```bat
@echo off
wt.exe wsl.exe -d Ubuntu --cd ~ -- bash -lc "~/tum-ai-boq-assistant/tools/leitstelle.sh"
```

## Browser command center

The control station also starts `python3 tools/dashboard.py`; on Windows, desktop shortcut `Dashboard.cmd` opens it directly. Visit http://localhost:8770:

- **First Mate console** in color with an input field (Enter sends) and buttons for Enter, Esc, arrows, 1–3, y/n and Ctrl+C.
- **Live tile per worker**; workers waiting for you appear first in yellow. Click to open the console and answer directly.
- **Team board** with input and highlighted mentions; posts without a prefix receive `[<login> · Control station]`.
- Quota rings, countdown to Sunday 11:30 (internal target), issues per person, PRs with CI status.
- **Alarms** (bell at top right): sound and Windows notification when an agent waits or you are mentioned.

The page controls real agents. It listens only on 127.0.0.1; every control request requires the page's session token and matching Origin.

## Control from your phone

- **Talk:** enter `/remote-control` in the First Mate window or start with `claude remote-control`. Find the session in the Claude app's Code tab; type or dictate as on the laptop. The laptop must remain on and online.
- **Get called:** agents mention your GitHub login on the board when they need a decision, access or help. Install GitHub's app, enable mention notifications and subscribe to issue #1. Every mention then reaches your phone.
- **Stay informed:** every completed merge affecting others is announced with `@all`; the GitHub app shows board history.

## Model selection

Setup copies `tools/firstmate/crew-dispatch.json` to `~/firstmate/config/`. FirstMate reads the natural-language rules and selects per task:

| Task | Claude | Codex | Google |
| --- | --- | --- | --- |
| Small change in one or two files | haiku | gpt-6-luna | – |
| UI visible to the jury | opus | – | – |
| Hard or unclear, interface, planning | opus | gpt-6.1-sol | – |
| Implementation against a finished spec or known bug cause (`modell:bugfix`) | sonnet | gpt-6.1-sol | – |
| Research and reading | – | gpt-6.1-sol | – |
| Documentation, pitch, text after planning (`modell:text`) | haiku | gpt-6-luna | – |
| Everything else | sonnet | gpt-6.1-sol | – |

`modell:bugfix` retains its name for specified implementations and known bug causes. Model names change often: check Claude Code and Codex model selectors before the weekend and update the file. `quota-axi --tui` shows remaining subscription quota live. Rerun setup after changing repository templates to update model rules. Existing captain preferences remain; ask your First Mate to incorporate changes from `tools/firstmate/captain.md` before kickoff.

## Who uses FirstMate

Recommendation: the two Mac users set up FirstMate; Windows laptops work directly with Claude Code or Codex and `tools/aufgabe.py`. Windows users wanting a crew use WSL as above.

## Boundaries

- Each crew works in its human's folders. The lead's integration crew may once modify the minimum cross-owner files needed for the kickoff interface, announced with `@all`, with subsequent owner assignment and module tests. Establish ownership before coding. Afterwards, First Mates start announced `agent-bereit` issues without further confirmation and release follow-up issues after named blockers merge.
- Workers on one GitHub account share 5,000 API calls per hour. Only the First Mate watches the board; workers read it before commits. With FirstMate variables (`FM_…`), Claude hooks automatically disable the wait loop; otherwise set `export BOARD_WAIT=off` before starting.
- Herdr, Ghostty and Homebrew commands above target Mac; on Windows use WSL.

Gemini CLI no longer accepts private Google accounts. Use the Google subscription through Antigravity in the IDE.
