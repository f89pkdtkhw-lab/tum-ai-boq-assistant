"""One interface for all model providers that may be available at the competition.

Select through environment variables (see .env.example):
    LLM_PROVIDER   anthropic | openai | azure | gemini | mock | grokbot
                   (empty = first provider with a key, otherwise mock)

    LLM_MODEL      Model name; defaults to a provider-specific model when omitted
    LLM_TIMEOUT    Seconds per model call (default 60); the BoQ review has its own LLM_REVIEW_TIMEOUT

`mock` runs without network access or keys so the demo and tests always start.
Keys never leave the server and never appear in error messages.

Entry points:
    complete(prompt, system, max_tokens)   raises LLMError with a UI-safe message
    complete_with_fallback(...)            never raises: on a missing key, error or timeout it answers
                                           with the mock and sets ``Answer.reason``
    config() / status()                    what the app runs on; status() also says whether the app
                                           effectively runs on the mock and why, and never raises
    research(prompt, system, max_tokens,   answer backed by Claude's web search: text + citations (url,
             max_searches=5, timeout)      title, cited_text); other providers answer without citations
    parse_json(text)                       robust JSON object extraction (code fences, prose around it)
    load_env_file(path)                    reads .env.local at app start (environment variables win)
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import base64
import contextvars
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import time
from pathlib import Path
from threading import RLock

import httpx

from . import sprache  # #196: German answers when the UI is German

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "",
    "azure": "",
    "gemini": "gemini-2.5-flash",
    "mock": "mock",
    "grokbot": "grok-bot",
}
KEY_FOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "azure": "AZURE_OPENAI_API_KEY",
           "gemini": "GEMINI_API_KEY"}
DEFAULT_TIMEOUT = 60.0
TIMEOUT = DEFAULT_TIMEOUT  # kept for compatibility; the effective value comes from seconds()


class LLMError(Exception):
    """A message that is safe to show in the UI."""


@dataclass
class Answer:
    text: str
    provider: str
    model: str
    ms: int
    reason: str | None = None  # set only by complete_with_fallback when it answered with the mock


def seconds(name="LLM_TIMEOUT", default=DEFAULT_TIMEOUT):
    """Seconds from an environment variable; invalid or non-positive values use the default."""
    try:
        value = float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


# #156: values set at runtime by the UI key route (app/ai/schluessel.py), held in memory only. They win
# over the environment so a key entered in the UI is used at once, without a restart. Never logged.
RUNTIME = {}


def env(name):
    return (RUNTIME.get(name) or os.environ.get(name, "")).strip()


_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env_file(path):
    """Load ``NAME=value`` lines (e.g. ``.env.local``) into ``os.environ``; returns the loaded names.

    Variables already set in the environment win, empty values and comments are skipped, quotes
    around a value are removed. Values are never logged or returned. A missing file is no error.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    loaded = []
    for line in lines:
        match = _ENV_LINE.match(line)
        if not match or line.lstrip().startswith("#"):
            continue
        name, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if value and not os.environ.get(name, "").strip():
            os.environ[name] = value
            loaded.append(name)
    return loaded


def provider():
    chosen = env("LLM_PROVIDER").lower()
    if chosen:
        if chosen not in DEFAULT_MODELS:
            raise LLMError(f"LLM_PROVIDER '{chosen}' ist unbekannt. Erlaubt: {', '.join(DEFAULT_MODELS)}")
        return chosen
    return next((name for name, key in KEY_FOR.items() if env(key)), "mock")


def model(name=None):
    name = name or provider()
    return env("LLM_MODEL") or (env("AZURE_OPENAI_DEPLOYMENT") if name == "azure" else "") or DEFAULT_MODELS[name]


def config():
    """What the app runs on, without any secret."""
    name = provider()
    return {"provider": name, "model": model(name), "mock": name == "mock",
            "keys": {provider_name: bool(env(key)) for provider_name, key in KEY_FOR.items()}}


def _keys():
    return {provider_name: bool(env(key)) for provider_name, key in KEY_FOR.items()}


def status():
    """Like config(), but never raises and reports the effective mode.

    ``mock`` is True when no real call would be made: provider ``mock``, an unknown provider, a
    missing key or a missing model name. ``reason`` explains why a configured provider is not used
    (None when the mock was chosen on purpose or no key exists at all).
    """
    try:
        name = provider()
    except LLMError as exc:
        return {"provider": "mock", "model": DEFAULT_MODELS["mock"], "mock": True, "keys": _keys(),
                "reason": str(exc), "key_set": False, "key_source": None}
    chosen = model(name)
    if name == "grokbot":
        return {"provider": name, "model": chosen, "mock": False, "keys": _keys(), "reason": None,
                "key_set": False, "key_source": None}
    key_name = KEY_FOR.get(name, KEY_FOR["anthropic"])  # #156: "key set" for the provider in use (Claude on mock)
    result = {"provider": name, "model": chosen, "mock": name == "mock", "keys": _keys(), "reason": None,
              "key_set": bool(env(key_name)),
              "key_source": "ui" if RUNTIME.get(key_name) else "env" if env(key_name) else None}
    if name != "mock" and not env(KEY_FOR[name]):
        result.update(mock=True, reason=f"Missing {KEY_FOR[name]} for {name}; AI steps run without a model.")
    elif name != "mock" and not chosen:
        result.update(mock=True, reason=f"Set LLM_MODEL for {name}; AI steps run without a model.")
    return result


def complete(prompt, system="", max_tokens=1024, *, timeout=None, json_mode=False, effort=None, bilder=None):
    """One model call. ``timeout`` (seconds) bounds the HTTP request; ``json_mode`` asks providers
    that support it (Gemini) for a JSON-only answer; ``effort`` (low|medium|high|xhigh|max) sets the
    Claude effort level (default: ANTHROPIC_EFFORT, else the model default). ``bilder`` (#192) is a list
    of JPEG bytes sent before the prompt (Claude only; other providers raise LLMError). Raises LLMError
    with a UI-safe message."""
    system = sprache.mit_hinweis(system)
    name = provider()
    chosen = model(name)
    started = time.perf_counter()
    if name not in ("mock", "grokbot") and not env(KEY_FOR[name]):
        raise LLMError(f"Missing {KEY_FOR[name]} for {name}. Without a key, set LLM_PROVIDER=mock.")
    if not chosen:
        raise LLMError(f"Set LLM_MODEL for {name} (model name from the provider documentation).")
    limit = timeout if timeout and timeout > 0 else seconds()
    if name == "grokbot":
        from . import grokbot as _grokbot_mod
        limit = _grokbot_mod.wartezeit(timeout)
    if bilder and name not in ("anthropic", "grokbot"):
        raise LLMError(f"{name} cannot read page images here; AI page reading needs Claude (LLM_PROVIDER=anthropic).")
    extra = {"bilder": bilder} if bilder else {}
    try:
        text = {"anthropic": _anthropic, "openai": _openai, "azure": _azure, "gemini": _gemini, "mock": _mock,
                "grokbot": _grokbot}[name](
            prompt, system, chosen, max_tokens, json_mode=json_mode, timeout=limit, effort=effort, **extra)
    except LLMError:
        raise
    except httpx.TimeoutException:
        raise LLMError(f"{name} did not answer within {limit:g} s.") from None
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = "Rate limit or free quota reached; wait a minute." if code == 429 else "Check the key, model and credit."
        raise LLMError(f"{name} returned HTTP {code}. {hint}") from None
    except httpx.HTTPError:
        raise LLMError(f"{name} is unreachable. Check the network or set LLM_PROVIDER=mock.") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise LLMError(f"{name} returned an unexpected response.") from None
    return Answer(text.strip(), name, chosen, round((time.perf_counter() - started) * 1000))


def complete_with_fallback(prompt, system="", max_tokens=1024, *, timeout=None, json_mode=False, effort=None,
                           mock_text=None):
    """Like complete(), but never raises and never waits longer than ``timeout`` seconds in total.

    On a missing key, HTTP error, unexpected answer or timeout it returns the mock answer (or
    ``mock_text`` when given) with ``provider == "mock"`` and a readable ``reason``. A deliberate mock
    configuration answers with the mock and ``reason=None``.
    """
    state = status()
    limit = timeout if timeout and timeout > 0 else seconds()
    if state["provider"] == "grokbot":
        from . import grokbot as _grokbot_mod
        limit = _grokbot_mod.wartezeit(timeout)

    def fallback(reason):
        answer = mock(prompt, system, max_tokens)
        if mock_text is not None:
            answer.text = mock_text
        answer.reason = reason
        return answer

    if state["mock"]:
        return fallback(state["reason"])
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-call")
    try:
        # copy_context: the pool thread keeps the request's answer language (#196)
        return pool.submit(contextvars.copy_context().run, complete, prompt, system, max_tokens, timeout=limit,
                           json_mode=json_mode,
                           effort=effort).result(
            timeout=limit + 1)
    except FutureTimeout:
        return fallback(f"{state['provider']} did not answer within {limit:g} s; no AI answer used.")
    except LLMError as exc:
        return fallback(f"{exc} No AI answer used.")
    except Exception as exc:  # the demo must never crash on a model call
        return fallback(f"{state['provider']} call failed ({type(exc).__name__}); no AI answer used.")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def parse_json(text):
    """Return the first JSON object or array in a model answer, or raise ValueError.

    Accepts plain JSON, JSON inside Markdown code fences and JSON with prose before or after it.
    """
    if not isinstance(text, str):
        raise ValueError("answer is not text")
    candidates = [text.strip()] + [block.strip() for block in _FENCE.findall(text)]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except ValueError:
            pass
        for index, char in enumerate(candidate):
            if char in "{[":
                try:
                    return decoder.raw_decode(candidate, index)[0]
                except ValueError:
                    continue
    raise ValueError("no JSON found in answer")


def _post(url, headers, payload, timeout=None):
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout or seconds())
    response.raise_for_status()
    return response.json()


EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _anthropic(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None, bilder=None):
    """Claude Messages API. Current models reject temperature/top_p/top_k, thinking {type: disabled}
    and assistant prefill, so none is sent; JSON comes from the prompt and parse_json()."""
    content = prompt
    if bilder:  # #192: page images first, then the instruction text
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.b64encode(b).decode("ascii")}} for b in bilder]
        content.append({"type": "text", "text": prompt})
    payload = {"model": chosen, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
    if system:
        payload["system"] = system
    effort = (effort or env("ANTHROPIC_EFFORT")).lower()
    if effort in EFFORTS:
        payload["output_config"] = {"effort": effort}
    data = _post(env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1/messages",
                 {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                  "content-type": "application/json"}, payload, timeout)
    stop = data.get("stop_reason")
    if stop == "refusal":
        category = (data.get("stop_details") or {}).get("category")
        raise LLMError(f"anthropic declined the request (refusal{': ' + category if category else ''}).")
    if stop == "max_tokens":
        raise LLMError(f"anthropic stopped at max_tokens ({max_tokens}); the answer is incomplete.")
    text = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
    if not text.strip():
        raise LLMError(f"anthropic returned no text ({stop or 'empty answer'}).")
    return text


def _chat_messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def _openai(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None):
    base = (env("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    data = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
                 {"model": chosen, "messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens},
                 timeout)
    return data["choices"][0]["message"]["content"]


def _azure(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None):
    endpoint = env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not endpoint or not chosen:
        raise LLMError("For azure, set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT.")
    version = env("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    data = _post(f"{endpoint}/openai/deployments/{chosen}/chat/completions?api-version={version}",
                 {"api-key": env("AZURE_OPENAI_API_KEY")},
                 {"messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens}, timeout)
    return data["choices"][0]["message"]["content"]


def _gemini(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None):
    generation = {"maxOutputTokens": max_tokens}
    if json_mode:
        generation["responseMimeType"] = "application/json"
    budget = env("GEMINI_THINKING_BUDGET")
    if budget.lstrip("-").isdigit():  # optional; e.g. 0 turns thinking off on Flash models
        generation["thinkingConfig"] = {"thinkingBudget": int(budget)}
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    base = (env("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    data = _post(f"{base}/models/{chosen}:generateContent", {"x-goog-api-key": env("GEMINI_API_KEY")}, payload,
                 timeout=timeout)
    blocked = (data.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise LLMError(f"gemini blocked the request ({blocked}).")
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError("gemini returned no answer.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    if not text.strip():
        reason = candidates[0].get("finishReason") or "empty answer"
        hint = " Raise max_tokens or set GEMINI_THINKING_BUDGET=0." if reason == "MAX_TOKENS" else ""
        raise LLMError(f"gemini returned no text ({reason}).{hint}")
    return text


def _mock(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None):
    lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
    question = (lines[-1] if lines else "").removeprefix("Frage:").removeprefix("Question:").strip()[:160]
    return f"[Mock response] Answered without a model key: “{question}”. With a key in .env.local, a real model responds."


def mock(prompt, system="", max_tokens=1024):
    """Explicit offline call, independent of keys and provider configuration."""
    return Answer(_mock(prompt, system, DEFAULT_MODELS["mock"], max_tokens), "mock", DEFAULT_MODELS["mock"], 0)


def _grokbot(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None, bilder=None):
    """File-queue provider: the job waits in GROKBOT_QUEUE_DIR for an assistant answer."""
    from . import grokbot
    data = grokbot.complete(prompt, system, chosen, max_tokens, json_mode=json_mode, timeout=timeout,
                            effort=effort, kind="complete", bilder=bilder)
    text = (data.get("text") or "").strip()
    if not text:
        raise LLMError("Grok Bot returned an empty answer.")
    return text


def _grokbot_research(prompt, system="", max_tokens=8000, *, timeout=None, effort=None, max_searches=5):
    from . import grokbot
    system = sprache.mit_hinweis(system)
    started = time.perf_counter()
    data = grokbot.complete(prompt, system, model("grokbot"), max_tokens, timeout=timeout, effort=effort,
                            kind="research", max_searches=max_searches)
    text = (data.get("text") or "").strip()
    if not text:
        raise LLMError("Grok Bot returned an empty research answer.")
    data["text"] = text
    return grokbot.antwort_zu_research(data, started, model("grokbot"))


@dataclass(frozen=True)
class JsonRequest:
    """One domain task with JSON input and an explicitly synthetic object fixture."""

    task: str
    input: dict
    mock_response: dict


@dataclass(frozen=True)
class StructuredAnswer:
    data: dict
    source: str
    input_hash: str
    cached: bool


class BudgetExceeded(LLMError):
    """The run has insufficient budget; no simulator call was made."""


def _json_object(value):
    """Canonicalize a JSON object without coercing non-string object keys."""
    def check(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError

    if not isinstance(value, dict):
        raise ValueError
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


class StructuredRun:
    """Offline JSON calls with a private, run-local cache.

    The optional simulator accepts (payloads, max_output_tokens) and returns one
    JSON object (or JSON object string) per payload. It is a synchronous test
    seam, never a legacy live adapter. One run belongs to one analysis; reuse it
    across steps to share cache and budget. Domain schema validation belongs to
    the caller. No confidential inputs are persisted.
    """

    def __init__(self, *, max_tokens=None, max_cost=None, batch_size=None,
                 simulator=None, cost_per_token=0):
        self.max_tokens = self._integer(
            max_tokens if max_tokens is not None else os.environ.get("LLM_RUN_MAX_TOKENS", "100000"),
            "LLM_RUN_MAX_TOKENS", minimum=0,
        )
        self.batch_size = self._integer(
            batch_size if batch_size is not None else os.environ.get("LLM_BATCH_SIZE", "20"),
            "LLM_BATCH_SIZE", minimum=1,
        )
        self.max_cost = self._decimal(
            max_cost if max_cost is not None else os.environ.get("LLM_RUN_MAX_COST", "0"),
            "LLM_RUN_MAX_COST",
        )
        self.cost_per_token = self._decimal(cost_per_token, "cost_per_token")
        self.simulator = simulator
        self._cache = {}
        self._reserved_tokens = 0
        self._reserved_cost = Decimal(0)
        self._lock = RLock()

    @staticmethod
    def _integer(value, name, *, minimum):
        try:
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError
            parsed = int(value)
            if parsed < minimum:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise LLMError(f"Invalid {name}; expected an integer >= {minimum}.") from None
        return parsed

    @staticmethod
    def _decimal(value, name):
        try:
            parsed = Decimal(str(value))
            if not parsed.is_finite() or parsed < 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise LLMError(f"Invalid {name}; expected a finite nonnegative amount.") from None
        return parsed

    @property
    def reserved_tokens(self):
        return self._reserved_tokens

    @property
    def reserved_cost(self):
        return self._reserved_cost

    def complete_batch(self, requests, max_output_tokens=1024):
        """Return ordered answers, or raise LLMError on invalid input/output/budget.

        Input UTF-8 bytes plus max_output_tokens per unique request are reserved
        before each batch, including failed calls. Output is conservatively
        limited to that many canonical JSON UTF-8 bytes. These are bounds for
        offline simulation, not a provider tokenizer or a live billing quote.
        Earlier successful batches stay cached if a later batch fails. Cache
        hits are free. Calls on a shared run are serialized to protect its cap.
        """
        with self._lock:
            return self._complete_batch(requests, max_output_tokens)

    def _complete_batch(self, requests, max_output_tokens):
        max_output_tokens = self._integer(max_output_tokens, "max_output_tokens", minimum=1)
        prepared = []
        pending = {}
        try:
            for request in requests:
                if (not isinstance(request, JsonRequest) or not isinstance(request.task, str)
                        or not request.task.strip()):
                    raise ValueError
                payload = _json_object({"task": request.task, "input": request.input})
                if not isinstance(request.input, dict):
                    raise ValueError
                fixture = _json_object(request.mock_response)
                identity = _json_object({"payload": json.loads(payload), "fixture": json.loads(fixture),
                                         "max_output_tokens": max_output_tokens})
                key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                prepared.append(key)
                if key not in self._cache:
                    pending[key] = (payload, fixture)
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise LLMError("Invalid structured JSON request.") from None

        fresh = set()
        items = list(pending.items())
        for start in range(0, len(items), self.batch_size):
            batch = items[start:start + self.batch_size]
            tokens = sum(len(payload.encode("utf-8")) + max_output_tokens
                         for _, (payload, _) in batch)
            cost = self.cost_per_token * tokens
            if (self._reserved_tokens + tokens > self.max_tokens
                    or self._reserved_cost + cost > self.max_cost):
                raise BudgetExceeded("LLM run budget exhausted; reduce input or start an approved run.")
            self._reserved_tokens += tokens
            self._reserved_cost += cost
            try:
                payloads = [json.loads(payload) for _, (payload, _) in batch]
                replies = (self.simulator(payloads, max_output_tokens) if self.simulator is not None
                           else [json.loads(fixture) for _, (_, fixture) in batch])
            except Exception:
                raise LLMError("Offline simulator failed; no retry was attempted.") from None
            try:
                if not isinstance(replies, list) or len(replies) != len(batch):
                    raise ValueError
                validated = {}
                for (key, _), reply in zip(batch, replies):
                    if isinstance(reply, str):
                        reply = json.loads(reply)
                    encoded = _json_object(reply)
                    if len(encoded.encode("utf-8")) > max_output_tokens:
                        raise ValueError
                    validated[key] = encoded
            except (TypeError, ValueError, OverflowError, RecursionError):
                raise LLMError("Invalid structured JSON response or output limit exceeded.") from None
            self._cache.update(validated)
            fresh.update(validated)

        answers = []
        for key in prepared:
            answers.append(StructuredAnswer(
                json.loads(self._cache[key]), "model_mock", key, key not in fresh,
            ))
            fresh.discard(key)
        return answers


# --- Research with web search (#166, package A; reused by #169 E) ------------------------------
# Claude's server tool `web_search` runs the searches on Anthropic's side; the answer carries
# citations (`web_search_result_location`: url, title, cited_text) on its text blocks. A long turn
# may stop with `stop_reason: pause_turn`; the paused answer is then sent back as-is to continue.
# Other providers have no server web search here: research() answers with complete() and no
# citations (`web_search=False`), so callers work the same on every provider and on the mock.

WEB_SEARCH_TOOL = "web_search_20250305"  # basic version, works on all Claude models
MAX_PAUSE_TURNS = 8  # continuations after pause_turn before the research gives up


@dataclass(frozen=True)
class Citation:
    """One web source: ``cited_text`` is the quoted passage (empty for a search hit Claude did not quote)."""
    url: str
    title: str
    cited_text: str = ""


@dataclass
class ResearchAnswer:
    """Text plus its web evidence. ``citations``: passages Claude quoted, in answer order, deduplicated.
    ``sources``: every search result Claude saw (url + title), a superset of the cited URLs.
    ``searches``: web searches the provider ran; ``web_search``: False when the provider has no web search."""
    text: str
    provider: str
    model: str
    ms: int
    citations: list = None
    sources: list = None
    searches: int = 0
    web_search: bool = False
    truncated: bool = False  # True when the model stopped at max_tokens but returned some text

    def __post_init__(self):
        self.citations = list(self.citations or [])
        self.sources = list(self.sources or [])


def research(prompt, system="", max_tokens=8000, *, max_searches=5, timeout=None, effort=None):
    """One model answer backed by web search, as a ResearchAnswer. Raises LLMError with a UI-safe message.

    ``max_searches`` caps the web searches of this call (tool ``max_uses``); ``timeout`` (seconds,
    default LLM_TIMEOUT) bounds the whole call including every pause_turn continuation. Claude only:
    other providers and the mock answer through complete() without citations.
    """
    name = provider()
    if name == "grokbot":
        return _grokbot_research(prompt, system, max_tokens, timeout=timeout, effort=effort,
                                 max_searches=max_searches)
    if name != "anthropic":
        answer = complete(prompt, system, max_tokens, timeout=timeout, effort=effort)
        return ResearchAnswer(answer.text, answer.provider, answer.model, answer.ms)
    chosen = model(name)
    if not env(KEY_FOR[name]):
        raise LLMError(f"Missing {KEY_FOR[name]} for {name}. Without a key, set LLM_PROVIDER=mock.")
    system = sprache.mit_hinweis(system)  # #196; the non-Claude path above gets it inside complete()
    limit = timeout if timeout and timeout > 0 else seconds()
    started = time.perf_counter()
    try:
        return _anthropic_research(prompt, system, chosen, max_tokens, max(1, int(max_searches)), limit, effort,
                                   started)
    except LLMError:
        raise
    except httpx.TimeoutException:
        raise LLMError(f"{name} did not finish the web research within {limit:g} s.") from None
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = ("Rate limit or free quota reached; wait a minute." if code == 429
                else "Check the key, model and credit, and that web search is enabled for the organisation.")
        raise LLMError(f"{name} returned HTTP {code}. {hint}") from None
    except httpx.HTTPError:
        raise LLMError(f"{name} is unreachable. Check the network or set LLM_PROVIDER=mock.") from None
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise LLMError(f"{name} returned an unexpected response.") from None


def _anthropic_research(prompt, system, chosen, max_tokens, max_searches, limit, effort, started):
    tool = {"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches}
    messages = [{"role": "user", "content": prompt}]
    payload = {"model": chosen, "max_tokens": max_tokens, "messages": messages, "tools": [tool]}
    if system:
        payload["system"] = system
    effort = (effort or env("ANTHROPIC_EFFORT")).lower()
    if effort in EFFORTS:
        payload["output_config"] = {"effort": effort}
    headers = {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    url = env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1/messages"
    texts, citations, sources, searches = [], {}, {}, 0
    for _ in range(MAX_PAUSE_TURNS + 1):
        remaining = limit - (time.perf_counter() - started)
        if remaining <= 0:
            raise LLMError(f"anthropic did not finish the web research within {limit:g} s.")
        data = _post(url, headers, payload, remaining)
        content = data["content"]
        searches += int(((data.get("usage") or {}).get("server_tool_use") or {}).get("web_search_requests") or 0)
        _collect_research(content, texts, citations, sources)
        stop = data.get("stop_reason")
        if stop == "pause_turn":  # the server paused a long turn: send it back unchanged to continue
            messages.append({"role": "assistant", "content": content})
            continue
        if stop == "refusal":
            category = (data.get("stop_details") or {}).get("category")
            raise LLMError(f"anthropic declined the request (refusal{': ' + category if category else ''}).")
        if stop == "max_tokens":
            text = "".join(texts).strip()
            if not text:
                raise LLMError(f"anthropic stopped at max_tokens ({max_tokens}); the research answer is incomplete.")
            return ResearchAnswer(text, "anthropic", chosen, round((time.perf_counter() - started) * 1000),
                                  list(citations.values()), list(sources.values()), searches, True,
                                  truncated=True)
        text = "".join(texts).strip()
        if not text:
            raise LLMError(f"anthropic returned no text ({stop or 'empty answer'}).")
        return ResearchAnswer(text, "anthropic", chosen, round((time.perf_counter() - started) * 1000),
                              list(citations.values()), list(sources.values()), searches, True)
    raise LLMError(f"anthropic paused the research more than {MAX_PAUSE_TURNS} times; no final answer.")


def _collect_research(content, texts, citations, sources):
    """Text, quoted passages and search hits of one answer chunk (accumulated across pause_turn)."""
    for block in content:
        kind = block.get("type")
        if kind == "text":
            texts.append(block.get("text", ""))
            for cite in block.get("citations") or []:
                if cite.get("type") == "web_search_result_location" and cite.get("url"):
                    entry = Citation(cite["url"], cite.get("title") or "", (cite.get("cited_text") or "").strip())
                    citations.setdefault((entry.url, entry.cited_text), entry)
        elif kind == "web_search_tool_result" and isinstance(block.get("content"), list):
            for hit in block["content"]:  # an error result is an object, not a list, and is skipped
                if hit.get("type") == "web_search_result" and hit.get("url"):
                    sources.setdefault(hit["url"], Citation(hit["url"], hit.get("title") or ""))
