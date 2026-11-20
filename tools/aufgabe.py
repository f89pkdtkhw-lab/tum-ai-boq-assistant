"""Start a GitHub issue on its own branch and worktree and write the agent assignment.

    python tools/aufgabe.py 7                  # Worktree beside the repository, branch 7-<short-name>
    python tools/aufgabe.py 7 --uebernehmen    # Also assign and comment on the claim
    python tools/aufgabe.py 7 --hier           # Without a worktree in the current folder

Then open the displayed folder in Claude Code, Codex or Antigravity and say:
“Read .auftrag.md and implement the task.”
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KNOWN_BASES = ("main",)
EMPTY = {"", "_No response_", "keine", "none", "-", "–"}
PROMPT = "Read .auftrag.md and implement the task."
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
        raise Stop(f"{' '.join(command)} failed:\n{(done.stderr or done.stdout).strip()}")
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
    value = fields.get("Target branch", fields.get("Zielbranch", "")).strip().strip("`").strip()
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

    def field(name, fallback="see issue text below"):
        legacy = {"Owner": "Verantwortliche Person", "Scope": "Bereich", "Tool": "Werkzeug",
                  "Outcome and acceptance test": "Ergebnis und Abnahmetest",
                  "Interfaces and dependencies": "Schnittstellen und Abhängigkeiten"}
        return fields.get(name, fields.get(legacy.get(name), fallback))

    return "\n".join([
        f"# Task from issue #{number}: {issue['title']}",
        "",
        f"Implement issue #{number} ({issue.get('url', '')}) on branch `{branch}`. "
        f"Target the pull request at `{base}`. Follow `AGENTS.md`.",
        "",
        f"- **Owner:** {field('Owner')}",
        f"- **Scope, change only these files:** {field('Scope')}",
        f"- **Tool:** {field('Tool', 'any')}",
        f"- **Interfaces and dependencies:** {field('Interfaces and dependencies', 'none specified')}",
        f"- **Model class:** `{klasse}` ({models['beschreibung']}): Claude `{models.get('claude') or '–'}`, "
        f"Codex `{models.get('codex') or '–'}`. If using a different model, state it in the pull request.",
        "",
        "## Outcome and acceptance test",
        "",
        field("Outcome and acceptance test"),
        "",
        "## How to finish",
        "",
        "1. Run `python -m unittest discover -s tests -v` and the acceptance example.",
        "2. Read `tools/board unread` first; coordinate changes to other owners' files or shared interfaces "
        "on the board beforehand.",
        f"3. `git fetch`, `git rebase origin/{base}`, push and open a pull request targeting `{base}` with `Closes #{number}`.",
        "4. Report the result, tests performed and open points in the pull request.",
        "5. Under FirstMate, open the finished PR; the First Mate merges after green checks. "
        "Otherwise merge yourself: `gh pr checks --watch`, then `gh pr merge --squash --delete-branch`.",
        "6. If the merge changes a shared interface, post with `@all` on the board (`tools/board post`).",
        "",
        "## Issue text",
        "",
        (issue.get("body") or "").strip() or "(empty)",
        "",
    ])


def prepare(number, base_override=None, here=False):
    issue = json.loads(run("gh", "issue", "view", str(number), "--json", "number,title,body,url,state,labels"))
    if issue.get("state") != "OPEN":
        raise Stop(f"Issue #{number} is not open.")
    fields = parse_form(issue.get("body"))
    base = base_override or base_branch(fields, issue.get("body"))
    if not base:
        raise Stop(f"Issue #{number} does not specify a target branch. Add it to the issue or use --basis main.")
    branch = branch_name(number, issue["title"])
    run("git", "fetch", "origin", base)
    has_branch = bool(run("git", "branch", "--list", branch))

    if here:
        if run("git", "status", "--porcelain"):
            raise Stop("The current folder has uncommitted changes. Commit first or omit --hier.")
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
    run("gh", "issue", "edit", str(number), "--add-assignee", "@me", "--add-label", "in-arbeit")
    run("gh", "issue", "comment", str(number), "--body",
        f"Claimed by @{login} using {tool} on branch `{branch}`.")
    board = subprocess.run([sys.executable, str(ROOT / "tools" / "board.py"), "post",
                            f"[{login} · {tool}] claims #{number} on branch `{branch}`."],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if board.returncode:
        print(f"! Could not post on board: {(board.stderr or board.stdout).strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("issue", type=int, help="GitHub issue number")
    parser.add_argument("--basis", help="target branch if the issue does not specify one")
    parser.add_argument("--hier", action="store_true", help="work in the current folder without a worktree")
    parser.add_argument("--uebernehmen", action="store_true", help="assign yourself and comment on the claim")
    parser.add_argument("--werkzeug", help="e.g. Claude Code, Codex or Antigravity (for the comment)")
    args = parser.parse_args()
    try:
        issue, fields, branch, base, folder = prepare(args.issue, args.basis, args.hier)
        if args.uebernehmen:
            claim(args.issue, branch, args.werkzeug or fields.get("Tool", fields.get("Werkzeug", "a coding agent")))
    except Stop as exc:
        print(f"✗ {exc}")
        return 1
    print(f"✓ Issue #{issue['number']}: {issue['title']}")
    print(f"✓ Folder {folder}")
    print(f"✓ Branch {branch}, pull request will target {base}")
    print(f"✓ Assignment in {folder / '.auftrag.md'}")
    print()
    klasse = model_class(issue.get("labels"))
    print(f'Next step: cd "{folder}", then choose a tool (model class {klasse}: {MODELS[klasse]["beschreibung"]})')
    for tool, command in launch_commands(klasse).items():
        print(f"  {tool + ':':<13} {command}")
    print(f"  Antigravity:  open the folder and type in the agent chat: {PROMPT}")
    print()
    print(f"At the end: git push -u origin {branch}, then a pull request targeting {base} with Closes #{issue['number']}.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
