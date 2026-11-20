"""Checks shared by the team setup and the rehearsal branch."""
from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


class TeamSetupTests(unittest.TestCase):
    def test_local_document_links_resolve_from_their_document(self):
        docs = [ROOT / "README.md", ROOT / "AGENTS.md", *(ROOT / "docs").glob("*.md")]
        for document in docs:
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                path = unquote(target.split("#", 1)[0])
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / path).exists())

    def test_local_keys_are_ignored_and_the_example_is_shareable(self):
        for name, expected in [(".env", 0), (".env.local", 0), (".env.example", 1)]:
            with self.subTest(name=name):
                check = subprocess.run(["git", "check-ignore", "--no-index", "-q", name], cwd=ROOT)
                self.assertEqual(check.returncode, expected)
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        settings = [line.partition("=") for line in lines if line and not line.startswith("#")]
        names = [name for name, _, _ in settings]
        self.assertEqual(len(names), len(set(names)), "Each variable occurs only once")
        self.assertTrue({"OPENAI_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "LLM_PROVIDER"} <= set(names))
        self.assertTrue(all(separator == "=" and not value for _, separator, value in settings))
