"""Prüft diesen Rechner für die Teamarbeit und aktiviert den Push-Check.

    python tools/setup.py                 # prüfen und Push-Check aktivieren
    python tools/setup.py --kommentar 2   # Ergebnis zusätzlich als Kommentar in Issue #2

Braucht nur die Python-Standardbibliothek. Läuft auf Windows, macOS und Linux.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 11)
AGENT_COMMANDS = {
    "Claude Code": ("claude",),
    "Codex": ("codex",),
    "Antigravity": ("antigravity", "antigravity-ide", "agy"),
    "Gemini CLI": ("gemini",),
}


def run(*command, timeout=60, stdin=None):
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, input=stdin)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def operating_system():
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]} ({platform.machine()})"
    if sys.platform == "win32":
        return f"Windows {platform.release()} ({platform.version()})"
    return f"{platform.system()} {platform.release()}"


KEY_NAMES = {"ANTHROPIC_API_KEY": "Anthropic", "OPENAI_API_KEY": "OpenAI", "AZURE_OPENAI_API_KEY": "Azure OpenAI",
             "GEMINI_API_KEY": "Gemini"}


def key_status(env_file=None):
    """Which provider keys exist in the environment or .env.local; never returns a value."""
    env_file = env_file or ROOT / ".env.local"
    present = {name for name in KEY_NAMES if os.environ.get(name, "").strip()}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() in KEY_NAMES and value.strip().strip("\"'"):
                present.add(name.strip())
    return [f"{KEY_NAMES[name]} ({where})" for name in KEY_NAMES if name in present
            for where in ["Umgebung" if os.environ.get(name, "").strip() else ".env.local"]]


def check(fix_hooks=True):
    """Return (rows, facts). A row is (status, label, detail) with status ok, warn or fail."""
    rows, facts = [], {"System": operating_system()}

    version = sys.version_info[:3]
    facts["Python"] = ".".join(map(str, version))
    rows.append(("ok" if version >= MIN_PYTHON else "fail", "Python",
                 facts["Python"] if version >= MIN_PYTHON else f"{facts['Python']}, bitte Python 3.11 oder neuer"))

    code, out = run("git", "--version")
    if code:
        rows.append(("fail", "Git", "nicht gefunden, bitte Git installieren"))
        return rows, facts
    rows.append(("ok", "Git", out.replace("git version ", "")))
    _, branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    _, commit = run("git", "rev-parse", "--short", "HEAD")
    facts["Branch"], facts["Commit"] = branch, commit
    rows.append(("ok", "Arbeitsstand", f"{branch} @ {commit}"))

    hook = ROOT / "tools" / "hooks" / "pre-push"
    if hook.is_file():
        if fix_hooks:
            run("git", "config", "--local", "core.hooksPath", "tools/hooks")
        _, hooks_path = run("git", "config", "--get", "core.hooksPath")
        active = hooks_path.replace("\\", "/").rstrip("/") == "tools/hooks"
        rows.append(("ok" if active else "warn", "Push-Check",
                     "aktiv: Tests laufen vor jedem Push" if active else "aus, python tools/setup.py ausführen"))

    if shutil.which("gh") is None:
        rows.append(("warn", "GitHub CLI", "nicht gefunden, https://cli.github.com installieren"))
    else:
        code, login = run("gh", "api", "user", "--jq", ".login", timeout=20)
        if code:
            rows.append(("warn", "GitHub CLI", "nicht angemeldet, gh auth login ausführen"))
        else:
            facts["GitHub"] = login
            _, permission = run("gh", "repo", "view", "--json", "viewerPermission", "--jq", ".viewerPermission",
                                timeout=20)
            can_push = permission in {"WRITE", "MAINTAIN", "ADMIN"}
            facts["Schreibrecht"] = "ja" if can_push else f"nein ({permission or 'unbekannt'})"
            rows.append(("ok" if can_push else "warn", "GitHub-Zugang",
                         f"{login}, Schreibrecht {facts['Schreibrecht']}"
                         + ("" if can_push else ": Einladung annehmen oder Integration fragen")))
            code, out = run(sys.executable, str(ROOT / "tools" / "board.py"), "whoami", timeout=30)
            facts["Team-Board"] = "erreichbar" if code == 0 else "nicht erreichbar"
            rows.append(("ok" if code == 0 else "warn", "Team-Board", out.splitlines()[-1] if out else "keine Antwort"))

    keys = key_status()
    facts["Schlüssel"] = ", ".join(keys) or "keine (Produkt läuft im Mock)"
    rows.append(("ok", "Modell-Zugänge", facts["Schlüssel"]))

    found = [name for name, commands in AGENT_COMMANDS.items() if any(shutil.which(c) for c in commands)]
    if (Path.home() / "firstmate" / "AGENTS.md").is_file():
        found.append("FirstMate")
    facts["Agenten"] = ", ".join(found) or "keiner im PATH"
    rows.append(("ok" if found else "warn", "Coding-Agenten", facts["Agenten"]
                 + ("" if found else " (Antigravity-App und Codex-App zählen trotzdem)")))

    code, out = run(sys.executable, "-m", "unittest", "discover", "-s", "tests", timeout=180)
    summary = next((line for line in reversed(out.splitlines()) if line.startswith("Ran ")), "keine Tests gefunden")
    facts["Tests"] = f"{summary}, {'OK' if code == 0 else 'FEHLER'}"
    rows.append(("ok" if code == 0 else "fail", "Tests", facts["Tests"]))
    if code:
        rows.append(("fail", "Testausgabe", "\n".join(out.splitlines()[-15:])))
    return rows, facts


def report(facts):
    lines = ["**Rechner-Check** (`python tools/setup.py`)", ""]
    lines += [f"- {key}: {value}" for key, value in facts.items()]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kommentar", type=int, metavar="ISSUE", help="Ergebnis als Kommentar in dieses Issue")
    parser.add_argument("--ohne-hook", action="store_true", help="Push-Check nicht aktivieren")
    args = parser.parse_args()

    rows, facts = check(fix_hooks=not args.ohne_hook)
    marks = {"ok": "✓", "warn": "!", "fail": "✗"}
    for status, label, detail in rows:
        print(f"{marks[status]} {label:<15} {detail}")
    print()
    print(report(facts))

    if args.kommentar:
        code, out = run("gh", "issue", "comment", str(args.kommentar), "--body-file", "-",
                        stdin=report(facts), timeout=30)
        print(f"\nKommentar in Issue #{args.kommentar}: {'gespeichert' if code == 0 else out}")
    return 1 if any(status == "fail" for status, _, _ in rows) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
