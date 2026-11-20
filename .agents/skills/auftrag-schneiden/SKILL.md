---
name: auftrag-schneiden
description: Split the case brief or a plan into parallel GitHub issues in our format, with owners from the ownership table, separate file scopes, acceptance tests, target branches and dependencies so agents can work without collisions.
---

Read `docs/case.md`, the ownership table in `AGENTS.md` (section 3), open issues (`gh issue list --state open`) and the folder structure. State the next demo's goal in one sentence before splitting. If the plan is unclear, suggest `grill-me` first.

1. Follow `to-tickets`: vertical slices providing a narrow but complete path through all layers, independently demonstrable. Each slice fits a fresh context window.
2. Each task belongs to exactly one owner from the ownership table. No two open tasks share a file. Where unavoidable, first create a short shared-interface task with fixed example data, allowing UI and logic to start in parallel afterwards.
3. Define the interface explicitly: function names or route, fields, example input and expected output.
4. Write each acceptance test as concrete input and a verifiable result, not an intention.
5. Show a table (title, owner, scope, blocked by, tool). During kickoff, the case-start instruction is approval: create issues immediately, blockers first; skip the `to-tickets` approval round. Outside kickoff, create them only after approval. Use exactly these headings so `tools/aufgabe.py` can read them:

```markdown
### Owner

github-login

### Outcome and acceptance test

For input … the UI displays …

### Scope

web/src/suche/, tests/test_suche.py

### Target branch

main

### Tool

any

### Interfaces and dependencies

Blocked by #12 (data format).
```

```sh
gh issue create --title "Task · …" --body-file auftrag.md --label agent-bereit --label modell:ui --assignee github-login
```

Give each issue exactly one model label: `modell:klein` (small, clearly specified change), `modell:ui` (demo UI), `modell:schwer` (interface, architecture, unclear), `modell:bugfix` (implementation against a finished spec or known bug cause), `modell:recherche` (read and report only), or `modell:text` (documentation, pitch, text after planning; inexpensive model). Unclear product decisions remain `modell:schwer`. The First Mate and `tools/aufgabe.py` select the model accordingly.

If an issue names a file delivered by another issue, list that issue number and file as a blocker under “Interfaces and dependencies”. Check this especially for pitch references to `docs/demo.md` and `data/vergleich.md`. Every logic issue gets its own connected placeholder module with a fixed contract and its own test file; `api/app/main.py` remains in the preceding interface PR.

Set `agent-bereit` (including in `gh issue create` above) only when scope, acceptance test and target branch are complete and no blocker remains open. The responsible First Mate adds the label after blockers merge. Finish with a board post naming immediately available issues and mentioning owners by GitHub login.
