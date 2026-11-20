"""One interface for all model providers that may be available at the competition.

Select through environment variables (see .env.example):
    LLM_PROVIDER   anthropic | openai | azure | gemini | mock   (empty = first provider with a key, otherwise mock)
    LLM_MODEL      Model name; defaults to a provider-specific model when omitted

`mock` runs without network access or keys so the demo and tests always start.
Keys never leave the server and never appear in error messages.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import time
from threading import RLock

import httpx

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "",
    "azure": "",
    "gemini": "gemini-2.5-flash",
    "mock": "mock",
}
KEY_FOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "azure": "AZURE_OPENAI_API_KEY",
           "gemini": "GEMINI_API_KEY"}
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))


class LLMError(Exception):
    """A message that is safe to show in the UI."""


@dataclass
class Answer:
    text: str
    provider: str
    model: str
    ms: int


def env(name):
    return os.environ.get(name, "").strip()


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


def complete(prompt, system="", max_tokens=1024):
    name = provider()
    chosen = model(name)
    started = time.perf_counter()
    if name != "mock" and not env(KEY_FOR[name]):
        raise LLMError(f"Missing {KEY_FOR[name]} for {name}. Without a key, set LLM_PROVIDER=mock.")
    if not chosen:
        raise LLMError(f"Set LLM_MODEL for {name} (model name from the provider documentation).")
    try:
        text = {"anthropic": _anthropic, "openai": _openai, "azure": _azure, "gemini": _gemini, "mock": _mock}[name](
            prompt, system, chosen, max_tokens)
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"{name} returned HTTP {exc.response.status_code}. Check the key, model and credit.") from None
    except httpx.HTTPError:
        raise LLMError(f"{name} is unreachable. Check the network or set LLM_PROVIDER=mock.") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise LLMError(f"{name} returned an unexpected response.") from None
    return Answer(text.strip(), name, chosen, round((time.perf_counter() - started) * 1000))


def _post(url, headers, payload):
    response = httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _anthropic(prompt, system, chosen, max_tokens):
    payload = {"model": chosen, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    data = _post(env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1/messages",
                 {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}, payload)
    return "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")


def _chat_messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def _openai(prompt, system, chosen, max_tokens):
    base = (env("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    data = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
                 {"model": chosen, "messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens})
    return data["choices"][0]["message"]["content"]


def _azure(prompt, system, chosen, max_tokens):
    endpoint = env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not endpoint or not chosen:
        raise LLMError("For azure, set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT.")
    version = env("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    data = _post(f"{endpoint}/openai/deployments/{chosen}/chat/completions?api-version={version}",
                 {"api-key": env("AZURE_OPENAI_API_KEY")},
                 {"messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens})
    return data["choices"][0]["message"]["content"]


def _gemini(prompt, system, chosen, max_tokens):
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{chosen}:generateContent",
                 {"x-goog-api-key": env("GEMINI_API_KEY")}, payload)
    return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])


def _mock(prompt, system, chosen, max_tokens):
    lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
    question = (lines[-1] if lines else "").removeprefix("Frage:").strip()[:160]
    return f"[Mock response] Answered without a model key: “{question}”. With a key in .env.local, a real model responds."


def mock(prompt, system="", max_tokens=1024):
    """Explicit offline call, independent of keys and provider configuration."""
    return Answer(_mock(prompt, system, DEFAULT_MODELS["mock"], max_tokens), "mock", DEFAULT_MODELS["mock"], 0)


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
