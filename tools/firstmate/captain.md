# Captain preferences for the TUM.ai Construction Hackathon (Challenge A, LV review assistant)

- Talk to me in English. Keep status updates to one or two sentences; I often read them on my phone.
- I am <NAME>, GitHub login @<LOGIN>, on the team repo https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant. Five people on five laptops each run their own first mate with their own Claude and Codex accounts; GitHub is the only shared state.
- That repo's AGENTS.md is binding for every crewmate: board, owner table, workflow, limits. Hard deadline: Sunday 22.11.2026 12:00 Europe/Berlin, internal target 11:30, feature freeze 09:00.

## Run autonomously

- Default posture is maximum autonomy: keep my crew busy without asking me. Escalate only for real product decisions, credentials, and blockers you cannot resolve; mention @<LOGIN> on the board as well so it reaches my phone.
- Team board: pinned issue #<BOARD> (`gh issue view <BOARD> --comments`, or `tools/board unread`). At the start and at every supervision pass run `python3 tools/stand.py` in the project checkout and `tools/board unread`. That is the shared picture of all five crews: claimed issues (label `in-arbeit`), ready issues, open PRs with CI, and overlap warnings.
- Pull work, never wait: when a crewmate slot is free, take `python3 tools/stand.py --naechstes --login <LOGIN>`. It returns my own `agent-bereit` issues first, then unassigned ones whose scope does not touch any claimed area. Claim before dispatching: `python3 tools/aufgabe.py <Nr> --uebernehmen --werkzeug "<harness>"` assigns me, adds `in-arbeit` and posts on the board. Never dispatch an issue that is already `in-arbeit` or assigned to someone else.
- No overlap: a crewmate edits only the files in its issue's scope. If `tools/stand.py` reports an overlap with another crew, pause the later claim and settle it on the board with the other owner before continuing.
- If the ready queue is empty, cut the next issues yourself with the `auftrag-schneiden` skill from `docs/case.md` (priority: error detection, then risk, then change orders, then pricing), inside my owner area, label them `agent-bereit`, and announce them on the board. Do not cut issues in other owners' areas; post a request to them instead.
- Run at most 5 crewmates at once (3 when `shared_quota` is set). More parallel workers mean more merge conflicts and rate limits on the shared GitHub account limit.

## Ship

- The project runs in direct-PR mode with yolo merge: a crewmate opens a ready PR with `Closes #<Nr>`; the first mate merges it once tests pass locally and the GitHub checks are green, then cleans up the worktree. Crewmates never merge. Never push straight to main or demo.
- When a merge changes something others depend on (API route, data model of a position or finding, data format, env var), make sure it is posted on the board with @all.
- If the board says "main is red", stop merging until it is green again; if my crew caused it, fixing it beats everything else.
- Demo first: work the judges will see gets the strongest model; every merge must keep `python3 tools/dev.py` starting.

## Claude and Codex are interchangeable

- Pick the harness per task from `config/crew-dispatch.json`. When one provider's quota runs low (`quota-axi`), dispatch new work to the other one; do not wait for quota.
- All task state lives in GitHub (issue, branch, PR, board) and in the worktree's `.auftrag.md`, never only in a session. A task started by Claude can be finished by Codex and vice versa: the new worker reads the issue, `.auftrag.md`, the branch diff and the latest issue comment.
- Before a crewmate stops mid-task (quota, context full, harness switch) it commits work in progress to its branch and leaves a handoff comment on the issue using the `handoff` skill: done, open, next step, how to verify.
- Posts by my crewmates start with `[<NAME> · Claude]` or `[<NAME> · Codex]`.

## Product facts every crewmate needs

- The product lives in web/ (Next.js), api/ (FastAPI), api/app/ai/ (model access) and data/. `python3 tools/dev.py` starts it; keep `cd api && python3 -m pytest -q`, `cd web && npm run build` and `python3 -m unittest discover -s tests -v` green.
- The partner's dataset is confidential: never copy it outside this private repo, never into public gists, issues of other repos, or prompts to third-party services other than the configured LLM provider.
