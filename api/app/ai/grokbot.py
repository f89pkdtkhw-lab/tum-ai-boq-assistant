"""File-queue bridge so a Grok Bot can answer model calls without a provider API key.

When ``LLM_PROVIDER=grokbot``, ``complete()`` / ``research()`` write a job to
``GROKBOT_QUEUE_DIR`` (default ``~/boq-grokbot-queue``) and wait for the matching
outbox file. The answer text is returned like a normal model response so downstream
JSON parsing keeps working. No API keys are written to the queue.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..fortschritt import AnalyseAbgebrochen, warte as fortschritt_warte

# Imported lazily-facing names used by llm.py; LLMError is imported inside helpers
# to keep this module importable from the CLI without pulling the HTTP stack first
# when only path helpers are needed. llm.LLMError is used at call time.

DEFAULT_QUEUE = Path.home() / "boq-grokbot-queue"
DEFAULT_TIMEOUT = 900.0  # 15 minutes
DEFAULT_POLL = 2.0
WARTET = "Wartet auf Grok Bot …"
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
PROVIDERS = ("anthropic", "mock", "grokbot")


def queue_dir(path=None) -> Path:
    raw = path or os.environ.get("GROKBOT_QUEUE_DIR", "").strip() or str(DEFAULT_QUEUE)
    return Path(raw).expanduser().resolve()


def inbox_dir(root=None) -> Path:
    return (root or queue_dir()) / "inbox"


def outbox_dir(root=None) -> Path:
    return (root or queue_dir()) / "outbox"


def done_dir(root=None) -> Path:
    return inbox_dir(root) / "done"


def wartezeit(timeout=None) -> float:
    """Seconds to wait for an answer file. The call's own LLM timeout is ignored:

    Grok Bot answers are written by a person or assistant and need minutes, not
    the 60–90 s HTTP limit of a provider API. Override with GROKBOT_TIMEOUT.
    """
    from .llm import seconds
    del timeout  # the provider HTTP timeout must not cut the queue short
    return seconds("GROKBOT_TIMEOUT", DEFAULT_TIMEOUT)


def poll_interval() -> float:
    from .llm import seconds
    return min(wartezeit(), seconds("GROKBOT_POLL", DEFAULT_POLL))


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, text: str) -> None:
    _ensure(path.parent)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            if not text.endswith("\n"):
                file.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _job_path(root: Path, job_id: str) -> Path:
    if not JOB_ID.match(job_id):
        raise ValueError(f"Invalid job id {job_id!r}.")
    return inbox_dir(root) / f"{job_id}.json"


def _out_path(root: Path, job_id: str) -> Path:
    if not JOB_ID.match(job_id):
        raise ValueError(f"Invalid job id {job_id!r}.")
    return outbox_dir(root) / f"{job_id}.json"


def pending(root=None) -> list[dict]:
    """Inbox jobs that do not yet have an outbox answer, newest first."""
    root = root or queue_dir()
    jobs = []
    folder = inbox_dir(root)
    if not folder.is_dir():
        return []
    for path in folder.glob("*.json"):
        if not JOB_ID.match(path.stem):
            continue
        if _out_path(root, path.stem).exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"job_id": path.stem, "kind": "?", "error": "unreadable job file"}
        data.setdefault("job_id", path.stem)
        data["_path"] = str(path)
        jobs.append(data)
    jobs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return jobs


def load_job(job_id: str, root=None) -> dict:
    root = root or queue_dir()
    path = _job_path(root, job_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"No pending job {job_id} in {inbox_dir(root)}.") from None
    except ValueError:
        raise ValueError(f"Job {job_id} is not valid JSON.") from None
    data.setdefault("job_id", job_id)
    data["_path"] = str(path)
    return data


def write_answer(job_id: str, payload, root=None) -> Path:
    """Write the outbox answer and move the inbox job to inbox/done/. Returns the outbox path."""
    root = root or queue_dir()
    inbox = _job_path(root, job_id)
    if not inbox.exists():
        raise FileNotFoundError(f"No pending job {job_id} in {inbox_dir(root)}.")
    body = _normalize_answer(payload)
    out = _out_path(root, job_id)
    _atomic_write(out, json.dumps(body, ensure_ascii=False, indent=2))
    target = _ensure(done_dir(root)) / inbox.name
    try:
        os.replace(inbox, target)
    except OSError:
        # done/ on another filesystem: copy then drop
        target.write_text(inbox.read_text(encoding="utf-8"), encoding="utf-8")
        inbox.unlink(missing_ok=True)
    return out


def _normalize_answer(payload) -> dict:
    """Accept a dict, a JSON string, or raw text and return ``{"text": ...}`` plus extras."""
    if isinstance(payload, dict):
        data = dict(payload)
    elif isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
        data = None
    else:
        data = None
        payload = str(payload)
    if data is None:
        text = payload.strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and ("text" in parsed or "citations" in parsed):
            data = parsed
        else:
            return {"text": text}
    text = data.get("text")
    if text is None:
        # The file is the model JSON itself (the structure the prompt asked for).
        data = {"text": json.dumps(data, ensure_ascii=False)}
    elif not isinstance(text, str):
        data["text"] = json.dumps(text, ensure_ascii=False)
    return data


def read_answer(job_id: str, root=None) -> dict:
    path = _out_path(root or queue_dir(), job_id)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"No answer for job {job_id} in {outbox_dir(root)}.") from None
    return _normalize_answer(raw)


def _schema_hint(kind: str, json_mode: bool) -> str:
    if kind == "research":
        return (
            "Write outbox/<job_id>.json as "
            '{"text": "...", "citations": [{"url": "", "title": "", "cited_text": ""}], '
            '"sources": [{"url": "", "title": ""}], "searches": 0, "web_search": true}. '
            "text is required; the other fields are optional."
        )
    if json_mode:
        return (
            "The prompt asks for a JSON object. Write outbox/<job_id>.json as "
            '{"text": "{...the JSON object as a string...}"} so parsers read Answer.text.'
        )
    return 'Write outbox/<job_id>.json as {"text": "..."}. text is the model answer.'


def build_job(kind, prompt, system="", max_tokens=1024, *, json_mode=False, effort=None,
              timeout=None, max_searches=None, bilder_pfade=None) -> dict:
    job_id = uuid.uuid4().hex
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt},
    ]
    return {
        "job_id": job_id,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "system": system or "",
        "prompt": prompt,
        "messages": messages,
        "expected_output": {
            "format": "research" if kind == "research" else ("json" if json_mode else "text"),
            "schema_hint": _schema_hint(kind, json_mode),
            "json_mode": bool(json_mode),
        },
        "model_params": {
            "max_tokens": max_tokens,
            "timeout": timeout,
            "effort": effort,
            "json_mode": bool(json_mode),
            "max_searches": max_searches,
        },
        "bilder": list(bilder_pfade or []),
    }


def _write_bilder(root: Path, job_id: str, bilder) -> list[str]:
    if not bilder:
        return []
    folder = _ensure(inbox_dir(root) / f"{job_id}.media")
    pfade = []
    for index, roh in enumerate(bilder, start=1):
        path = folder / f"page-{index:02d}.jpg"
        path.write_bytes(roh)
        pfade.append(str(path))
    return pfade


def enqueue(kind, prompt, system="", max_tokens=1024, *, json_mode=False, effort=None,
            timeout=None, max_searches=None, bilder=None, root=None) -> dict:
    root = root or queue_dir()
    _ensure(inbox_dir(root))
    _ensure(outbox_dir(root))
    job = build_job(kind, prompt, system, max_tokens, json_mode=json_mode, effort=effort,
                    timeout=timeout, max_searches=max_searches)
    job["bilder"] = _write_bilder(root, job["job_id"], bilder)
    _atomic_write(_job_path(root, job["job_id"]), json.dumps(job, ensure_ascii=False, indent=2))
    return job


def complete(prompt, system="", chosen="grok-bot", max_tokens=1024, json_mode=False,
             timeout=None, effort=None, kind="complete", max_searches=None, bilder=None):
    """Write a job, poll the outbox, return the answer text (and extras for research)."""
    from .llm import LLMError

    root = queue_dir()
    limit = wartezeit(timeout)
    poll = poll_interval()
    try:
        job = enqueue(kind, prompt, system, max_tokens, json_mode=json_mode, effort=effort,
                      timeout=limit, max_searches=max_searches, bilder=bilder, root=root)
    except OSError as exc:
        raise LLMError(f"Could not write a Grok Bot job under {root}: {exc}.") from None
    job_id = job["job_id"]
    out = _out_path(root, job_id)
    deadline = time.monotonic() + limit
    try:
        while True:
            try:
                fortschritt_warte(WARTET)
            except AnalyseAbgebrochen:
                raise LLMError(f"The analysis stopped while waiting for Grok Bot (job {job_id}).") from None
            if out.exists():
                try:
                    return read_answer(job_id, root)
                except ValueError:
                    raise LLMError(f"Grok Bot wrote an unreadable answer for job {job_id}.") from None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMError(
                    f"Grok Bot did not answer within {limit:g} s (job {job_id}). "
                    f"Put the answer in {out}."
                )
            time.sleep(min(poll, remaining))
    except LLMError:
        raise
    except OSError as exc:
        raise LLMError(f"Grok Bot queue error while waiting for job {job_id}: {exc}.") from None


def antwort_zu_research(data: dict, started: float, chosen="grok-bot"):
    from .llm import Citation, ResearchAnswer

    def _cite(item, with_text=True):
        if not isinstance(item, dict) or not item.get("url"):
            return None
        return Citation(str(item["url"]), str(item.get("title") or ""),
                        (str(item.get("cited_text") or "").strip() if with_text else ""))

    citations = [c for c in (_cite(item) for item in (data.get("citations") or [])) if c]
    sources = [c for c in (_cite(item, with_text=False) for item in (data.get("sources") or [])) if c]
    searches = data.get("searches") or 0
    try:
        searches = int(searches)
    except (TypeError, ValueError):
        searches = 0
    ms = round((time.perf_counter() - started) * 1000)
    return ResearchAnswer(
        str(data.get("text") or "").strip(), "grokbot", chosen, ms,
        citations, sources, searches, bool(data.get("web_search") or citations or sources),
    )
