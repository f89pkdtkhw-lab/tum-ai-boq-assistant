"""Developer options behind a simple unlock code: AI provider switch (Claude / Mock / Grok Bot).

Routes:
    POST /api/ai/dev-options/unlock   {"code": "..."}  → {"ok": true} or 403
    GET  /api/ai/dev-options          current provider, never the code
    POST /api/ai/dev-options          {"provider": "anthropic"|"mock"|"grokbot"}

The unlock is a UI gate: the frontend stores "unlocked" in localStorage. The backend
checks the code against DEV_OPTIONS_CODE (default 2211 when unset). The code is never
logged, echoed or returned. Changing the provider updates llm.RUNTIME, like the API-key
route, so the next model call uses it without a restart.
"""
import hashlib
import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from . import grokbot, llm

router = APIRouter(prefix="/api/ai/dev-options", tags=["ai"])

DEFAULT_CODE = "2211"
PROVIDERS = grokbot.PROVIDERS  # anthropic, mock, grokbot


def configured_code() -> str:
    return os.environ.get("DEV_OPTIONS_CODE", "").strip() or DEFAULT_CODE


def code_ok(given) -> bool:
    if not isinstance(given, str):
        return False
    expected = configured_code().encode("utf-8")
    got = given.strip().encode("utf-8")
    return hmac.compare_digest(hashlib.sha256(got).digest(), hashlib.sha256(expected).digest())


def state():
    current = llm.status()
    return {
        "provider": current["provider"],
        "model": current["model"],
        "mock": current["mock"],
        "reason": current.get("reason"),
        "providers": list(PROVIDERS),
        "queue_dir": str(grokbot.queue_dir()),
        "timeout_s": grokbot.wartezeit(),
    }


@router.post("/unlock")
async def unlock(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(400, "Send JSON like {\"code\": \"...\"}.")
    given = body.get("code")
    if not code_ok(given):
        # Never echo the submitted value (it may be a typo of the real code, or a secret).
        raise HTTPException(403, "Wrong unlock code.")
    return {"ok": True}


@router.get("")
def get_options():
    return state()


@router.post("")
async def set_provider(request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise HTTPException(400, "Send JSON like {\"provider\": \"mock\"}.")
    # Optional extra gate: if a code is sent, it must be correct. The UI usually
    # only calls this after unlock and does not resend the code.
    if "code" in body and not code_ok(body.get("code")):
        raise HTTPException(403, "Wrong unlock code.")
    chosen = body.get("provider")
    if not isinstance(chosen, str) or chosen.strip().lower() not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider. Allowed: {', '.join(PROVIDERS)}.")
    llm.RUNTIME["LLM_PROVIDER"] = chosen.strip().lower()
    return state()
