"""Team-Board: ein angeheftetes GitHub-Issue, über das sich alle Agenten und Menschen Arbeit übergeben.

    tools/board post "[Raban · Claude] Login fertig. @leon1ce die Route POST /api/session steht."
    tools/board unread                    # neue Posts seit dem letzten Blick, Erwähnungen markiert
    tools/board read -n 20                # die letzten 20 Posts
    tools/board wait                      # blockiert, bis jemand anderes postet
    tools/board wait --nur-erwaehnungen   # blockiert, bis dich jemand erwähnt
    tools/board whoami

Unter Windows in PowerShell `python tools/board.py ...` statt `tools/board ...`.
Braucht nur Python und die angemeldete GitHub CLI (gh). Einstellungen: BOARD_ISSUE (sonst
tools/board.json), BOARD_REPO (sonst aus git/gh), BOARD_WAIT=off schaltet die Warte-Schleife
für Claude-Hooks ab.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tools" / "board.json"
STATE = ROOT / ".board"
PREFIX = re.compile(r"^\[[^\[\]\n]{2,60}\]\s")
ROW_JQ = '.[] | [(.id|tostring), .user.login, .created_at, (.body|@base64)] | @tsv'
MAX_FAILURES = 10


class BoardError(Exception):
    """A message for the agent or person using the board."""


def gh(*args, stdin=None):
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", input=stdin, timeout=60)
    except FileNotFoundError:
        raise BoardError("gh nicht gefunden. https://cli.github.com installieren, dann gh auth login.") from None
    except subprocess.TimeoutExpired:
        raise BoardError("gh antwortet nicht (Zeitüberschreitung).") from None
    if done.returncode:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise BoardError(lines[-1] if lines else f"gh {' '.join(args[:2])} schlug fehl")
    return done.stdout


def issue_number():
    value = os.environ.get("BOARD_ISSUE")
    if not value and CONFIG.is_file():
        value = json.loads(CONFIG.read_text(encoding="utf-8")).get("issue")
    if not str(value or "").isdigit():
        raise BoardError("Kein Board-Issue eingestellt: tools/board.json oder BOARD_ISSUE setzen.")
    return int(value)


def _cached(name, compute):
    path = STATE / name
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = compute().strip()
    STATE.mkdir(exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return value


def repo():
    if os.environ.get("BOARD_REPO"):
        return os.environ["BOARD_REPO"]
    return _cached("repo", lambda: gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"))


def me():
    if os.environ.get("BOARD_LOGIN"):
        return os.environ["BOARD_LOGIN"]
    return _cached("login", lambda: gh("api", "user", "--jq", ".login"))


def parse_rows(text):
    """Turn gh's tab-separated rows into posts sorted by comment id."""
    posts = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        body = base64.b64decode(parts[3]).decode("utf-8", "replace").replace("\r", "")
        posts.append({"id": int(parts[0]), "user": parts[1], "created_at": parts[2], "body": body})
    return sorted(posts, key=lambda post: post["id"])


def mentions(body, login):
    return re.search(rf"(?<![\w-])@({re.escape(login)}|all)(?![\w-])", body, re.IGNORECASE) is not None


def render(posts, login):
    blocks = []
    for post in posts:
        flag = "  ** MENTION **" if mentions(post["body"], login) else ""
        blocks.append(f"--- @{post['user']} {post['created_at']} (#{post['id']}){flag}\n{post['body']}")
    return "\n".join(blocks)


def fetch_since(repository, issue, since):
    return parse_rows(gh("api", "--paginate", f"repos/{repository}/issues/{issue}/comments?per_page=100&since={since}",
                         "--jq", ROW_JQ))


def fetch_last(repository, issue, count):
    total = gh("api", f"repos/{repository}/issues/{issue}", "--jq", ".comments").strip()
    total = int(total) if total.isdigit() else 0
    page, posts = (total + 99) // 100, []
    while page >= 1 and len(posts) < count:
        posts = parse_rows(gh("api", f"repos/{repository}/issues/{issue}/comments?per_page=100&page={page}",
                              "--jq", ROW_JQ)) + posts
        page -= 1
    return posts[-count:] if count else []


def _cursor_path(repository, issue):
    return STATE / f"cursor-{repository.replace('/', '_')}-{issue}.json"


def load_cursor(repository, issue):
    try:
        cursor = json.loads(_cursor_path(repository, issue).read_text(encoding="utf-8"))
        return cursor if isinstance(cursor.get("id"), int) and cursor.get("created_at") else None
    except (OSError, ValueError, AttributeError):
        return None


def save_cursor(repository, issue, post):
    current = load_cursor(repository, issue)
    if current and current["id"] >= post["id"]:
        return
    STATE.mkdir(exist_ok=True)
    _cursor_path(repository, issue).write_text(
        json.dumps({"id": post["id"], "created_at": post["created_at"]}), encoding="utf-8")


def unread_posts(repository, issue, login):
    """Posts by others since this checkout last looked; the first look shows the last ten."""
    cursor = load_cursor(repository, issue)
    if cursor is None:
        posts = fetch_last(repository, issue, 10)
    else:
        posts = [post for post in fetch_since(repository, issue, cursor["created_at"]) if post["id"] > cursor["id"]]
    if posts:
        save_cursor(repository, issue, posts[-1])
    return [post for post in posts if post["user"].lower() != login.lower()]


def cmd_post(args):
    text = sys.stdin.read().strip() if not args.text or args.text == ["-"] else " ".join(args.text).strip()
    if not PREFIX.match(text):
        raise BoardError("Jeder Post beginnt mit [<Name> · <Agent>], z. B. [Raban · Claude] ...")
    print(gh("issue", "comment", str(issue_number()), "--repo", repo(), "--body-file", "-", stdin=text).strip())


def cmd_unread(_args):
    login = me()
    posts = unread_posts(repo(), issue_number(), login)
    if posts:
        print(render(posts, login))
    else:
        print("Keine neuen Posts.")


def cmd_read(args):
    print(render(fetch_last(repo(), issue_number(), args.n), me()))


def cmd_wait(args):
    login, repository, issue = me(), repo(), issue_number()
    interval, started, failures = max(10, args.interval), time.monotonic(), 0
    while True:
        try:
            posts = unread_posts(repository, issue, login)
            failures = 0
        except BoardError as exc:
            failures += 1
            print(f"board: {exc} (Versuch {failures}/{MAX_FAILURES})", file=sys.stderr)
            if failures >= MAX_FAILURES:
                return 1
            posts = []
        if posts:
            print(render(posts, login), flush=True)
            if not args.nur_erwaehnungen or any(mentions(post["body"], login) for post in posts):
                return 0
        if args.max and time.monotonic() - started >= args.max:
            print("Keine neuen Posts.")
            return 3
        time.sleep(interval)


def cmd_whoami(_args):
    print(f"{me()} auf {repo()}, Board-Issue #{issue_number()}")


def quiet_wait():
    """FirstMate workers and anyone with BOARD_WAIT=off rely on a supervisor instead of a background wait."""
    return os.environ.get("BOARD_WAIT") == "off" or any(key.startswith("FM_") for key in os.environ)


def cmd_hook_start(_args):
    try:
        issue = issue_number()
        login = me()
        unread = render(unread_posts(repo(), issue, login), login)
    except BoardError as exc:
        print(f"Team-Board nicht erreichbar ({exc}). Später tools/board unread ausführen.")
        return 0
    print(f"Team-Board: GitHub-Issue #{issue}. Regeln in AGENTS.md, Abschnitt 2. Du postest für @{login}.")
    print(f"Ungelesene Posts:\n{unread}" if unread else "Keine ungelesenen Posts.")
    if quiet_wait():
        print("Board-Schleife: Dein Supervisor beobachtet das Board. Starte kein tools/board wait, "
              "führe aber tools/board unread vor jedem Commit und nach jedem Merge aus.")
    else:
        print("Board-Schleife: Starte jetzt EINEN Bash-Befehl im Hintergrund (run_in_background): "
              "`tools/board wait`. Wenn er endet, enthält seine Ausgabe neue Posts. Bei ** MENTION ** "
              "handeln und auf dem Board antworten, sonst nur die eigene Arbeit prüfen, ob sie betroffen ist; "
              "keine reinen Bestätigungen posten. Danach `tools/board wait` erneut im Hintergrund starten. "
              "Nie zwei Waits gleichzeitig.")
    return 0


def cmd_hook_prompt(_args):
    try:
        login = me()
        unread = render(unread_posts(repo(), issue_number(), login), login)
    except BoardError:
        return 0
    if unread:
        print(f"Neue Posts auf dem Team-Board (Regeln: AGENTS.md, Abschnitt 2):\n{unread}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    post = commands.add_parser("post", help="Post schreiben (Text, '-' oder kein Text für stdin)")
    post.add_argument("text", nargs="*")
    post.set_defaults(run=cmd_post)
    commands.add_parser("unread", help="neue Posts seit dem letzten Blick").set_defaults(run=cmd_unread)
    read = commands.add_parser("read", help="letzte Posts lesen")
    read.add_argument("-n", type=int, default=20)
    read.set_defaults(run=cmd_read)
    wait = commands.add_parser("wait", help="warten, bis jemand anderes postet")
    wait.add_argument("--interval", type=int, default=30, help="Sekunden zwischen zwei Abfragen (mindestens 10)")
    wait.add_argument("--nur-erwaehnungen", action="store_true", help="erst bei einer Erwähnung zurückkehren")
    wait.add_argument("--max", type=int, default=0, help="nach so vielen Sekunden ohne Post aufgeben")
    wait.set_defaults(run=cmd_wait)
    commands.add_parser("whoami", help="eigenen Login, Repo und Board zeigen").set_defaults(run=cmd_whoami)
    commands.add_parser("hook-start", help=argparse.SUPPRESS).set_defaults(run=cmd_hook_start)
    commands.add_parser("hook-prompt", help=argparse.SUPPRESS).set_defaults(run=cmd_hook_prompt)
    args = parser.parse_args(argv)
    try:
        return args.run(args) or 0
    except BoardError as exc:
        print(f"board: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
