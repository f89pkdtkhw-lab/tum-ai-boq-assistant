"""Graphify provisioning stays offline in tests and reports actionable failures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("graphify_team_setup", ROOT / "tools/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class GraphifySetupTests(unittest.TestCase):
    def provision(self, installed, available, results):
        def which(name):
            if name == "graphify":
                return next(installed)
            return f"/tools/{name}" if name in available else None

        with patch.object(setup.shutil, "which", side_effect=which), patch.object(
            setup, "run", side_effect=results
        ) as run:
            status, detail = setup.setup_graphify()
        return status, detail, run

    def test_existing_cli_registers_skill_without_installing_or_extracting(self):
        status, _, run = self.provision(iter(["/tools/graphify"]), set(), [(0, "v"), (0, "ok")])
        self.assertEqual(status, "ok")
        self.assertEqual([c.args for c in run.call_args_list], [
            ("/tools/graphify", "--version"), ("/tools/graphify", "install")])

    def test_missing_cli_prefers_uv_then_checks_and_registers(self):
        status, _, run = self.provision(iter([None, "/tools/graphify"]), {"uv", "pipx"}, [(0, "ok")] * 3)
        self.assertEqual(status, "ok")
        self.assertEqual(run.call_args_list[0].args, ("uv", "tool", "install", "graphifyy"))
        self.assertEqual(run.call_args_list[-1].args, ("/tools/graphify", "install"))

    def test_pipx_is_used_when_uv_is_missing(self):
        status, _, run = self.provision(iter([None, "/tools/graphify"]), {"pipx"}, [(0, "ok")] * 3)
        self.assertEqual(status, "ok")
        self.assertEqual(run.call_args_list[0].args, ("pipx", "install", "graphifyy"))

    def test_no_installer_reports_missing_without_network(self):
        status, detail, run = self.provision(iter([None]), set(), [])
        self.assertEqual(status, "fail")
        self.assertIn("MISSING", detail)
        run.assert_not_called()

    def test_install_failure_stops_and_does_not_leak_process_output(self):
        status, detail, run = self.provision(iter([None]), {"uv"}, [(1, "private stderr")])
        self.assertEqual(status, "fail")
        self.assertNotIn("private stderr", detail)
        self.assertEqual(run.call_count, 1)

    def test_install_without_path_entry_is_a_failure(self):
        status, detail, run = self.provision(iter([None, None]), {"uv"}, [(0, "ok")])
        self.assertEqual(status, "fail")
        self.assertIn("PATH", detail)
        self.assertEqual(run.call_count, 1)

    def test_broken_cli_and_failed_skill_registration_are_failures(self):
        for results, expected in [([(1, "error")], "cannot start"),
                                  ([(0, "v"), (1, "error")], "install failed")]:
            with self.subTest(expected=expected):
                status, detail, _ = self.provision(iter(["/tools/graphify"]), set(), results)
                self.assertEqual(status, "fail")
                self.assertIn(expected, detail)

    def test_setup_surfaces_graphify_failure_in_report(self):
        with patch.object(setup, "run", return_value=(0, "ok")), patch.object(
            setup.shutil, "which", return_value=None
        ), patch.object(setup, "key_status", return_value=[]), patch.object(
            setup, "setup_graphify", return_value=("fail", "MISSING: graphify")
        ):
            rows, facts = setup.check(fix_hooks=False)
        self.assertIn(("fail", "Graphify", "MISSING: graphify"), rows)
        self.assertEqual(facts["Graphify"], "MISSING: graphify")

    def test_confidential_paths_and_generated_graph_are_excluded(self):
        # Gitignore semantics independently validate the Graphify ignore patterns.
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            (temp / ".gitignore").write_text((ROOT / ".graphifyignore").read_text())
            for name in ("data/datensatz/lv.x83", "data/testfaelle/case/lv.pdf", ".env.local",
                         "docs/quellen/source.pdf", "graphify-out/graph.json"):
                with self.subTest(path=name):
                    result = subprocess.run(["git", "check-ignore", "--no-index", "-q", name], cwd=temp)
                    self.assertEqual(result.returncode, 0)
            result = subprocess.run(["git", "check-ignore", "--no-index", "-q", "api/app/main.py"], cwd=temp)
            self.assertEqual(result.returncode, 1)
