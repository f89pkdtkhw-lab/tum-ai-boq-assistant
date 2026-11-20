"""Regression checks for paired results used as pitch evidence."""
from pathlib import Path
import runpy
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/demo-vergleich/scripts/vergleich.py"
summarize = runpy.run_path(str(SCRIPT))["summarize"]


class DemoVergleichTests(unittest.TestCase):
    def test_equal_totals_keep_gains_losses_and_outages_visible(self):
        rows = [
            {"fall": "A", "soll": "frei", "bisher": "belegt", "prototyp": "frei"},
            {"fall": "B", "soll": "voll", "bisher": "voll", "prototyp": None},
        ]
        self.assertEqual(summarize(rows), (1, 1, 2, ["A"], ["B"], ["B (prototyp)"]))

    def test_incomplete_or_duplicate_cases_are_not_scored(self):
        row = {"fall": "A", "soll": "ok", "bisher": "ok", "prototyp": "ok"}
        for rows in ([], [row, dict(row)], [{k: v for k, v in row.items() if k != "bisher"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                summarize(rows)
