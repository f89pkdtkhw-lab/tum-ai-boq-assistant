"""Check this machine for teamwork and enable the push check.

    python tools/setup.py                 # Check and enable push check
    python tools/setup.py --kommentar 2   # Also report as a comment in issue #2

Requires only the Python standard library. Runs on Windows, macOS and Linux.
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
            for where in ["environment" if os.environ.get(name, "").strip() else ".env.local"]]


def setup_graphify():
    """Install the developer tool if missing and register its assistant skill.

    Never build a graph or send repository content to a model during setup.
    """
    executable = shutil.which("graphify")
    if executable is None:
        installer = next((name for name in ("uv", "pipx") if shutil.which(name)), None)
        if installer is None:
            return "fail", "MISSING: graphify; install uv or pipx, then rerun setup"
        command = (installer, "tool", "install", "graphifyy") if installer == "uv" else (installer, "install", "graphifyy")
        code, _ = run(*command, timeout=180)
        if code:
            return "fail", f"graphifyy installation using {installer} failed; install manually and rerun setup"
        executable = shutil.which("graphify")
        if executable is None:
            return "fail", "MISSING: graphify not on PATH after installation; add the tool bin directory and rerun setup"
    code, _ = run(executable, "--version")
    if code:
        return "fail", "cannot start graphify; check installation and rerun setup"
    code, _ = run(executable, "install", timeout=60)
    if code:
        return "fail", "graphify install failed; register the assistant skill manually and rerun setup"
    return "ok", "graphify available, assistant skill registered (use code only)"


def check(fix_hooks=True):
    """Return (rows, facts). A row is (status, label, detail) with status ok, warn or fail."""
    rows, facts = [], {"System": operating_system()}

    version = sys.version_info[:3]
    facts["Python"] = ".".join(map(str, version))
    rows.append(("ok" if version >= MIN_PYTHON else "fail", "Python",
                 facts["Python"] if version >= MIN_PYTHON else f"{facts['Python']}, please use Python 3.11 or newer"))

    code, out = run("git", "--version")
    if code:
        rows.append(("fail", "Git", "not found, please install Git"))
        return rows, facts
    rows.append(("ok", "Git", out.replace("git version ", "")))
    _, branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    _, commit = run("git", "rev-parse", "--short", "HEAD")
    facts["Branch"], facts["Commit"] = branch, commit
    rows.append(("ok", "Revision", f"{branch} @ {commit}"))

    hook = ROOT / "tools" / "hooks" / "pre-push"
    if hook.is_file():
        if fix_hooks:
            run("git", "config", "--local", "core.hooksPath", "tools/hooks")
        _, hooks_path = run("git", "config", "--get", "core.hooksPath")
        active = hooks_path.replace("\\", "/").rstrip("/") == "tools/hooks"
        rows.append(("ok" if active else "warn", "Push check",
                     "enabled: tests run before every push" if active else "disabled, run python tools/setup.py"))

    if shutil.which("gh") is None:
        rows.append(("warn", "GitHub CLI", "not found, install https://cli.github.com"))
    else:
        code, login = run("gh", "api", "user", "--jq", ".login", timeout=20)
        if code:
            rows.append(("warn", "GitHub CLI", "not signed in, run gh auth login"))
        else:
            facts["GitHub"] = login
            _, permission = run("gh", "repo", "view", "--json", "viewerPermission", "--jq", ".viewerPermission",
                                timeout=20)
            can_push = permission in {"WRITE", "MAINTAIN", "ADMIN"}
            facts["Write access"] = "yes" if can_push else f"no ({permission or 'unknown'})"
            rows.append(("ok" if can_push else "warn", "GitHub access",
                         f"{login}, Write access {facts['Write access']}"
                         + ("" if can_push else ": accept invitation or ask integration")))
            code, out = run(sys.executable, str(ROOT / "tools" / "board.py"), "whoami", timeout=30)
            facts["Team board"] = "reachable" if code == 0 else "unreachable"
            rows.append(("ok" if code == 0 else "warn", "Team board", out.splitlines()[-1] if out else "no response"))

    status, detail = setup_graphify()
    facts["Graphify"] = detail
    rows.append((status, "Graphify", detail))

    keys = key_status()
    facts["Keys"] = ", ".join(keys) or "none (product uses mock)"
    rows.append(("ok", "Model access", facts["Keys"]))

    found = [name for name, commands in AGENT_COMMANDS.items() if any(shutil.which(c) for c in commands)]
    if (Path.home() / "firstmate" / "AGENTS.md").is_file():
        found.append("FirstMate")
    facts["Agents"] = ", ".join(found) or "none on PATH"
    rows.append(("ok" if found else "warn", "Coding agents", facts["Agents"]
                 + ("" if found else " (Antigravity and Codex apps still count)")))

    code, out = run(sys.executable, "-m", "unittest", "discover", "-s", "tests", timeout=180)
    summary = next((line for line in reversed(out.splitlines()) if line.startswith("Ran ")), "no tests found")
    facts["Tests"] = f"{summary}, {'OK' if code == 0 else 'FAILED'}"
    rows.append(("ok" if code == 0 else "fail", "Tests", facts["Tests"]))
    if code:
        rows.append(("fail", "Test output", "\n".join(out.splitlines()[-15:])))
    return rows, facts


def report(facts):
    lines = ["**Machine check** (`python tools/setup.py`)", ""]
    lines += [f"- {key}: {value}" for key, value in facts.items()]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kommentar", type=int, metavar="ISSUE", help="post result as a comment in this issue")
    parser.add_argument("--ohne-hook", action="store_true", help="do not enable push check")
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
        print(f"\nComment on issue #{args.kommentar}: {'saved' if code == 0 else out}")
    return 1 if any(status == "fail" for status, _, _ in rows) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
