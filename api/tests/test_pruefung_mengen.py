from app.modelle import LV
from app.pruefung.mengen import pruefe_mengen


def test_empty_lv_has_no_invented_findings():
    assert pruefe_mengen(LV(name="Leer", quelle="synthetisch")) == []
