"""Enter the Claude API key in the UI (#156).

Routes (all answers carry only "key set: yes/no", its source and the model, never the key):
    GET    /api/ai/key        current state, same fields as /health
    POST   /api/ai/key        {"key": "...", "model": "optional", "persist": false}
                              keeps the key in memory (llm.RUNTIME) and switches the provider to
                              anthropic at once; with persist=true also writes it to .env.local
    DELETE /api/ai/key        forgets the in-memory key (an environment / .env.local key still applies)
    POST   /api/ai/key/test   one small probe call; {"ok": true, ...} or {"ok": false, "error": "..."}

The key is never logged, echoed or sent anywhere except the configured provider. The request body is
parsed by hand so a validation error can never echo the key back (FastAPI's 422 answers contain the
input). Set LLM_KEY_UI=off on a backend that others can reach to disable changing the key.
"""
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from . import llm

router = APIRouter(prefix="/api/ai/key", tags=["ai"])

ENV_FILE = Path(__file__).resolve().parents[3] / ".env.local"  # gitignored (.env.*)
KEY_NAME = llm.KEY_FOR["anthropic"]
_MODEL = re.compile(r"^[A-Za-z0-9._:@/-]{1,100}$")
PROBE_TIMEOUT = 20.0


def state():
    """What /health shows for the key: provider, model, mock, key_set, key_source, reason."""
    current = llm.status()
    return {name: current.get(name) for name in ("provider", "model", "mock", "key_set", "key_source", "reason")} | {
        "ui_enabled": _ui_enabled()}


def _ui_enabled():
    return os.environ.get("LLM_KEY_UI", "").strip().lower() not in ("off", "0", "false", "no")


def _require_ui():
    if not _ui_enabled():
        raise HTTPException(403, "Entering the key in the UI is disabled on this server (LLM_KEY_UI=off).")


def _valid_key(value):
    """A plausible API key: printable ASCII without spaces. The message never contains the value."""
    if not isinstance(value, str):
        raise HTTPException(400, "Send the key as text in the field 'key'.")
    value = value.strip()
    if not 20 <= len(value) <= 400 or not all(33 <= ord(char) <= 126 for char in value):
        raise HTTPException(400, "This does not look like an API key (20-400 characters, no spaces).")
    return value


def _claude_model(value):
    if value in (None, ""):
        configured = llm.env("LLM_MODEL")
        return configured if configured.startswith("claude") else llm.DEFAULT_MODELS["anthropic"]
    if not isinstance(value, str) or not _MODEL.match(value.strip()):
        raise HTTPException(400, "Invalid model name.")
    return value.strip()


def persist(values, path=None):
    """Set NAME=value lines in .env.local (other lines stay), file mode 0600. Values are never logged."""
    path = Path(path or ENV_FILE)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    pending = dict(values)
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in pending:
            name = match.group(1)
            lines[index] = f"{name}={pending.pop(name)}"
    lines += [f"{name}={value}" for name, value in pending.items()]
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".env.local.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@router.get("")
def key_state():
    return state()


@router.post("")
async def set_key(request: Request):
    _require_ui()
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(400, "Send JSON like {\"key\": \"...\"}.")
    key = _valid_key(body.get("key"))
    chosen = _claude_model(body.get("model"))
    values = {"LLM_PROVIDER": "anthropic", "LLM_MODEL": chosen, KEY_NAME: key}
    if body.get("persist") is True:
        try:
            persist(values)
        except OSError:
            raise HTTPException(500, "Could not write .env.local; the key was not saved.") from None
    llm.RUNTIME.update(values)
    return state() | {"persisted": body.get("persist") is True}


@router.delete("")
def clear_key():
    _require_ui()
    llm.RUNTIME.clear()
    return state()


@router.post("/test")
def test_key():
    """One small probe call with the current configuration. Never raises; the error is readable."""
    _require_ui()
    current = state()
    if current["provider"] == "grokbot":
        from . import grokbot
        try:
            grokbot.queue_dir().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"ok": False, "provider": "grokbot", "model": current["model"],
                    "error": f"The Grok Bot queue directory is not writable ({exc})."}
        return {"ok": True, "provider": "grokbot", "model": current["model"], "ms": 0}
    if current["mock"]:
        reason = current["reason"] or "No API key set."
        return {"ok": False, "provider": current["provider"], "model": current["model"],
                "error": f"{reason} The app runs on the offline mock."}
    try:
        answer = llm.complete("Reply with the single word OK.", max_tokens=64, timeout=PROBE_TIMEOUT)
    except llm.LLMError as exc:
        return {"ok": False, "provider": current["provider"], "model": current["model"], "error": str(exc)}
    except Exception as exc:  # the probe must never crash the API
        return {"ok": False, "provider": current["provider"], "model": current["model"],
                "error": f"Probe call failed ({type(exc).__name__})."}
    return {"ok": True, "provider": answer.provider, "model": answer.model, "ms": answer.ms}
