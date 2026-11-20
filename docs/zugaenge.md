# Access provided at the competition

Partners and organizers often provide model access through accounts or API keys. There are two separate uses: **coding agents** and the **product**. Never put keys in chat, board posts, issues or the repository; share them only through a password manager.

## Coding agents

| Access | Claude Code | Codex |
| --- | --- | --- |
| Account login | Start `claude`, then `/login` with the provided account | Start `codex`, then “Sign in” with the provided account |
| API key | `export ANTHROPIC_API_KEY=…` before starting | `codex login --api-key …` |
| AWS Bedrock | `export CLAUDE_CODE_USE_BEDROCK=1` plus AWS access | – |
| Google Vertex | `export CLAUDE_CODE_USE_VERTEX=1` plus Google project | – |

With a provided API budget rather than personal subscriptions, quota-axi cannot see the quota. Switch the First Mate to budget mode:

```sh
bash tools/firstmate/modus.sh budget   # Cheaper models, shared budget, at most 4 workers
bash tools/firstmate/modus.sh abo      # Return to personal subscriptions
```

## Product

```sh
cp .env.example .env.local
```

Enter the provider's key in `.env.local` and set `LLM_PROVIDER` and `LLM_MODEL`. Without an explicit provider, the backend selects the first provider with a key, or the mock if no key exists. `python tools/setup.py` shows which keys were found, never their values. `http://localhost:8000/health` shows the product's current provider and model.

| Provider | Variables |
| --- | --- |
| Anthropic | `ANTHROPIC_API_KEY`, optional `ANTHROPIC_BASE_URL` |
| OpenAI or compatible endpoint | `OPENAI_API_KEY`, `LLM_MODEL`, optional `OPENAI_BASE_URL` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Google Gemini | `GEMINI_API_KEY` |

For a public deployment (Vercel or Render, see `render.yaml`), enter the same variables in the host's dashboard. For GitHub Actions: `gh secret set NAME`.

## Watch the budget

- Pay-per-use keys can run out within an hour if many workers use Opus. Budget mode uses Haiku and Sonnet, with Opus reserved for the hardest tasks.
- Tests and the demo use the mock and cost nothing. Make real model calls only when required by the issue.
- Ask the partner at their booth for the key's limit and record it in `docs/case.md`.
