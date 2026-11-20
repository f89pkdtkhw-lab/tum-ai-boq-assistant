"""Browser command center: live agents, First Mate controls, answers and board posts.

    python3 tools/dashboard.py              # Then open http://localhost:8770
    python3 tools/dashboard.py --port 8771

Sources: Herdr (each agent with status and colored pane contents), quota-axi and GitHub via gh.
If a source is missing, the others keep running. The server listens only on 127.0.0.1.
Write requests (prompts, keys, board posts) require the served page's session token and
matching Origin, preventing another website from controlling your agents.
"""
import argparse
from collections import deque
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path(__file__).with_name("dashboard.html")
DEADLINE = "2026-11-22T11:30:00+01:00"
OFFICIAL_DEADLINE = "2026-11-22T12:00:00+01:00"
SCREEN_LINES = 40
ALLOWED_KEYS = {"enter", "esc", "tab", "up", "down", "left", "right", "ctrl+c", "y", "n",
                "1", "2", "3", "4", "5", "6", "7", "8", "9"}
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def run(*command, timeout=20):
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def run_checked(*command, timeout=20):
    """Like run, but return (ok, message) for actions the user triggered."""
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    message = (done.stdout or done.stderr).strip()
    try:
        error = json.loads(message).get("error")
        if error:
            return False, error.get("message") or error.get("code") or message
    except (ValueError, AttributeError):
        pass
    return done.returncode == 0, message


def team_from_agents_md(text):
    """Read the '| @login | Role |' rows of section 1 in AGENTS.md."""
    section = text.split("## 1.", 1)[-1].split("\n## ", 1)[0]
    return [{"login": login, "role": role.strip()}
            for login, role in re.findall(r"^\|\s*@([A-Za-z0-9-]+)\s*\|\s*([^|]+?)\s*\|", section, re.M)]


def ci_state(rollup):
    states = [(item.get("conclusion") or item.get("state") or item.get("status") or "").upper() for item in rollup or []]
    if not states:
        return "none"
    if any(state in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for state in states):
        return "red"
    if all(state in {"SUCCESS", "SKIPPED", "NEUTRAL"} for state in states):
        return "green"
    return "pending"


def quota_summary(data):
    """Reduce quota-axi --json to one row per provider with its tightest window."""
    rows = []
    for provider in (data or {}).get("providers", []):
        windows = [w for w in provider.get("windows", []) if isinstance(w.get("percentRemaining"), (int, float))]
        if not windows:
            continue
        tight = min(windows, key=lambda w: w["percentRemaining"])
        rows.append({
            "provider": provider.get("provider", "?"),
            "plan": provider.get("plan") or "",
            "percent": round(tight["percentRemaining"]),
            "window": tight.get("label") or tight.get("id") or "",
            "resetsAt": tight.get("resetsAt"),
            "windows": [{"label": w.get("label") or w.get("id"), "percent": round(w["percentRemaining"])} for w in windows],
        })
    return rows


def is_first_mate(pane):
    return bool(pane.get("agent")) and (pane.get("cwd") or "").rstrip("/").endswith("/firstmate")


def agent_summary(pane, screen, branch=""):
    """One Herdr pane; `pane` may come from `agent list` or plain `pane list` (then it is a shell)."""
    cwd = pane.get("foreground_cwd") or pane.get("cwd") or ""
    is_agent = bool(pane.get("agent"))
    return {
        "id": pane.get("pane_id"),
        "agent": pane.get("agent") or "shell",
        "isAgent": is_agent,
        "status": (pane.get("agent_status") or "unknown") if is_agent else "shell",
        "title": pane.get("terminal_title_stripped") or pane.get("terminal_title") or "",
        "cwd": cwd,
        "folder": cwd.rstrip("/").rsplit("/", 1)[-1],
        "tab": pane.get("tab_id") or "",
        "workspace": pane.get("workspace_id") or "",
        "branch": branch,
        "firstMate": is_first_mate(pane),
        "screen": screen.rstrip("\n").split("\n")[-SCREEN_LINES:] if screen else [],
    }


def crew_events(before, after):
    """Status changes between two crew lists, as telemetry events."""
    old = {a["id"]: a for a in before or []}
    events = []
    def name(agent):
        if agent.get("firstMate"):
            return "First Mate"
        return agent.get("branch") or agent.get("title") or agent.get("folder") or agent["id"]

    for agent in after:
        previous = old.pop(agent["id"], None)
        if previous is None:
            events.append(("spawn", f"{name(agent)} started ({agent.get('agent', '?')})", agent["id"]))
        elif previous["status"] != agent["status"]:
            kind = "blocked" if agent["status"] == "blocked" else "status"
            events.append((kind, f"{name(agent)}: {previous['status']} → {agent['status']}", agent["id"]))
    for gone in old.values():
        events.append(("exit", f"{name(gone)} stopped", gone["id"]))
    return events


def github_events(before, after):
    """New or changed PRs, CI results and board posts between two GitHub snapshots."""
    if not before:
        return []
    events = []
    old_prs = {p["number"]: p for p in before.get("prs", [])}
    for pr in after.get("prs", []):
        previous = old_prs.get(pr["number"])
        label = f"PR #{pr['number']} {pr['title'][:60]}"
        if previous is None:
            events.append(("pr", f"{label} opened by @{pr['author']}", None))
        elif previous["state"] != pr["state"]:
            events.append(("merge" if pr["state"] == "MERGED" else "pr", f"{label}: {pr['state'].lower()}", None))
        elif previous["ci"] != pr["ci"] and pr["ci"] in {"green", "red"}:
            events.append(("ci-" + pr["ci"], f"{label}: Checks {'green' if pr['ci'] == 'green' else 'red'}", None))
    old_pipe, new_pipe = before.get("pipeline") or {}, after.get("pipeline") or {}
    if new_pipe.get("status") in {"success", "failure"} and old_pipe.get("status") != new_pipe.get("status"):
        events.append(("ci-green" if new_pipe["status"] == "success" else "ci-red",
                       f"main {'green' if new_pipe['status'] == 'success' else 'RED'} at {new_pipe.get('checked')}, demo at {new_pipe.get('demo') or '–'}", None))
    seen = {post["id"] for post in before.get("board", [])}
    for post in after.get("board", []):
        if post["id"] not in seen:
            events.append(("board", f"@{post['user']}: {post['body'][:90]}", None))
    return events


class State:
    """Shared snapshot, refreshed by background pollers, plus an event log and a load history."""

    def __init__(self):
        self.lock = threading.Lock()
        self.data = {"crew": None, "quota": None, "github": None, "errors": {}}
        self.events = deque(maxlen=300)
        self.history = deque(maxlen=360)
        self.started = datetime.now(timezone.utc).isoformat()

    def put(self, key, value, error=None):
        with self.lock:
            before = self.data.get(key)
            self.data[key] = value
            if error:
                self.data["errors"][key] = error
            else:
                self.data["errors"].pop(key, None)
            now = datetime.now(timezone.utc).isoformat()
            if key == "crew" and value is not None:
                if before is not None or value:
                    for kind, text, ref in crew_events(before or [], value):
                        self.events.append({"t": now, "kind": kind, "text": text, "ref": ref})
                agents = [a for a in value if a.get("isAgent", True)]
                sample = {"t": now, "working": sum(a["status"] == "working" for a in agents),
                          "blocked": sum(a["status"] == "blocked" for a in agents), "agents": len(agents)}
                if not self.history or time.time() - self.history[-1]["_s"] >= 10:
                    self.history.append({**sample, "_s": time.time()})
            if key == "github" and value:
                for kind, text, ref in github_events(before, value):
                    self.events.append({"t": now, "kind": kind, "text": text, "ref": ref})

    def snapshot(self):
        with self.lock:
            history = [{k: v for k, v in h.items() if k != "_s"} for h in self.history]
            return json.loads(json.dumps({**self.data, "deadline": DEADLINE, "officialDeadline": OFFICIAL_DEADLINE,
                                          "events": list(self.events)[-150:], "history": history,
                                          "started": self.started, "now": datetime.now(timezone.utc).isoformat()}))

    def agent(self, pane_id):
        with self.lock:
            return next((a for a in self.data.get("crew") or [] if a["id"] == pane_id), None)


def poll_crew(state):
    if not shutil.which("herdr"):
        state.put("crew", [], "Herdr not found: start the dashboard where Herdr runs (Ubuntu/macOS).")
        return
    raw_panes, raw_agents = run("herdr", "pane", "list"), run("herdr", "agent", "list")
    if raw_panes is None:
        state.put("crew", [], "Herdr is not running. Start the control station or herdr first.")
        return
    agents = {a["pane_id"]: a for a in json.loads(raw_agents or "{}").get("result", {}).get("agents", [])
              if a.get("pane_id")}
    crew = []
    for pane in json.loads(raw_panes).get("result", {}).get("panes", []):
        pane_id = pane.get("pane_id")
        if not pane_id:
            continue
        merged = {**pane, **agents.get(pane_id, {})}
        screen = run("herdr", "pane", "read", pane_id, "--source", "visible",
                     "--lines", str(SCREEN_LINES), "--format", "ansi") or ""
        crew.append(agent_summary(merged, screen, git_branch(merged.get("foreground_cwd") or merged.get("cwd"))))
    crew.sort(key=lambda a: (not a["firstMate"], not a["isAgent"], a["folder"], a["id"]))
    state.put("crew", crew)


_branches = {}


def git_branch(cwd):
    """Current branch of a worker's checkout, cached for 15 seconds."""
    if not cwd:
        return ""
    cached = _branches.get(cwd)
    if cached and time.time() - cached[1] < 15:
        return cached[0]
    branch = (run("git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD", timeout=5) or "").strip()
    _branches[cwd] = (branch, time.time())
    return branch


def poll_quota(state):
    if not shutil.which("quota-axi"):
        state.put("quota", [], "quota-axi not found.")
        return
    raw = run("quota-axi", "--json", "--max-age", "2m", timeout=60)
    state.put("quota", quota_summary(json.loads(raw)) if raw else [], None if raw else "quota-axi returned nothing.")


def load_board():
    spec = importlib.util.spec_from_file_location("team_board", ROOT / "tools" / "board.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def poll_github(state, board):
    issues = run("gh", "issue", "list", "--state", "open", "--limit", "100",
                 "--json", "number,title,assignees,labels,url")
    prs = run("gh", "pr", "list", "--state", "all", "--limit", "15",
              "--json", "number,title,author,state,isDraft,headRefName,url,updatedAt,statusCheckRollup")
    if issues is None or prs is None:
        state.put("github", None, "GitHub unreachable: check gh auth login.")
        return
    try:
        board_issue, login = board.issue_number(), board.me()
        posts = board.fetch_last(board.repo(), board_issue, 20)
    except board.BoardError:
        board_issue, login, posts = None, None, []
    team = team_from_agents_md((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    pipeline = pipeline_status(board)
    state.put("github", {
        "pipeline": pipeline,
        "team": team,
        "issues": [{"number": i["number"], "title": i["title"], "url": i["url"],
                    "assignees": [a["login"] for a in i.get("assignees", [])],
                    "labels": [label["name"] for label in i.get("labels", [])]} for i in json.loads(issues)],
        "prs": [{"number": p["number"], "title": p["title"], "url": p["url"], "state": p["state"],
                 "draft": p.get("isDraft", False), "author": (p.get("author") or {}).get("login", ""),
                 "branch": p.get("headRefName", ""), "updatedAt": p.get("updatedAt"),
                 "ci": ci_state(p.get("statusCheckRollup"))} for p in json.loads(prs)],
        "board": [{"id": post["id"], "user": post["user"], "createdAt": post["created_at"], "body": post["body"]}
                  for post in posts],
        "boardIssue": board_issue,
        "me": login,
    })


def pipeline_status(board):
    """Latest checks on main and where the demo branch (the jury URL) stands."""
    try:
        repo = board.repo()
    except board.BoardError:
        return None
    runs = json.loads(run("gh", "run", "list", "--branch", "main", "--workflow", "Team-Checks", "--limit", "1",
                          "--json", "conclusion,status,headSha,url") or "[]")
    main_sha = (run("gh", "api", f"repos/{repo}/branches/main", "--jq", ".commit.sha") or "").strip()
    demo_sha = (run("gh", "api", f"repos/{repo}/branches/demo", "--jq", ".commit.sha") or "").strip()
    latest = runs[0] if runs else {}
    return {"main": main_sha[:7], "demo": demo_sha[:7], "checked": (latest.get("headSha") or "")[:7],
            "status": latest.get("conclusion") or latest.get("status") or "unknown", "url": latest.get("url", "")}


def poller(state, every, task, *args):
    while True:
        try:
            task(state, *args)
        except Exception as exc:  # keep the dashboard alive whatever one source does
            state.put(task.__name__.replace("poll_", ""), None, f"{type(exc).__name__}: {exc}")
        time.sleep(every)


def send_prompt(state, pane_id, text):
    agent = state.agent(pane_id)
    if not agent:
        return False, "This agent no longer exists."
    text = text.strip()
    if not text or len(text) > 8000:
        return False, "Empty or overly long text."
    if agent["status"] in {"blocked", "shell"}:
        # A blocked agent waits at a question or approval, a shell waits for a command: type like a person.
        ok, message = run_checked("herdr", "pane", "send-text", pane_id, text)
        return run_checked("herdr", "pane", "send-keys", pane_id, "enter") if ok else (ok, message)
    return run_checked("herdr", "agent", "prompt", pane_id, text)


def send_keys(state, pane_id, keys):
    if not state.agent(pane_id):
        return False, "This agent no longer exists."
    if not keys or not all(key in ALLOWED_KEYS for key in keys):
        return False, "Key not allowed."
    return run_checked("herdr", "pane", "send-keys", pane_id, *keys)


def post_board(board, text):
    text = text.strip()
    if not text or len(text) > 4000:
        return False, "Empty or overly long post."
    try:
        if not board.PREFIX.match(text):
            text = f"[{board.me()} · Control station] {text}"
        return run_checked("gh", "issue", "comment", str(board.issue_number()), "--repo", board.repo(),
                           "--body", text)
    except board.BoardError as exc:
        return False, str(exc)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, state, board, token, **kwargs):
        self.state, self.board, self.token = state, board, token
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass

    def send(self, status, media_type, body):
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def local_host(self):
        return self.headers.get("Host", "").rsplit(":", 1)[0] in LOCAL_HOSTS

    def do_GET(self):
        if not self.local_host():
            self.send(403, "text/plain; charset=utf-8", b"Available locally only.")
        elif self.path == "/":
            self.send(200, "text/html; charset=utf-8",
                      PAGE.read_text(encoding="utf-8").replace("__TOKEN__", self.token).encode("utf-8"))
        elif self.path == "/api/state":
            self.send_json(200, self.state.snapshot())
        else:
            self.send(404, "text/plain; charset=utf-8", b"Not found.")

    def do_POST(self):
        host = self.headers.get("Host", "")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        # Read the body before any answer, so a refused request does not reset the connection.
        raw = self.rfile.read(length) if 0 < length <= 16384 else b""
        if (not self.local_host() or self.headers.get("Origin") != f"http://{host}"
                or not secrets.compare_digest(self.headers.get("X-Leitstelle-Token", ""), self.token)):
            self.send_json(403, {"ok": False, "message": "Not allowed."})
            return
        try:
            if not raw:
                raise ValueError
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            self.send_json(400, {"ok": False, "message": "Invalid request."})
            return
        if self.path == "/api/prompt":
            ok, message = send_prompt(self.state, str(body.get("id", "")), str(body.get("text", "")))
        elif self.path == "/api/keys":
            keys = body.get("keys")
            ok, message = send_keys(self.state, str(body.get("id", "")),
                                    [str(k) for k in keys] if isinstance(keys, list) else [])
        elif self.path == "/api/board":
            ok, message = post_board(self.board, str(body.get("text", "")))
        else:
            self.send_json(404, {"ok": False, "message": "Not found."})
            return
        self.send_json(200 if ok else 422, {"ok": ok, "message": message[-400:]})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    state, board, token = State(), load_board(), secrets.token_urlsafe(24)
    for every, task, extra in ((2, poll_crew, ()), (60, poll_quota, ()), (20, poll_github, (board,))):
        threading.Thread(target=poller, args=(state, every, task, *extra), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, state=state, board=board, token=token))
    print(f"Command center running: http://localhost:{args.port}  (Ctrl+C stops it)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()
