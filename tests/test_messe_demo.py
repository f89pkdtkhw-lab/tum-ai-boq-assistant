"""Measurement logic of tools/messe_demo.py on a small fixed example (offline, standard library only)."""
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "tools/messe_demo.py"))
parse_gold, expand_oz, measure, ACCEPTED = MODULE["parse_gold"], MODULE["expand_oz"], MODULE["measure"], MODULE["ACCEPTED"]

# Synthetic gold table in the format of erwartung.md; it contains no partner or benchmark content.
GOLD = """
| # | OZ | Kat. | Befund | Regel? |
|---|---|---|---|---|
| 1 | 1...1 | F | hit expected | ja |
| 2 | 1...2 | F | rule exists but does not fire | ja |
| 3 | 2...1 | R | no rule yet | LLM |
| 4 | Titel 3 | R | whole title | ja |
| 5 | Vorbem. S. 1 | R | no OZ at all | LLM |
"""
A = frozenset
EXAMPLE_ACCEPTED = {
    1: (A({"EINHEIT_FEHLT"}), False, "x"), 2: (A({"TEXT_WIDERSPRUCH"}), False, "x"),
    3: (A(), False, "x"), 4: (A({"RISK_STUNDENLOHN"}), True, "x"), 5: (A(), False, "x"),
}


def finding(oz, regel_id, id_=None):
    return {"id": id_ or f"{regel_id}:{oz}", "oz": oz, "regel_id": regel_id}


class MesseDemoTests(unittest.TestCase):
    def test_example_with_false_alarm_and_missed_findings_is_counted_exactly(self):
        findings = [
            finding("1...1", "EINHEIT_FEHLT"),          # hit for #1
            finding("3...1", "RISK_STUNDENLOHN"),       # hit for #4 (inside title 3)
            finding("3...2", "RISK_STUNDENLOHN"),       # second finding for #4, still one hit
            finding("1...2", "EINHEIT_TIPPFEHLER"),     # on a gold OZ but a different rule: false alarm
            finding("9...9", "MENGE_FEHLT"),            # false alarm: no gold entry
            finding("2...1", "MOCK_LLM"),               # model mock: excluded, must not count as hit or alarm
        ]
        result = measure(parse_gold(GOLD), EXAMPLE_ACCEPTED, findings)
        self.assertEqual((result["gold_total"], result["hits"], result["missed"]), (5, 2, 3))
        self.assertEqual(result["generic_hits"], 1)
        self.assertEqual((result["rule_findable_hits"], result["rule_findable_total"]), (2, 3))
        self.assertEqual((result["findings_considered"], result["findings_mock_excluded"]), (5, 1))
        self.assertEqual((result["findings_matched"], result["false_alarms"]), (3, 2))
        self.assertEqual(result["false_alarm_list"], [{"oz": "1...2", "regel_id": "EINHEIT_TIPPFEHLER"},
                                                      {"oz": "9...9", "regel_id": "MENGE_FEHLT"}])
        by_nr = {r["nr"]: r for r in result["entries"]}
        self.assertEqual(by_nr[1]["matched"], ["1...1 EINHEIT_FEHLT"])
        self.assertEqual(by_nr[4]["matched"], ["3...1 RISK_STUNDENLOHN", "3...2 RISK_STUNDENLOHN"])
        self.assertIn("did not fire", by_nr[2]["reason"])
        self.assertIn("no fixed rule", by_nr[3]["reason"])
        self.assertIn("no item OZ", by_nr[5]["reason"])
        self.assertEqual(result["by_category"], {"F": {"hits": 1, "total": 2}, "R": {"hits": 1, "total": 3}})

    def test_mock_finding_alone_never_counts_as_a_hit(self):
        accepted = {**EXAMPLE_ACCEPTED, 3: (A({"MOCK_LLM"}), False, "x")}
        result = measure(parse_gold(GOLD), accepted, [finding("2...1", "MOCK_LLM")])
        self.assertEqual((result["hits"], result["false_alarms"], result["findings_considered"]), (0, 0, 0))

    def test_no_findings_means_no_hits_and_no_false_alarms(self):
        result = measure(parse_gold(GOLD), EXAMPLE_ACCEPTED, [])
        self.assertEqual((result["hits"], result["missed"], result["false_alarms"]), (0, 5, 0))

    def test_oz_cells_of_the_gold_format_are_expanded(self):
        self.assertEqual(expand_oz("8...3"), (("8...3",), ()))
        self.assertEqual(expand_oz("3...1 / 3...2 / 4...4 / 4...5"), (("3...1", "3...2", "4...4", "4...5"), ()))
        self.assertEqual(expand_oz("4...1–4...4"), (("4...1", "4...2", "4...3", "4...4"), ()))
        self.assertEqual(expand_oz("5...15, 5...16"), (("5...15", "5...16"), ()))
        self.assertEqual(expand_oz("Titel 7"), ((), ("7",)))
        for cell in ("Vorbem. S. 1", "div."):
            self.assertEqual(expand_oz(cell), ((), ()))
        with self.assertRaises(ValueError):
            expand_oz("4...4–4...1")

    def test_real_gold_standard_still_has_25_entries_covered_by_the_mapping(self):
        gold = ROOT / "data/testfaelle/rohbau_efh/erwartung.md"
        if not gold.exists():
            self.skipTest("benchmark test case not present in this checkout")
        entries = parse_gold(gold.read_text(encoding="utf-8"))
        self.assertEqual([e.nr for e in entries], list(range(1, 26)))
        self.assertEqual(set(ACCEPTED), {e.nr for e in entries})


if __name__ == "__main__":
    unittest.main()
