from app.modelle import LV, Position
from app.pruefung.llm_pruefung import pruefe_mit_llm


def test_mock_uses_an_existing_oz_and_is_marked_as_demonstration(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-value")
    lv = LV(name="Test", quelle="synthetisch", positionen=[Position(oz="8...3")])
    result = pruefe_mit_llm(lv)
    assert len(result) == 1
    assert result[0].oz == "8...3" and result[0].quelle == "modell"
    assert result[0].regel_id == "MOCK_LLM" and "Mock" in result[0].titel
    assert result[0].euro_wirkung is None
    assert pruefe_mit_llm(LV(name="Leer", quelle="synthetisch")) == []
