import unittest

from app.modelle import LV, Position
from app.pruefung.mengen import pruefe_mengen
from app.pruefung.textplausibilitaet import pruefe_textplausibilitaet


def _lv(text: str) -> LV:
    return LV(name="t", quelle="t", positionen=[Position(oz="1.1", kurztext="x", langtext=text)])


def _ids(text: str) -> list[str]:
    return [f.regel_id for f in pruefe_textplausibilitaet(_lv(text))]


class DimensionUnitTest(unittest.TestCase):
    def test_flags_cm_with_metre_precision(self):
        for text in ("Wanddicke 0,240cm", "Wanddicke\n0,240 cm", "d=0,175 cm"):
            self.assertEqual(_ids(text), ["MASS_EINHEIT_UNPLAUSIBEL"], text)

    def test_finding_fields_and_both_readings(self):
        (f,) = pruefe_textplausibilitaet(_lv("Wanddicke 0,240cm"))
        self.assertEqual((f.kategorie, f.schwere, f.quelle, f.euro_wirkung),
                         ("fehler", "mittel", "regel", None))
        self.assertIn("2,4 mm", f.begruendung)
        self.assertIn("24 cm", f.begruendung)

    def test_plausible_values_pass(self):
        for text in ("Wanddicke 24 cm", "Dicke 0,2 mm", "Wanddicke 3 mm", "Breite 0,5 cm",
                     "Ohne Maß 0,240 cm"):
            self.assertEqual(_ids(text), [], text)


class DanglingManufacturerTest(unittest.TestCase):
    def test_flags_dangling_name(self):
        text = "Fabrikat: Musterplatte X, oder gleichwertig.\nBeispielwerk\n\nOberfläche glatt."
        (f,) = pruefe_textplausibilitaet(_lv(text))
        self.assertEqual(f.regel_id, "FABRIKAT_WIDERSPRUCH")
        self.assertEqual((f.kategorie, f.quelle, f.euro_wirkung), ("fehler", "regel", None))
        self.assertIn("Musterplatte X", f.begruendung)
        self.assertIn("Beispielwerk", f.begruendung)

    def test_flags_at_end_of_text(self):
        self.assertEqual(_ids("Fabrikat: Muster, oder gleichwertig\nBeispielwerk"),
                         ["FABRIKAT_WIDERSPRUCH"])

    def test_no_false_alarms(self):
        for text in ("Fabrikat: Muster, oder gleichwertig.\n\nAngebotenes Fabrikat:\n....",
                     "Fabrikat: Muster, oder gleichwertig, liefern und verlegen."):
            self.assertEqual(_ids(text), [], text)


class WiringTest(unittest.TestCase):
    def test_pruefe_mengen_includes_rules(self):
        ids = [f.regel_id for f in pruefe_mengen(_lv("Wanddicke 0,240cm"))]
        self.assertIn("MASS_EINHEIT_UNPLAUSIBEL", ids)


if __name__ == "__main__":
    unittest.main()
