# API

FastAPI backend of the BoQ review assistant. Start it with `python tools/dev.py` from the repository root, or `uvicorn app.main:app --port 8000` from `api/`. Health: `http://localhost:8000/health`.

Keys and model settings live in the repository-root `.env.local` (see `.env.example`). Never commit real keys.

## Developer options

The Claude API key is entered in **Settings → Entwickleroptionen**, behind an unlock code. The backend checks `POST /api/ai/dev-options/unlock` against `DEV_OPTIONS_CODE`. If that variable is unset, the default code is `2211` (local demo only; set your own value in `.env.local` if others can reach the backend).

The same settings page can switch the model provider between `anthropic` (Claude API key), `mock` and `grokbot`. Grok Bot mode is a file-queue bridge, documented in [docs/grokbot-bridge.md](../docs/grokbot-bridge.md).
