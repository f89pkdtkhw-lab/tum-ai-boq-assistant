"""Lagebild für alle Menschen und Agenten: wer arbeitet woran, was ist frei, wo droht Überschneidung.

    python tools/stand.py                      # Gesamtbild: in Arbeit, bereit, blockiert, offene PRs, Konflikte
    python tools/stand.py --naechstes          # das nächste freie Issue für dich (erst deine, dann unverteilte)
    python tools/stand.py --naechstes --login Zukipany
    python tools/stand.py --json               # maschinenlesbar für First Mates

Jeder First Mate ruft das bei jedem Aufsichtsdurchgang auf, jeder Worker vor Arbeitsbeginn.
Braucht nur Python und die angemeldete GitHub CLI (gh). Liest nur, ändert nichts.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLAIM = "in-arbeit"
READY = "agent-bereit"
BLOCKED = "blockiert"

_spec = importlib.util.spec_from_file_location("team_aufgabe", ROOT / "tools" / "aufgabe.py")
_aufgabe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_aufgabe)
parse_form = _aufgabe.parse_form


class Stop(Exception):
    pass


def gh_json(*args):
    try:
        done = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
    except FileNotFoundError:
        raise Stop("gh nicht gefunden. https://cli.github.com installieren, dann gh auth login.") from None
    if done.returncode:
        raise Stop((done.stderr or done.stdout).strip().splitlines()[-1])
    return json.loads(done.stdout or "null")


def labels_of(item):
    return {label["name"] for label in item.get("labels", [])}


def logins(item):
    return [person["login"] for person in item.get("assignees", [])]


def area_paths(text):
    """Split a 'Bereich' field into normalized path prefixes."""
    parts = []
    for raw in (text or "").replace("\n", ",").replace(";", ",").split(","):
        path = raw.strip().strip("`").strip().rstrip("/").lstrip("./")
        if path and " " not in path:
            parts.append(path)
    return parts


def paths_overlap(a, b):
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def area_conflicts(issues):
    """Pairs of claimed issues whose Bereich overlaps."""
    found = []
    for i, first in enumerate(issues):
        for second in issues[i + 1:]:
            shared = sorted({p for x in first["bereich"] for y in second["bereich"]
                             if paths_overlap(x, y) for p in (x, y)})
            if shared:
                found.append((first["number"], second["number"], shared))
    return found


def file_conflicts(prs):
    """Files changed by more than one open PR."""
    owners = {}
    for pr in prs:
        for path in pr["files"]:
            owners.setdefault(path, []).append(pr["number"])
    return {path: numbers for path, numbers in sorted(owners.items()) if len(numbers) > 1}


def ci_state(checks):
    states = {(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in checks or []}
    if not states:
        return "–"
    if states & {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
        return "rot"
    if states & {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING"}:
        return "läuft"
    return "grün"


def classify(issue):
    tags = labels_of(issue)
    if BLOCKED in tags:
        return "blockiert"
    if CLAIM in tags:
        return "in Arbeit"
    if READY in tags:
        return "bereit"
    return "offen"


def collect():
    raw_issues = gh_json("issue", "list", "--state", "open", "--limit", "200",
                         "--json", "number,title,labels,assignees,body,updatedAt")
    raw_prs = gh_json("pr", "list", "--state", "open", "--limit", "100",
                      "--json", "number,title,headRefName,author,isDraft,files,statusCheckRollup,body")
    merged = gh_json("pr", "list", "--state", "merged", "--limit", "5", "--json", "number,title,author,mergedAt")
    issues = []
    for issue in raw_issues:
        if issue["number"] in (1, 2):  # Board und Setup-Check sind keine Aufträge
            continue
        fields = parse_form(issue.get("body"))
        issues.append({
            "number": issue["number"], "title": issue["title"], "status": classify(issue),
            "assignees": logins(issue), "labels": sorted(labels_of(issue)),
            "bereich": area_paths(fields.get("Bereich", "")),
        })
    prs = [{
        "number": pr["number"], "title": pr["title"], "branch": pr["headRefName"],
        "author": (pr.get("author") or {}).get("login", "?"), "draft": pr.get("isDraft", False),
        "files": [f["path"] for f in pr.get("files") or []], "ci": ci_state(pr.get("statusCheckRollup")),
    } for pr in raw_prs]
    claimed = [i for i in issues if i["status"] == "in Arbeit"]
    return {
        "issues": issues, "prs": prs, "merged": merged,
        "bereich_konflikte": [{"issues": [a, b], "pfade": shared} for a, b, shared in area_conflicts(claimed)],
        "datei_konflikte": [{"pfad": p, "prs": n} for p, n in file_conflicts(prs).items()],
    }


def next_issue(data, login):
    """Own ready issues first, then unassigned ready ones that do not touch claimed areas."""
    busy = [p for i in data["issues"] if i["status"] == "in Arbeit" for p in i["bereich"]]
    ready = [i for i in data["issues"] if i["status"] == "bereit"]
    free = lambda issue: not any(paths_overlap(p, q) for p in issue["bereich"] for q in busy)
    mine = [i for i in ready if login in i["assignees"] and free(i)]
    open_ = [i for i in ready if not i["assignees"] and free(i)]
    return (mine or open_ or [None])[0]


def render(data):
    out = []
    by_status = {}
    for issue in data["issues"]:
        by_status.setdefault(issue["status"], []).append(issue)
    for status in ("in Arbeit", "bereit", "blockiert", "offen"):
        rows = by_status.get(status, [])
        out.append(f"\n== {status.upper()} ({len(rows)})")
        for i in rows:
            who = ", ".join("@" + a for a in i["assignees"]) or "frei"
            area = ", ".join(i["bereich"]) or "Bereich fehlt!"
            out.append(f"  #{i['number']:<4} {i['title'][:60]:<60} {who:<22} {area}")
    out.append(f"\n== OFFENE PRs ({len(data['prs'])})")
    for pr in data["prs"]:
        flag = " (Entwurf)" if pr["draft"] else ""
        out.append(f"  PR #{pr['number']:<4} CI {pr['ci']:<6} @{pr['author']:<16} {pr['title'][:60]}{flag}")
    out.append("\n== ZULETZT GEMERGT")
    for pr in data["merged"]:
        out.append(f"  PR #{pr['number']:<4} {pr['mergedAt'][:16].replace('T', ' ')}  {pr['title'][:70]}")
    if data["bereich_konflikte"] or data["datei_konflikte"]:
        out.append("\n!! ÜBERSCHNEIDUNGEN – vor dem Weiterarbeiten auf dem Board klären")
        for c in data["bereich_konflikte"]:
            out.append(f"  Issues #{c['issues'][0]} und #{c['issues'][1]} teilen {', '.join(c['pfade'])}")
        for c in data["datei_konflikte"]:
            out.append(f"  {c['pfad']} wird von PRs {', '.join('#' + str(n) for n in c['prs'])} geändert")
    else:
        out.append("\n✓ Keine Überschneidungen zwischen laufenden Aufträgen und offenen PRs.")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    parser.add_argument("--naechstes", action="store_true", help="nächstes freies Issue vorschlagen")
    parser.add_argument("--login", help="GitHub-Login (Standard: angemeldeter gh-Nutzer)")
    args = parser.parse_args()
    try:
        data = collect()
        if args.naechstes:
            login = args.login or gh_json("api", "user")["login"]
            pick = next_issue(data, login)
            if args.json:
                print(json.dumps(pick, ensure_ascii=False))
            elif pick:
                print(f"#{pick['number']} {pick['title']}\n"
                      f"Übernehmen: python tools/aufgabe.py {pick['number']} --uebernehmen")
            else:
                print("Kein freies agent-bereit-Issue. Lead auf dem Board fragen oder Folge-Issue schneiden.")
            return 0
        print(json.dumps(data, ensure_ascii=False, indent=1) if args.json else render(data))
    except Stop as exc:
        print(f"✗ {exc}")
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
