from app.modelle import LV
from app.pruefung.regeln import pruefe_regeln


def test_empty_lv_has_no_invented_findings():
    assert pruefe_regeln(LV(name="Leer", quelle="synthetisch")) == []
