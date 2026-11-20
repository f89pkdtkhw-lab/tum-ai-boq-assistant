"""Checks that Claude Code, Codex and Antigravity see the same rules, skills and tools."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEST_COMMAND = "python -m unittest discover -s tests -v"


def load(name):
    spec = importlib.util.spec_from_file_location(f"team_{name}", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SharedInstructionTests(unittest.TestCase):
    def test_every_tool_reaches_the_shared_rules(self):
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(claude[0].strip(), "@AGENTS.md")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Code Review Rules", agents)
        self.assertFalse((ROOT / "GEMINI.md").exists(), "Antigravity must read AGENTS.md, not a second rules file")

    def test_docs_and_ci_use_the_same_test_command(self):
        for path in ("AGENTS.md", "README.md", ".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/workflows/tests.yml"):
            with self.subTest(path=path):
                self.assertIn(TEST_COMMAND, (ROOT / path).read_text(encoding="utf-8"))

    def test_skills_are_valid_and_mirrored_for_claude_code(self):
        sync = load("agents_sync")
        self.assertGreaterEqual(len(sync.skill_dirs()), 1)
        self.assertEqual(sync.problems(), [], "run python tools/agents_sync.py")

    def test_skill_check_reports_broken_frontmatter(self):
        sync = load("agents_sync")
        with self.assertRaises(ValueError):
            sync.read_frontmatter("name: ohne-frontmatter\n")
        fields, body = sync.read_frontmatter("---\r\nname: a\r\ndescription: b\r\n---\r\n\r\nText")
        self.assertEqual(fields, {"name": "a", "description": "b"})
        self.assertEqual("---\nname: a\ndescription: b\n---\n\nText"[body:], "\nText")

    def test_claude_may_self_merge_but_not_force_or_push_protected_branches(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow, deny = settings["permissions"]["allow"], settings["permissions"]["deny"]
        self.assertIn("Bash(gh pr merge:*)", allow)
        for rule in ("Bash(git push --force:*)", "Bash(git push origin main:*)", "Bash(git add -A:*)", "Read(./.env)"):
            self.assertIn(rule, deny)
        self.assertTrue(set(allow).isdisjoint(deny))

    def test_claude_hooks_bring_the_board_into_every_session(self):
        hooks = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]
        for event, command in (("SessionStart", "hook-start"), ("UserPromptSubmit", "hook-prompt")):
            with self.subTest(event=event):
                commands = [hook["command"] for entry in hooks[event] for hook in entry["hooks"]]
                self.assertTrue(any("tools/board" in c and c.endswith(command) for c in commands))

    def test_rules_name_the_configured_board_and_every_role(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        issue = json.loads((ROOT / "tools" / "board.json").read_text(encoding="utf-8"))["issue"]
        self.assertIn(f"pinned issue #{issue}", agents)
        for heading in ("## 2. The board", "## 3. Ownership", "gh pr merge --squash --delete-branch"):
            self.assertIn(heading, agents)

    def test_vendored_skills_keep_their_license(self):
        for name in ("grill-me", "grilling", "handoff", "to-tickets", "tdd", "diagnosing-bugs", "prototype"):
            with self.subTest(skill=name):
                self.assertIn("MIT License", (ROOT / ".agents" / "skills" / name / "LICENSE").read_text(encoding="utf-8"))

    def test_shell_scripts_are_portable(self):
        for path, shebang in (("tools/hooks/pre-push", b"#!/bin/sh\n"), ("tools/board", b"#!/bin/sh\n"),
                              ("tools/firstmate/setup.sh", b"#!/usr/bin/env bash\n"),
                              ("tools/leitstelle.sh", b"#!/usr/bin/env bash\n")):
            with self.subTest(path=path):
                script = (ROOT / path).read_bytes()
                self.assertTrue(script.startswith(shebang))
                self.assertNotIn(b"\r\n", script, "Scripts need LF line endings to run on macOS")
        hook = (ROOT / "tools" / "hooks" / "pre-push").read_bytes()
        self.assertIn(b"refs/heads/main", hook)
        self.assertIn(b"refs/heads/demo", hook)
        self.assertIn(b"-m unittest discover -s tests", hook)

    def test_firstmate_dispatch_rules_are_complete(self):
        for name in ("crew-dispatch.json", "crew-dispatch.budget.json"):
            dispatch = json.loads((ROOT / "tools" / "firstmate" / name).read_text(encoding="utf-8"))
            self.assertTrue(dispatch["default"])
            for rule in dispatch["rules"]:
                with self.subTest(file=name, rule=rule["when"][:40]):
                    profiles = rule["use"] if isinstance(rule["use"], list) else [rule["use"]]
                    self.assertTrue(profiles and all(profile.get("harness") for profile in profiles))
        self.assertTrue(json.loads((ROOT / "tools" / "firstmate" / "crew-dispatch.budget.json").read_text(encoding="utf-8"))["shared_quota"])
        captain = (ROOT / "tools" / "firstmate" / "captain.md").read_text(encoding="utf-8")
        for placeholder in ("<LOGIN>", "<NAME>", "<BOARD>"):
            self.assertIn(placeholder, captain)

    def test_local_agent_files_stay_out_of_git(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in (".claude/settings.local.json", ".auftrag.md", ".board/", ".env"):
            self.assertIn(entry, ignored)


class TaskScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load("aufgabe")

    def test_reads_issue_form_fields(self):
        body = ("### Verantwortliche Person\n\nleon1ce\n\n### Ergebnis und Abnahmetest\n\nAfter reset the field is empty.\n\n"
                "### Bereich\n\nweb/app/page.tsx\n\n### Zielbranch\n\nmain\n\n"
                "### Werkzeug\n\nCodex\n\n### Schnittstellen und Abhängigkeiten\n\n_No response_")
        fields = self.task.parse_form(body)
        self.assertEqual(fields["Verantwortliche Person"], "leon1ce")
        self.assertEqual(fields["Bereich"], "web/app/page.tsx")
        self.assertNotIn("Schnittstellen und Abhängigkeiten", fields)
        self.assertEqual(self.task.base_branch(fields, body), "main")

    def test_english_form_produces_assignment_and_explicit_target_branch(self):
        body = ("### Owner\n\nexample-user\n\n### Scope\n\nweb/app/page.tsx\n\n"
                "### Target branch\n\nrelease/english\n\n### Tool\n\nCodex\n\n"
                "### Outcome and acceptance test\n\nAn empty upload displays an error.\n\n"
                "### Interfaces and dependencies\n\nBlocked by #12.")
        fields = self.task.parse_form(body)
        self.assertEqual(self.task.base_branch(fields, body), "release/english")
        text = self.task.assignment({"number": 7, "title": "Upload", "body": body},
                                    fields, "7-upload", "release/english")
        for value in ("**Owner:** example-user", "web/app/page.tsx", "**Tool:** Codex",
                      "An empty upload displays an error.", "Blocked by #12."):
            self.assertIn(value, text)
        self.assertNotIn("see issue text below", text)

    def test_finds_target_branch_in_free_text_issues(self):
        self.assertEqual(self.task.base_branch({}, "Keyboard checked. PR target is main."), "main")
        self.assertEqual(self.task.base_branch({}, "The case starts on `main`."), "main")
        self.assertIsNone(self.task.base_branch({}, "The domain stays unchanged."))

    def test_branch_names_are_short_and_ascii(self):
        self.assertEqual(self.task.branch_name(7, "Freitag · Agentenauftrag Oberfläche: Eingabe zurücksetzen"),
                         "7-eingabe-zuruecksetzen")
        name = self.task.branch_name(12, "Task · " + "very long description " * 5)
        self.assertLessEqual(len(name), 43)
        self.assertRegex(name, r"^12-[a-z0-9-]+[a-z0-9]$")
        self.assertEqual(self.task.branch_name(3, "···"), "3")

    def test_model_label_picks_model_and_launch_command(self):
        self.assertEqual(self.task.model_class([{"name": "agent-bereit"}, {"name": "modell:klein"}]), "klein")
        self.assertEqual(self.task.model_class([{"name": "modell:text"}]), "text")
        writing = self.task.launch_commands("text")
        self.assertIn("claude --model haiku", writing["Claude Code"])
        self.assertIn("codex -m gpt-6-luna", writing["Codex"])
        self.assertEqual(self.task.model_class([{"name": "modell:gibtsnicht"}]), "standard")
        self.assertEqual(self.task.model_class([]), "standard")
        ui = self.task.launch_commands("ui")
        self.assertIn("claude --model opus", ui["Claude Code"])
        self.assertNotIn("Codex", ui)
        text = self.task.assignment({"number": 3, "title": "t", "labels": [{"name": "modell:bugfix"}]}, {}, "3-t", "main")
        self.assertIn("Model class:** `bugfix`", text)

    def test_model_table_matches_firstmate_rules_and_labels(self):
        models = json.loads((ROOT / "tools" / "modelle.json").read_text(encoding="utf-8"))["klassen"]
        dispatch = (ROOT / "tools" / "firstmate" / "crew-dispatch.json").read_text(encoding="utf-8")
        for klasse, row in models.items():
            with self.subTest(klasse=klasse):
                if klasse != "standard":
                    self.assertIn(f"modell:{klasse}", dispatch)
                for model in (row.get("claude"), row.get("codex")):
                    if model:
                        self.assertIn(f'"{model}"', dispatch)

    def test_assignment_names_branch_target_and_acceptance(self):
        issue = {"number": 7, "title": "Reset", "url": "https://example.test/7", "body": "Text"}
        text = self.task.assignment(issue, {"Bereich": "web/app/page.tsx"}, "7-reset", "main")
        for fragment in ("issue #7", "`7-reset`", "`main`", "web/app/page.tsx",
                         "Closes #7", "python -m unittest discover -s tests -v", "AGENTS.md"):
            self.assertIn(fragment, text)


class KeyCheckTests(unittest.TestCase):
    def test_key_check_names_providers_but_never_values(self):
        import os
        import tempfile
        from unittest.mock import patch
        setup = load("setup")
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env.local"
            env_file.write_text("OPENAI_API_KEY=sk-geheim\nGEMINI_API_KEY=\n# ANTHROPIC_API_KEY=x\n", encoding="utf-8")
            clean = {k: v for k, v in os.environ.items() if k not in setup.KEY_NAMES}
            with patch.dict(os.environ, clean, clear=True):
                found = setup.key_status(env_file)
        self.assertEqual(found, ["OpenAI (.env.local)"])
        self.assertNotIn("sk-geheim", " ".join(found))


class SetupScriptTests(unittest.TestCase):
    def test_report_lists_facts_for_the_laptop_issue(self):
        setup = load("setup")
        text = setup.report({"System": "macOS 15", "Branch": "main", "Tests": "Ran 3 tests, OK"})
        self.assertIn("- System: macOS 15", text)
        self.assertIn("- Tests: Ran 3 tests, OK", text)
        self.assertTrue(re.search(r"(Windows|macOS|Linux|\w+) ", setup.operating_system()))


if __name__ == "__main__":
    unittest.main()
