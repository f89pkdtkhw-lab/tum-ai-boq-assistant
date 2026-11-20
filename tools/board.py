"""Team board: a pinned GitHub issue for handovers between all agents and people.

    tools/board post "[Raban · Claude] Login finished. @leon1ce route POST /api/session is ready."
    tools/board unread                    # New posts since last check, mentions marked
    tools/board read -n 20                # Last 20 posts
    tools/board wait                      # Block until someone else posts
    tools/board wait --nur-erwaehnungen   # Block until someone mentions you
    tools/board whoami

On Windows PowerShell use `python tools/board.py ...` instead of `tools/board ...`.
Requires only Python and an authenticated GitHub CLI (gh). Settings: BOARD_ISSUE (fallback:
tools/board.json), BOARD_REPO (fallback: git/gh), BOARD_WAIT=off disables the wait loop
for Claude hooks.
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
        raise BoardError("gh not found. Install https://cli.github.com, then run gh auth login.") from None
    except subprocess.TimeoutExpired:
        raise BoardError("gh did not respond (timeout).") from None
    if done.returncode:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise BoardError(lines[-1] if lines else f"gh {' '.join(args[:2])} failed")
    return done.stdout


def issue_number():
    value = os.environ.get("BOARD_ISSUE")
    if not value and CONFIG.is_file():
        value = json.loads(CONFIG.read_text(encoding="utf-8")).get("issue")
    if not str(value or "").isdigit():
        raise BoardError("No board issue configured: set tools/board.json or BOARD_ISSUE.")
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
        raise BoardError("Every post starts with [<Name> · <Agent>], e.g. [Raban · Claude] ...")
    print(gh("issue", "comment", str(issue_number()), "--repo", repo(), "--body-file", "-", stdin=text).strip())


def cmd_unread(_args):
    login = me()
    posts = unread_posts(repo(), issue_number(), login)
    if posts:
        print(render(posts, login))
    else:
        print("No new posts.")


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
            print(f"board: {exc} (attempt {failures}/{MAX_FAILURES})", file=sys.stderr)
            if failures >= MAX_FAILURES:
                return 1
            posts = []
        if posts:
            print(render(posts, login), flush=True)
            if not args.nur_erwaehnungen or any(mentions(post["body"], login) for post in posts):
                return 0
        if args.max and time.monotonic() - started >= args.max:
            print("No new posts.")
            return 3
        time.sleep(interval)


def cmd_whoami(_args):
    print(f"{me()} on {repo()}, board issue #{issue_number()}")


def quiet_wait():
    """FirstMate workers and anyone with BOARD_WAIT=off rely on a supervisor instead of a background wait."""
    return os.environ.get("BOARD_WAIT") == "off" or any(key.startswith("FM_") for key in os.environ)


def cmd_hook_start(_args):
    try:
        issue = issue_number()
        login = me()
        unread = render(unread_posts(repo(), issue, login), login)
    except BoardError as exc:
        print(f"Team board unreachable ({exc}). Run tools/board unread later.")
        return 0
    print(f"Team board: GitHub issue #{issue}. Rules in AGENTS.md, section 2. You post for @{login}.")
    print(f"Unread posts:\n{unread}" if unread else "No unread posts.")
    if quiet_wait():
        print("Board loop: your supervisor monitors the board. Do not start tools/board wait, "
              "but run tools/board unread before every commit and after every merge.")
    else:
        print("Board loop: start ONE Bash command in the background now (run_in_background): "
              "`tools/board wait`. When it exits, its output contains new posts. On ** MENTION ** "
              "act and reply on the board; otherwise check whether your work is affected; "
              "do not post mere acknowledgements. Then restart `tools/board wait` in the background. "
              "Never run two waits simultaneously.")
    return 0


def cmd_hook_prompt(_args):
    try:
        login = me()
        unread = render(unread_posts(repo(), issue_number(), login), login)
    except BoardError:
        return 0
    if unread:
        print(f"New team board posts (rules: AGENTS.md, section 2):\n{unread}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    post = commands.add_parser("post", help="write a post (text, '-' or no text for stdin)")
    post.add_argument("text", nargs="*")
    post.set_defaults(run=cmd_post)
    commands.add_parser("unread", help="new posts since last check").set_defaults(run=cmd_unread)
    read = commands.add_parser("read", help="read recent posts")
    read.add_argument("-n", type=int, default=20)
    read.set_defaults(run=cmd_read)
    wait = commands.add_parser("wait", help="wait until someone else posts")
    wait.add_argument("--interval", type=int, default=30, help="seconds between polls (minimum 10)")
    wait.add_argument("--nur-erwaehnungen", action="store_true", help="return only on a mention")
    wait.add_argument("--max", type=int, default=0, help="stop after this many seconds without a post")
    wait.set_defaults(run=cmd_wait)
    commands.add_parser("whoami", help="show your login, repository and board").set_defaults(run=cmd_whoami)
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
