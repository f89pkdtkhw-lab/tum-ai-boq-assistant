# Captain preferences for TUM.ai Construction Hackathon

- Talk to me in German. Keep status updates to one or two sentences; I often read them on my phone.
- I am <NAME>, GitHub login @<LOGIN>, on the team repo https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant.
- That repo's AGENTS.md is binding for every crewmate: the team board, the owner table, the workflow and the limits. Only dispatch work for issues assigned to @<LOGIN> or inside the folders the owner table gives @<LOGIN>. The lead's integration crew may make the minimal cross-owner changes in the one kickoff interface PR after announcing exact files with @all and assigning their later owners including module tests. Other work outside owned folders goes to the board as a request to its owner.
- The project runs in direct-PR mode with yolo merge: a crewmate opens a ready PR; the first mate merges it once the tests pass locally and the GitHub checks are green, and handles worktree cleanup. Crewmates never merge or remove worktrees themselves. Never push straight to main or demo.
- A kickoff case text authorizes the lead's integration crew to run kickoff through issue creation without another approval. On its board start signal, dispatch assigned agent-bereit issues without asking the person to confirm. Keep dependent issues unready until their named blockers merge, then add agent-bereit and dispatch them.
- Team board: pinned issue #<BOARD> in that repo. At every supervision pass, read new comments with `gh issue view <BOARD> -R f89pkdtkhw-lab/tum-ai-boq-assistant --comments`. When a post mentions @<LOGIN> or @all, act on it: steer or spawn the matching crewmate, and have it answer on the board. Posts by my crewmates start with `[<NAME> · <agent>]`.
- When a crewmate finishes something others depend on (API route, schema, data format, env var), make sure it posts that on the board with @all.
- Demo first: work the judges will see gets the strongest model, and the demo must start on the presentation laptop at every merge.
- Run at most 6 crewmates at the same time unless I say otherwise; more parallel workers mean more merge conflicts and rate limits. With a shared API budget (`shared_quota` in crew-dispatch.json) stay at 4.
- The product lives in web/ (Next.js), api/ (FastAPI), api/app/ai/ (model access) and data/. `python tools/dev.py` starts it; every crewmate keeps `cd api && python -m pytest -q` and `cd web && npm run build` green.
- Escalate to me only for real decisions, credentials, and blockers. Mention @<LOGIN> on the board as well, so it reaches my phone through GitHub.
