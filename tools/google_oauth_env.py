#!/usr/bin/env python3
"""Write Google OAuth values from the client JSON downloaded in Google Cloud into web/.env.local.

    python3 tools/google_oauth_env.py ~/Downloads/client_secret_XXXX.json

Sets AUTH_GOOGLE_ID and AUTH_GOOGLE_SECRET, adds AUTH_SECRET (random) when missing and APP_URL
(http://localhost:3000) when missing. Every other line of web/.env.local is kept. Prints only "ok" -
never a value - and writes the file with mode 600. Delete the downloaded JSON afterwards.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

ZIEL = Path(__file__).resolve().parent.parent / "web" / ".env.local"


def werte_aus_json(pfad: Path) -> tuple[str, str]:
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    block = daten.get("web") or daten.get("installed") or daten
    cid, geheim = block.get("client_id"), block.get("client_secret")
    if not cid or not geheim:
        raise ValueError("client_id/client_secret missing in the JSON (expected the OAuth client download)")
    return str(cid).strip(), str(geheim).strip()


def zusammenfuehren(alt: str, neu: dict[str, str], nur_wenn_fehlt: dict[str, str]) -> str:
    zeilen = alt.splitlines()
    gesehen: set[str] = set()
    aus: list[str] = []
    for zeile in zeilen:
        name = zeile.split("=", 1)[0].strip() if "=" in zeile and not zeile.lstrip().startswith("#") else None
        if name in neu:
            if name in gesehen:
                continue  # drop duplicates of a key we set
            aus.append(f"{name}={neu[name]}")
            gesehen.add(name)
        elif name in nur_wenn_fehlt:
            wert = zeile.split("=", 1)[1].strip()
            if not wert:
                aus.append(f"{name}={nur_wenn_fehlt[name]}")
            else:
                aus.append(zeile)
            gesehen.add(name)
        else:
            aus.append(zeile)
    for name, wert in {**neu, **nur_wenn_fehlt}.items():
        if name not in gesehen:
            aus.append(f"{name}={wert}")
    return "\n".join(aus).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 tools/google_oauth_env.py <client_secret.json>", file=sys.stderr)
        return 2
    try:
        cid, geheim = werte_aus_json(Path(argv[1]).expanduser())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {type(exc).__name__}: could not read the client JSON", file=sys.stderr)
        return 1
    alt = ZIEL.read_text(encoding="utf-8") if ZIEL.exists() else ""
    text = zusammenfuehren(
        alt,
        {"AUTH_GOOGLE_ID": cid, "AUTH_GOOGLE_SECRET": geheim},
        {"AUTH_SECRET": secrets.token_hex(32), "APP_URL": "http://localhost:3000"},
    )
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = ZIEL.with_suffix(".local.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, ZIEL)
    os.chmod(ZIEL, 0o600)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
