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
| Anthropic (default) | `ANTHROPIC_API_KEY`, optional `LLM_MODEL` (default `claude-sonnet-5-5`), `ANTHROPIC_BASE_URL`, `ANTHROPIC_EFFORT` |
| OpenAI or compatible endpoint | `OPENAI_API_KEY`, `LLM_MODEL`, optional `OPENAI_BASE_URL` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Google Gemini | `GEMINI_API_KEY`, optional `LLM_MODEL` (default `gemini-2.5-flash`), optional `GEMINI_THINKING_BUDGET` |

### Claude for the demo (default)

1. Open the [Claude Console](https://platform.claude.com), sign in, and create a key under **API keys** (the account needs credit or the partner's provided budget).
2. In `.env.local` (never in `.env.example`, a commit, an issue or the board):

   ```sh
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=<your key>
   ```

3. Restart `python tools/dev.py` (the backend reads `.env.local` at start; variables already set in the shell win). `http://localhost:8000/health` must show `"provider": "anthropic"`, `"model": "claude-sonnet-5-5"` and `"mock": false`. `LLM_MODEL` overrides the model.

**Gemini instead:** create a free key in [Google AI Studio](https://aistudio.google.com/apikey) and set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env.local`; `/health` then shows `gemini-2.5-flash`. The free tier is rate limited to a few requests per minute.

The BoQ review (`/api/lv/pruefen`, `/api/lv/analyse`) then sends **all** items to the model, in batches of `LLM_BATCH_SIZE` (default 20) with up to `LLM_PARALLEL` (default 3) calls at a time; Claude runs the review at effort `LLM_REVIEW_EFFORT` (default `low`). The whole model review is bounded by `LLM_REVIEW_TIMEOUT` (default 60 s), every single call by `LLM_TIMEOUT` (default 60 s). With a key, the norm research N5 (`NORM_KI_RECHERCHE`) also makes one call per review.

**The demo never crashes on the model.** Without a key, on a timeout, an HTTP error (for example 429 on a rate limit), a refusal (`stop_reason: refusal`), an answer cut off at `max_tokens` or an unreadable answer, the report is still returned with the offline mock findings, `kennzahlen.modell_mock: true` and a readable `kennzahlen.modell_reason`. With a working model, `kennzahlen.modell_mock` is `false` and `kennzahlen.modell` names the model, e.g. `gemini/gemini-2.5-flash`. Model findings carry `quelle: "modell"` and a `regel_id` starting with `LLM_`; they never contain euro amounts.

For other server code: `llm.complete(prompt, system, max_tokens)` raises `LLMError` with a UI-safe message, `llm.complete_with_fallback(...)` never raises and returns the mock with `Answer.reason` instead, `llm.status()` says whether the app effectively runs on the mock and why, and `llm.parse_json(text)` reads JSON even inside code fences or with prose around it.

For a public deployment (Vercel or Render, see `render.yaml`), enter the same variables in the host's dashboard. For GitHub Actions: `gh secret set NAME`.

## Watch the budget

- Pay-per-use keys can run out within an hour if many workers use Opus. Budget mode uses Haiku and Sonnet, with Opus reserved for the hardest tasks.
- Tests always run offline on the mock (`api/tests/conftest.py` clears every model variable) and cost nothing. The demo uses the model only when a key is in `.env.local`. Make real model calls only when required by the issue.
- Ask the partner at their booth for the key's limit and record it in `docs/case.md`.
