"""Beginnt ein GitHub-Issue auf eigenem Branch und Worktree und schreibt den Agentenauftrag.

    python tools/aufgabe.py 7                  # Worktree neben dem Repo, Branch 7-<kurzname>
    python tools/aufgabe.py 7 --uebernehmen    # zusätzlich zuweisen und Übernahme kommentieren
    python tools/aufgabe.py 7 --hier           # ohne Worktree im aktuellen Ordner

Danach den angezeigten Ordner in Claude Code, Codex oder Antigravity öffnen und schreiben:
„Lies .auftrag.md und setze den Auftrag um.“
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KNOWN_BASES = ("main",)
EMPTY = {"", "_No response_", "keine", "-", "–"}
PROMPT = "Lies .auftrag.md und setze den Auftrag um."
MODELS = json.loads((ROOT / "tools" / "modelle.json").read_text(encoding="utf-8"))["klassen"]


def model_class(labels):
    """Pick the model class from a modell:<klasse> label; without one, the standard class."""
    for label in labels or []:
        name = (label.get("name") if isinstance(label, dict) else label) or ""
        if name.startswith("modell:") and name[7:] in MODELS:
            return name[7:]
    return "standard"


def launch_commands(klasse):
    models = MODELS[klasse]
    commands = {"Claude Code": f'claude --model {models["claude"]} "{PROMPT}"' if models.get("claude") else None,
                "Codex": f'codex -m {models["codex"]} "{PROMPT}"' if models.get("codex") else None}
    return {tool: command for tool, command in commands.items() if command}


class Stop(Exception):
    """A message for the person running the script."""


def run(*command, cwd=ROOT, check=True):
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and done.returncode:
        raise Stop(f"{' '.join(command)} schlug fehl:\n{(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def parse_form(body):
    """Read the '### Heading' sections that GitHub issue forms and our skill write."""
    fields, heading, lines = {}, None, []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if line.startswith("### "):
            if heading is not None:
                fields[heading] = "\n".join(lines).strip()
            heading, lines = line[4:].strip(), []
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        fields[heading] = "\n".join(lines).strip()
    return {key: value for key, value in fields.items() if value not in EMPTY}


def base_branch(fields, body):
    value = fields.get("Zielbranch", "").strip().strip("`").strip()
    if re.fullmatch(r"[A-Za-z0-9._/-]+", value):
        return value
    for name in KNOWN_BASES:
        if re.search(rf"(?<![\w/-]){re.escape(name)}(?![\w/-])", body or ""):
            return name
    return None


def branch_name(number, title):
    tail = re.split(r"[:·]", title or "")[-1].strip() or title or ""
    text = tail.lower()
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(slug) > 40:
        slug = slug[:40].rsplit("-", 1)[0]
    return f"{number}-{slug}" if slug else str(number)


def assignment(issue, fields, branch, base):
    number = issue["number"]
    klasse = model_class(issue.get("labels"))
    models = MODELS[klasse]

    def field(name, fallback="siehe Issue-Text unten"):
        return fields.get(name, fallback)

    return "\n".join([
        f"# Auftrag aus Issue #{number}: {issue['title']}",
        "",
        f"Bearbeite Issue #{number} ({issue.get('url', '')}) auf Branch `{branch}`. "
        f"Der Pull Request geht auf `{base}`. Halte dich an `AGENTS.md`.",
        "",
        f"- **Verantwortlich:** {field('Verantwortliche Person')}",
        f"- **Bereich, nur diese Dateien ändern:** {field('Bereich')}",
        f"- **Werkzeug:** {field('Werkzeug', 'egal')}",
        f"- **Schnittstellen und Abhängigkeiten:** {field('Schnittstellen und Abhängigkeiten', 'keine genannt')}",
        f"- **Modellklasse:** `{klasse}` ({models['beschreibung']}): Claude `{models.get('claude') or '–'}`, "
        f"Codex `{models.get('codex') or '–'}`. Läufst du mit einem anderen Modell, sag es im Pull Request.",
        "",
        "## Ergebnis und Abnahmetest",
        "",
        field("Ergebnis und Abnahmetest"),
        "",
        "## So schließt du ab",
        "",
        "1. Teste mit `python -m unittest discover -s tests -v` und spiele das Abnahmebeispiel durch.",
        "2. Lies vorher `tools/board unread`; Änderungen an fremden Dateien oder geteilten Schnittstellen "
        "erst auf dem Board abstimmen.",
        f"3. `git fetch`, `git rebase origin/{base}`, pushen und Pull Request auf `{base}` mit `Closes #{number}` öffnen.",
        "4. Berichte Ergebnis, ausgeführte Tests und offene Punkte im Pull Request.",
        "5. Unter FirstMate öffnest du den fertigen PR; der First Mate mergt nach grünen Checks. "
        "Sonst merge selbst: `gh pr checks --watch`, dann `gh pr merge --squash --delete-branch`.",
        "6. Ändert der Merge eine geteilte Schnittstelle, poste es mit `@all` auf dem Board (`tools/board post`).",
        "",
        "## Issue-Text",
        "",
        (issue.get("body") or "").strip() or "(leer)",
        "",
    ])


def prepare(number, base_override=None, here=False):
    issue = json.loads(run("gh", "issue", "view", str(number), "--json", "number,title,body,url,state,labels"))
    if issue.get("state") != "OPEN":
        raise Stop(f"Issue #{number} ist nicht offen.")
    fields = parse_form(issue.get("body"))
    base = base_override or base_branch(fields, issue.get("body"))
    if not base:
        raise Stop(f"Issue #{number} nennt keinen Zielbranch. Ergänze ihn im Issue oder nutze --basis main.")
    branch = branch_name(number, issue["title"])
    run("git", "fetch", "origin", base)
    has_branch = bool(run("git", "branch", "--list", branch))

    if here:
        if run("git", "status", "--porcelain"):
            raise Stop("Im aktuellen Ordner gibt es ungesicherte Änderungen. Erst committen oder --hier weglassen.")
        if has_branch:
            run("git", "switch", branch)
        else:
            run("git", "switch", "-c", branch, f"origin/{base}")
        folder = ROOT
    else:
        folder = ROOT.parent / f"{ROOT.name}-{number}"
        if not folder.exists():
            if has_branch:
                run("git", "worktree", "add", str(folder), branch)
            else:
                run("git", "worktree", "add", "-b", branch, str(folder), f"origin/{base}")
    (folder / ".auftrag.md").write_text(assignment(issue, fields, branch, base), encoding="utf-8")
    return issue, fields, branch, base, folder


def claim(number, branch, tool):
    login = run("gh", "api", "user", "--jq", ".login")
    run("gh", "issue", "edit", str(number), "--add-assignee", "@me")
    run("gh", "issue", "comment", str(number), "--body",
        f"Übernommen von @{login} mit {tool} auf Branch `{branch}`.")
    board = subprocess.run([sys.executable, str(ROOT / "tools" / "board.py"), "post",
                            f"[{login} · {tool}] übernimmt #{number} auf Branch `{branch}`."],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if board.returncode:
        print(f"! Board-Post nicht möglich: {(board.stderr or board.stdout).strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("issue", type=int, help="Nummer des GitHub-Issues")
    parser.add_argument("--basis", help="Zielbranch, falls das Issue keinen nennt")
    parser.add_argument("--hier", action="store_true", help="ohne Worktree im aktuellen Ordner arbeiten")
    parser.add_argument("--uebernehmen", action="store_true", help="dich zuweisen und Übernahme kommentieren")
    parser.add_argument("--werkzeug", help="z. B. Claude Code, Codex oder Antigravity (für den Kommentar)")
    args = parser.parse_args()
    try:
        issue, fields, branch, base, folder = prepare(args.issue, args.basis, args.hier)
        if args.uebernehmen:
            claim(args.issue, branch, args.werkzeug or fields.get("Werkzeug", "einem Coding-Agenten"))
    except Stop as exc:
        print(f"✗ {exc}")
        return 1
    print(f"✓ Issue #{issue['number']}: {issue['title']}")
    print(f"✓ Ordner {folder}")
    print(f"✓ Branch {branch}, Pull Request später auf {base}")
    print(f"✓ Auftrag in {folder / '.auftrag.md'}")
    print()
    klasse = model_class(issue.get("labels"))
    print(f'Nächster Schritt: cd "{folder}", dann je nach Werkzeug (Modellklasse {klasse}: {MODELS[klasse]["beschreibung"]})')
    for tool, command in launch_commands(klasse).items():
        print(f"  {tool + ':':<13} {command}")
    print(f"  Antigravity:  den Ordner öffnen und in den Agent-Chat schreiben: {PROMPT}")
    print()
    print(f"Am Ende: git push -u origin {branch}, danach Pull Request auf {base} mit Closes #{issue['number']}.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
