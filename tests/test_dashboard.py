"""Offline checks for the command center: data shaping and the guard in front of agent control."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("team_dashboard", ROOT / "tools" / "dashboard.py")
dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dash)


class DataTests(unittest.TestCase):
    def test_team_comes_from_agents_md(self):
        team = dash.team_from_agents_md((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        roles = {member["login"]: member["role"] for member in team}
        self.assertTrue(roles["f89pkdtkhw-lab"].startswith("Lead, Integration, Deploy, Demo"))
        self.assertIn("Beschreibung und Tags", roles["f89pkdtkhw-lab"])
        self.assertEqual(len(team), 5)

    def test_ci_traffic_light(self):
        self.assertEqual(dash.ci_state([]), "none")
        self.assertEqual(dash.ci_state([{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}]), "green")
        self.assertEqual(dash.ci_state([{"conclusion": "SUCCESS"}, {"status": "IN_PROGRESS"}]), "pending")
        self.assertEqual(dash.ci_state([{"conclusion": "FAILURE"}, {"status": "IN_PROGRESS"}]), "red")

    def test_quota_keeps_tightest_window(self):
        rows = dash.quota_summary({"providers": [{"provider": "claude", "plan": "pro", "windows": [
            {"label": "session", "percentRemaining": 44.4}, {"label": "week", "percentRemaining": 12.6}]},
            {"provider": "none", "windows": []}]})
        self.assertEqual([(r["provider"], r["percent"], r["window"]) for r in rows], [("claude", 13, "week")])

    def test_first_mate_agents_and_shells_are_told_apart(self):
        fm = dash.agent_summary({"pane_id": "w1:p1", "cwd": "/home/x/firstmate", "agent": "claude", "agent_status": "idle"}, "a\nb\n")
        worker = dash.agent_summary({"pane_id": "w1:p2", "cwd": "/home/x/wt/7-reset", "agent": "codex"}, "", "7-reset")
        shell = dash.agent_summary({"pane_id": "w1:p3", "cwd": "/home/x/firstmate", "tab_id": "w1:t2"}, "$ ")
        self.assertTrue(fm["firstMate"])
        self.assertEqual(fm["screen"], ["a", "b"])
        self.assertEqual((worker["folder"], worker["status"], worker["branch"]), ("7-reset", "unknown", "7-reset"))
        self.assertEqual((shell["isAgent"], shell["status"], shell["firstMate"], shell["tab"]), (False, "shell", False, "w1:t2"))

    def test_crew_changes_become_events(self):
        a = {"id": "w1:p2", "status": "working", "firstMate": False, "branch": "7-reset", "title": "", "folder": "", "agent": "codex"}
        events = dash.crew_events([a], [{**a, "status": "blocked"}, {**a, "id": "w1:p4", "branch": "8-tests"}])
        self.assertEqual([e[0] for e in events], ["blocked", "spawn"])
        self.assertIn("working → blocked", events[0][1])
        self.assertEqual(dash.crew_events([a], [])[0][0], "exit")

    def test_github_changes_become_events(self):
        pr = {"number": 3, "title": "Login", "author": "k1ub1", "state": "OPEN", "ci": "pending"}
        before = {"prs": [pr], "board": [{"id": 1, "user": "a", "body": "x"}]}
        after = {"prs": [{**pr, "ci": "red"}, {**pr, "number": 4}], "board": [{"id": 1, "user": "a", "body": "x"}, {"id": 2, "user": "b", "body": "@all neu"}]}
        self.assertEqual([e[0] for e in dash.github_events(before, after)], ["ci-red", "pr", "board"])
        self.assertEqual(dash.github_events(None, after), [])
        merged = dash.github_events({"prs": [pr], "board": []}, {"prs": [{**pr, "state": "MERGED"}], "board": []})
        self.assertEqual(merged[0][0], "merge")
        red = dash.github_events({"prs": [], "board": [], "pipeline": {"status": "success"}},
                                 {"prs": [], "board": [], "pipeline": {"status": "failure", "checked": "abc1234", "demo": "def5678"}})
        self.assertEqual(red[0][0], "ci-red")
        self.assertIn("def5678", red[0][1])

    def test_state_keeps_event_log_and_load_history(self):
        state = dash.State()
        a = {"id": "w1:p2", "status": "idle", "firstMate": False, "branch": "b", "title": "", "folder": "", "agent": "codex", "isAgent": True}
        state.put("crew", [a])
        state.put("crew", [{**a, "status": "working"}])
        snap = state.snapshot()
        self.assertEqual([e["kind"] for e in snap["events"]], ["spawn", "status"])
        self.assertEqual(snap["history"][0]["agents"], 1)
        self.assertNotIn("_s", snap["history"][0])


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.state = dash.State()
        self.state.put("crew", [{"id": "w1:p2", "status": "blocked"}, {"id": "w1:p3", "status": "idle"}])

    def test_blocked_agent_gets_typed_answer_and_idle_agent_gets_prompt(self):
        with patch.object(dash, "run_checked", return_value=(True, "ok")) as call:
            dash.send_prompt(self.state, "w1:p2", "2")
            dash.send_prompt(self.state, "w1:p3", "Arbeite Issue #7 ab")
        commands = [c.args for c in call.call_args_list]
        self.assertEqual(commands[0], ("herdr", "pane", "send-text", "w1:p2", "2"))
        self.assertEqual(commands[1], ("herdr", "pane", "send-keys", "w1:p2", "enter"))
        self.assertEqual(commands[2], ("herdr", "agent", "prompt", "w1:p3", "Arbeite Issue #7 ab"))

    def test_only_known_agents_and_allowed_keys(self):
        with patch.object(dash, "run_checked") as call:
            self.assertFalse(dash.send_prompt(self.state, "w9:p9", "hi")[0])
            self.assertFalse(dash.send_keys(self.state, "w1:p2", ["rm -rf"])[0])
            self.assertFalse(dash.send_prompt(self.state, "w1:p3", "   ")[0])
            call.assert_not_called()


class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = dash.State()
        cls.state.put("crew", [{"id": "w1:p1", "status": "idle"}])
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(dash.Handler, state=cls.state, board=None, token="geheim"))
        Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            connection.close()

    def test_page_carries_the_session_token(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('const TOKEN = "geheim"', html)

    def test_control_needs_token_and_same_origin(self):
        body = json.dumps({"id": "w1:p1", "text": "hallo"})
        with patch.object(dash, "send_prompt", return_value=(True, "ok")) as send:
            for headers in ({}, {"Origin": self.origin}, {"X-Leitstelle-Token": "geheim"},
                            {"Origin": "https://evil.example", "X-Leitstelle-Token": "geheim"},
                            {"Origin": self.origin, "X-Leitstelle-Token": "falsch"}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.request("POST", "/api/prompt", body, headers)[0], 403)
            send.assert_not_called()
            status, text = self.request("POST", "/api/prompt", body, {"Origin": self.origin, "X-Leitstelle-Token": "geheim"})
            self.assertEqual((status, json.loads(text)["ok"]), (200, True))
            send.assert_called_once()

    def test_foreign_host_is_refused(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "evil.example"})[0], 403)


if __name__ == "__main__":
    unittest.main()
