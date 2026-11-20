"""Offline-Tests für das Lagebild tools/stand.py."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("team_stand", ROOT / "tools" / "stand.py")
stand = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stand)


def issue(number, status, bereich, assignees=()):
    return {"number": number, "title": f"Aufgabe {number}", "status": status,
            "assignees": list(assignees), "labels": [], "bereich": bereich}


class StandTests(unittest.TestCase):
    def test_area_paths_accept_commas_newlines_and_backticks(self):
        self.assertEqual(stand.area_paths("`api/app/lv/`, api/tests/test_import_gaeb.py\nweb/app"),
                         ["api/app/lv", "api/tests/test_import_gaeb.py", "web/app"])

    def test_folder_overlaps_file_inside_it(self):
        self.assertTrue(stand.paths_overlap("api/app/lv", "api/app/lv/gaeb.py"))
        self.assertFalse(stand.paths_overlap("api/app/lv", "api/app/lvx.py"))

    def test_claimed_issues_sharing_a_folder_are_reported(self):
        conflicts = stand.area_conflicts([issue(3, "in Arbeit", ["api/app/lv"]),
                                          issue(4, "in Arbeit", ["api/app/lv/pdf.py"]),
                                          issue(5, "in Arbeit", ["web"])])
        self.assertEqual(conflicts, [(3, 4, ["api/app/lv", "api/app/lv/pdf.py"])])

    def test_files_touched_by_two_prs_are_reported(self):
        prs = [{"number": 7, "files": ["api/app/main.py", "a.py"]}, {"number": 8, "files": ["api/app/main.py"]}]
        self.assertEqual(stand.file_conflicts(prs), {"api/app/main.py": [7, 8]})

    def test_next_issue_prefers_own_then_free_and_skips_busy_areas(self):
        data = {"issues": [issue(3, "in Arbeit", ["api/app/lv"], ["Anatomik5"]),
                           issue(4, "bereit", ["api/app/lv/pdf.py"]),
                           issue(5, "bereit", ["web"]),
                           issue(6, "bereit", ["api/app/pruefung"], ["Bartuan3600"])]}
        self.assertEqual(stand.next_issue(data, "Bartuan3600")["number"], 6)
        self.assertEqual(stand.next_issue(data, "Zukipany")["number"], 5)

    def test_ci_state(self):
        self.assertEqual(stand.ci_state([]), "–")
        self.assertEqual(stand.ci_state([{"conclusion": "SUCCESS"}]), "grün")
        self.assertEqual(stand.ci_state([{"conclusion": "SUCCESS"}, {"status": "IN_PROGRESS"}]), "läuft")
        self.assertEqual(stand.ci_state([{"conclusion": "FAILURE"}]), "rot")


if __name__ == "__main__":
    unittest.main()
