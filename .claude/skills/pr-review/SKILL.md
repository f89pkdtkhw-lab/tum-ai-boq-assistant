---
name: pr-review
description: Review a team repository pull request against its issue, tests and AGENTS.md Code Review Rules, then leave a concise review comment. Optional cross-review alongside self-merge.
---

<!-- Generated from .agents/skills/pr-review/SKILL.md using python tools/agents_sync.py. Do not edit here. -->

Given a PR number, read it with `gh pr view <number>` and `gh pr diff <number>`, and read the linked issue with `gh issue view <number>`. Without a number, use the current branch's PR.

1. Check out the revision in your own worktree and run `python -m unittest discover -s tests -v`. Check GitHub results with `gh pr checks <number>`.
2. Run the issue's acceptance example yourself, in a browser for UI work. Record input, expected and observed output.
3. Apply the Code Review Rules in `AGENTS.md`: files stay within the owner's scope, no unannounced interface changes, no keys, no new dependencies, clear error cases, demo still starts.
4. Leave one comment with `gh pr review <number> --comment --body-file review.md`: one sentence with the overall assessment, at most five findings with file, line and example, then checks performed. If already merged and you find a real bug, open an issue using the bug form and mention the owner on the board.

Never merge someone else's PR or approve on a person's behalf. Explicitly state what you could not verify.
