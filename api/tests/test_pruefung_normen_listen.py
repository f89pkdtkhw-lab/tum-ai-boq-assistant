"""Norm check N6 (issue #90): closed-list checks. Synthetic fixtures only; offline, no model calls."""
import re

import pytest

from app import main
from app.modelle import LV, Position
from app.pruefung.normen import KEIN_NORMGUTACHTEN, pruefe_normen
from app.pruefung.normen_listen import NORM_KLASSE_UNGUELTIG, NORM_PRODUKTNORM_WIDERSPRUCH, pruefe_listen

CLAIM_WORDS = re.compile(r"violat|breach|verstoß|verstoss|non-?complian", re.IGNORECASE)


def lv_mit(*texte: str) -> LV:
    return LV(name="Synthetic list LV", quelle="test", positionen=[
        Position(oz=f"01.{i:02d}", kurztext="Item", langtext=text, menge=1, einheit="St")
        for i, text in enumerate(texte, start=1)
    ])


def ids(text: str) -> list[str]:
    return [f.regel_id for f in pruefe_listen(lv_mit(text))]


@pytest.mark.parametrize("text", [
    "Concrete XC4/XF1//WF", "Concrete XC5", "Concrete XF5", "Concrete C25/35",
    "Concrete XC4/XF1/WX",
])
def test_invalid_class_yields_one_finding(text):
    assert ids(text) == [NORM_KLASSE_UNGUELTIG]


@pytest.mark.parametrize("text", [
    "Concrete XC4, XF1, WF, C25/30", "Concrete X0 XD3 XS1 XA2 XM3 WA WS W0", "Concrete C8/10 C100/115 C30/37",
    "Lightweight LC25/28", "Concrete XC4, Wasserdicht", "Plain text without classes", "Concrete XC0 and XC0/XC1",
])
def test_valid_classes_yield_nothing(text):
    assert ids(text) == []


def test_klasse_finding_quotes_only_offending_token():
    (f,) = pruefe_listen(lv_mit("Concrete C25/30 XC4 XC5"))
    assert f.kategorie == "fehler" and f.schwere == "mittel" and f.quelle == "regel"
    assert f.id == f"{NORM_KLASSE_UNGUELTIG}:01.01"
    assert '"XC5"' in f.begruendung and "XC4" not in f.begruendung and "DIN EN 206" in f.begruendung
    assert KEIN_NORMGUTACHTEN in f.begruendung and not CLAIM_WORDS.search(f.begruendung + f.vorschlag)


def test_empty_element_is_named():
    (f,) = pruefe_listen(lv_mit("XC4/XF1//WF"))
    assert "empty element" in f.begruendung


@pytest.mark.parametrize("text, expected", [
    ("XPS insulation board according to DIN EN 13162", [NORM_PRODUKTNORM_WIDERSPRUCH]),
    ("XPS insulation board according to DIN EN 13164", []),
    ("Mineralwolle according to DIN EN 13162", []),
    ("Insulation board according to DIN EN 13162", []),
    ("Mineralwolle and EPS according to DIN EN 13162", []),
    ("extrudierter Polystyrol-Hartschaum nach DIN EN 13164", []),
    ("Polystyrol-Hartschaum nach DIN EN 13163", []),
    ("Holzfaserplatte nach DIN EN 13163", [NORM_PRODUKTNORM_WIDERSPRUCH]),
    ("Schaumglas nach DIN EN 13167 und DIN EN 13165", []),
    ("XPS nach EN 13162 und EN 13163", [NORM_PRODUKTNORM_WIDERSPRUCH]),
])
def test_product_standard(text, expected):
    assert ids(text) == expected


def test_produktnorm_finding_is_bidder_question():
    (f,) = pruefe_listen(lv_mit("XPS board DIN EN 13162"))
    assert f.kategorie == "fehler" and f.schwere == "mittel" and f.quelle == "regel"
    assert "Which product standard applies to the specified material" in f.vorschlag
    assert KEIN_NORMGUTACHTEN in f.begruendung and not CLAIM_WORDS.search(f.begruendung + f.vorschlag)


def test_pruefe_normen_includes_listen_in_position_order():
    lv = lv_mit("Plain", "XPS board DIN EN 13162", "Concrete XC5")
    found = [(f.oz, f.regel_id) for f in pruefe_normen(lv) if f.regel_id.startswith("NORM_") and
             f.regel_id in (NORM_KLASSE_UNGUELTIG, NORM_PRODUKTNORM_WIDERSPRUCH)]
    assert found == [("01.02", NORM_PRODUKTNORM_WIDERSPRUCH), ("01.03", NORM_KLASSE_UNGUELTIG)]


def test_switch_off_leaves_report_unchanged(monkeypatch):
    lv = lv_mit("Concrete XC5", "XPS board DIN EN 13162")
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    assert not any(f.regel_id in (NORM_KLASSE_UNGUELTIG, NORM_PRODUKTNORM_WIDERSPRUCH)
                   for f in main.pruefen(lv).findings)
