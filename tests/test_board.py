"""Offline checks for the team board script; gh is never called."""
import base64
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("team_board", ROOT / "tools" / "board.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
ISSUE_NUMBER = board.issue_number


def row(comment_id, user, body, created="2026-11-21T12:00:00Z"):
    return f"{comment_id}\t{user}\t{created}\t{base64.b64encode(body.encode()).decode()}"


class BoardTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        for name, value in (("STATE", Path(state.name)), ("issue_number", lambda: 18),
                            ("repo", lambda: "team/hack"), ("me", lambda: "leon1ce")):
            patcher = patch.object(board, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rows_keep_newlines_umlauts_and_order(self):
        posts = board.parse_rows("\n".join([row(7, "a", "zwei\r\nZeilen äö"), "kaputt", row(3, "b", "früher")]))
        self.assertEqual([post["id"] for post in posts], [3, 7])
        self.assertEqual(posts[1]["body"], "zwei\nZeilen äö")

    def test_mentions_match_login_or_all_but_not_longer_names(self):
        self.assertTrue(board.mentions("@leon1ce bitte Route bauen", "leon1ce"))
        self.assertTrue(board.mentions("Achtung @ALL: neues Schema", "leon1ce"))
        self.assertFalse(board.mentions("@leon1ce-bot macht das", "leon1ce"))
        self.assertFalse(board.mentions("mail@leon1ce.de", "leon1ce"))
        self.assertIn("** MENTION **", board.render([{"id": 1, "user": "a", "created_at": "t",
                                                      "body": "@leon1ce los"}], "leon1ce"))

    def test_first_look_shows_recent_posts_then_only_new_ones_from_others(self):
        with patch.object(board, "fetch_last", return_value=board.parse_rows(
                "\n".join([row(1, "k1ub1", "[Kai · Claude] Hallo"), row(2, "leon1ce", "[Leon · Codex] eigener Post")]))):
            first = board.unread_posts("team/hack", 18, "leon1ce")
        self.assertEqual([post["id"] for post in first], [1])
        newer = board.parse_rows("\n".join([row(2, "leon1ce", "alt"), row(3, "nedasblv", "[Neda · Codex] neu")]))
        with patch.object(board, "fetch_since", return_value=newer) as since:
            second = board.unread_posts("team/hack", 18, "leon1ce")
        self.assertEqual([post["id"] for post in second], [3])
        self.assertEqual(since.call_args.args[2], "2026-11-21T12:00:00Z")
        with patch.object(board, "fetch_since", return_value=newer):
            self.assertEqual(board.unread_posts("team/hack", 18, "leon1ce"), [])

    def test_posts_need_the_name_and_agent_prefix(self):
        with patch.object(board, "gh") as gh:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(board.main(["post", "ohne Präfix"]), 1)
            self.assertIn("[<Name> · <Agent>]", err.getvalue())
            gh.assert_not_called()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(board.main(["post", "[Leon · Codex] Route fertig @all"]), 0)
            self.assertEqual(gh.call_args.kwargs["stdin"], "[Leon · Codex] Route fertig @all")

    def test_post_reads_stdin_with_dash_or_without_text(self):
        text = "[Raban · Codex] @all Neue Schnittstelle\nZweite Zeile mit Umlauten äö."
        for args in (["post", "-"], ["post"]):
            with self.subTest(args=args), patch.object(board.sys, "stdin", io.StringIO(text + "\n")), \
                    patch.object(board, "gh", return_value="https://example.test/comment") as gh, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(board.main(args), 0)
                gh.assert_called_once_with("issue", "comment", "18", "--repo", "team/hack",
                                           "--body-file", "-", stdin=text)

    def test_unread_reports_no_new_posts_on_one_line(self):
        out = io.StringIO()
        with patch.object(board, "unread_posts", return_value=[]), contextlib.redirect_stdout(out):
            self.assertEqual(board.main(["unread"]), 0)
        self.assertEqual(out.getvalue(), "Keine neuen Posts.\n")

    def test_wait_returns_on_mention_and_skips_other_posts_when_asked(self):
        quiet = [{"id": 5, "user": "k1ub1", "created_at": "t", "body": "[Kai · Claude] Info"}]
        loud = [{"id": 6, "user": "k1ub1", "created_at": "t", "body": "[Kai · Claude] @leon1ce bitte"}]
        out = io.StringIO()
        with patch.object(board, "unread_posts", side_effect=[quiet, loud]), patch.object(board.time, "sleep"), \
                contextlib.redirect_stdout(out):
            self.assertEqual(board.main(["wait", "--nur-erwaehnungen", "--interval", "10"]), 0)
        self.assertIn("Info", out.getvalue())
        self.assertIn("** MENTION **", out.getvalue())

    def test_hooks_never_fail_and_firstmate_workers_do_not_start_a_wait(self):
        failing = patch.object(board, "unread_posts", side_effect=board.BoardError("offline"))
        out = io.StringIO()
        with failing, contextlib.redirect_stdout(out):
            self.assertEqual(board.main(["hook-start"]), 0)
            self.assertEqual(board.main(["hook-prompt"]), 0)
        self.assertIn("nicht erreichbar", out.getvalue())
        with patch.dict(board.os.environ, {"FM_HOME": "/x"}):
            self.assertTrue(board.quiet_wait())
        with patch.dict(board.os.environ, {"BOARD_WAIT": "off"}):
            self.assertTrue(board.quiet_wait())

    def test_configured_issue_comes_from_env_or_file(self):
        with patch.dict(board.os.environ, {"BOARD_ISSUE": "42"}):
            self.assertEqual(ISSUE_NUMBER(), 42)
        with patch.dict(board.os.environ, {"BOARD_ISSUE": ""}):
            self.assertGreater(ISSUE_NUMBER(), 0)


if __name__ == "__main__":
    unittest.main()
