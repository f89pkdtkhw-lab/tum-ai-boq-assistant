#!/usr/bin/env python3
"""Inspect and answer Grok Bot queue jobs written by the BoQ backend.

    python tools/grokbot_queue.py list
    python tools/grokbot_queue.py show <job_id>
    python tools/grokbot_queue.py answer <job_id> <file>

The queue directory is GROKBOT_QUEUE_DIR, or ~/boq-grokbot-queue by default.
See docs/grokbot-bridge.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from app.ai import grokbot  # noqa: E402


def _print(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def cmd_list(_args) -> int:
    jobs = grokbot.pending()
    if not jobs:
        _print(f"No pending jobs in {grokbot.inbox_dir()}.")
        return 0
    _print(f"{len(jobs)} pending job(s) in {grokbot.inbox_dir()}:")
    for job in jobs:
        kind = job.get("kind") or "?"
        created = job.get("created_at") or "?"
        prompt = (job.get("prompt") or "").replace("\n", " ").strip()
        if len(prompt) > 80:
            prompt = prompt[:77] + "..."
        _print(f"  {job.get('job_id')}  {kind}  {created}  {prompt}")
    return 0


def cmd_show(args) -> int:
    try:
        job = grokbot.load_job(args.job_id)
    except (FileNotFoundError, ValueError) as exc:
        _print(str(exc))
        return 1
    # Print a readable prompt first, then the raw job (no secrets are stored).
    _print(f"job_id:     {job.get('job_id')}")
    _print(f"kind:       {job.get('kind')}")
    _print(f"created_at: {job.get('created_at')}")
    hint = (job.get("expected_output") or {}).get("schema_hint")
    if hint:
        _print(f"answer as:  {hint}")
    if job.get("system"):
        _print("\n--- system ---\n" + job["system"])
    _print("\n--- prompt ---\n" + (job.get("prompt") or ""))
    if job.get("bilder"):
        _print("\n--- images ---\n" + "\n".join(job["bilder"]))
    return 0


def cmd_answer(args) -> int:
    path = Path(args.file)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        _print(f"Cannot read {path}: {exc}")
        return 1
    if not raw.strip():
        _print(f"{path} is empty.")
        return 1
    try:
        out = grokbot.write_answer(args.job_id, raw)
    except (FileNotFoundError, ValueError, OSError) as exc:
        _print(str(exc))
        return 1
    _print(f"Wrote {out} and moved the job to {grokbot.done_dir()}.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="pending jobs in the inbox")

    show = sub.add_parser("show", help="print the system prompt and user prompt of a job")
    show.add_argument("job_id")

    answer = sub.add_parser("answer", help="write a file into the outbox and mark the job done")
    answer.add_argument("job_id")
    answer.add_argument("file", help="JSON {\"text\": \"...\"} or plain text")

    args = parser.parse_args(argv)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "answer":
        return cmd_answer(args)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
