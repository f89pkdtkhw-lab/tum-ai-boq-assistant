import json
import socket

import pytest

from app.modelle import LV, Position
from app.pruefung.llm_pruefung import (
    pruefe_in_batches, pruefe_mit_llm, stable_id, validiere_antwort,
)

KATALOG = {"VOB/C-DIN18299-0.2": "Test catalogue entry: description of the service"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access in offline test")
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def lv_of(*ozs, **texte):
    return LV(name="Test", quelle="synthetisch",
              positionen=[Position(oz=o, kurztext=texte.get(o.replace(".", "_"), "")) for o in ozs])


def finding(oz, regel_id="MOCK_VAGUE", **over):
    base = {"oz": oz, "kategorie": "risiko", "schwere": "mittel", "titel": "Vague text",
            "begruendung": "Text says 'as required'.", "vorschlag": "Specify.",
            "quelle": "modell", "regel_id": regel_id, "euro_wirkung": None}
    base.update(over)
    return base


def answer(*findings):
    return json.dumps({"findings": list(findings)})


def test_default_mock_uses_an_existing_oz_and_is_marked_as_demonstration(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")  # selected provider, no key
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = pruefe_mit_llm(lv_of("8...3", "8...4"))
    assert len(result) == 1
    f = result[0]
    assert f.oz == "8...3" and f.quelle == "modell" and f.euro_wirkung is None
    assert f.regel_id == "MOCK_LLM" and f.regel_id.startswith("MOCK_")
    assert "Demonstration" in f.titel and "Demonstration" in f.begruendung
    assert pruefe_mit_llm(LV(name="Leer", quelle="synthetisch")) == []


def test_batch_size_limits_items_per_model_call():
    sizes = []

    def model(batch):
        sizes.append(len(batch))
        return answer()
    pruefe_in_batches(lv_of(*[f"1.{i}" for i in range(7)]), model, batch_size=3)
    assert sizes == [3, 3, 1]
    with pytest.raises(ValueError):
        pruefe_in_batches(lv_of("1"), model, batch_size=0)


def test_ids_are_stable_across_batch_sizes():
    lv = lv_of("1.1", "1.2", "1.3")
    model = lambda batch: answer(*[finding(p.oz) for p in batch])  # noqa: E731
    ids = [[f.id for f in pruefe_in_batches(lv, model, batch_size=n).findings] for n in (1, 2, 5)]
    assert ids[0] == ids[1] == ids[2] == [stable_id(o, "MOCK_VAGUE") for o in ("1.1", "1.2", "1.3")]


@pytest.mark.parametrize("raw", ["not json", "", "[]", '{"findings": 3}', "null"])
def test_invalid_json_is_handled_safely(raw):
    result = pruefe_in_batches(lv_of("1.1"), lambda b: raw)
    assert result.findings == [] and result.rejected


def test_failing_model_is_handled_safely():
    def boom(batch):
        raise RuntimeError("provider down")
    result = pruefe_in_batches(lv_of("1.1"), boom)
    assert result.findings == [] and "model call failed" in result.rejected[0]


def test_invented_oz_and_empty_boq():
    result = validiere_antwort(answer(finding("9.9"), finding("1.1")), lv_of("1.1").positionen)
    assert [f.oz for f in result.findings] == ["1.1"] and len(result.rejected) == 1
    called = []
    assert pruefe_in_batches(LV(name="Leer", quelle="s"), lambda b: called.append(1) or answer()).findings == []
    assert called == []


@pytest.mark.parametrize("over", [
    {"quelle": "regel"}, {"kategorie": "stil"}, {"schwere": "extrem"},
    {"regel_id": "VOB_REAL"}, {"euro_wirkung": 1200.0}, {"titel": ""}, {"extra": 1},
])
def test_invalid_fields_are_rejected(over):
    result = validiere_antwort(answer(finding("1.1", **over)), lv_of("1.1").positionen)
    assert result.findings == [] and len(result.rejected) == 1


def test_vague_and_contradiction_fixtures_are_marked_as_demonstration():
    lv = LV(name="T", quelle="s", positionen=[
        Position(oz="1.1", kurztext="Concrete", langtext="as required, if applicable"),
        Position(oz="1.2", kurztext="Pipe DN100", langtext="Pipe DN150 laid"),
    ])
    raw = answer(finding("1.1", "MOCK_VAGUE"),
                 finding("1.2", "MOCK_CONTRADICTION", kategorie="fehler", titel="Short/long text differ"))
    findings = validiere_antwort(raw, lv.positionen).findings
    assert [f.regel_id for f in findings] == ["MOCK_VAGUE", "MOCK_CONTRADICTION"]
    assert all("Demonstration" in f.titel and "Demonstration" in f.begruendung for f in findings)


def test_standard_reference_needs_catalogue_evidence():
    pos = lv_of("1.1").positionen
    ok = validiere_antwort(answer(finding("1.1", norm_ref="VOB/C-DIN18299-0.2")), pos, KATALOG)
    assert len(ok.findings) == 1 and "VOB/C-DIN18299-0.2" in ok.findings[0].begruendung
    assert "Demonstration" in ok.findings[0].begruendung
    for catalogue in (KATALOG, None):
        bad = validiere_antwort(answer(finding("1.1", norm_ref="DIN 99999")), pos, catalogue)
        assert bad.findings == [] and "catalogue" in bad.rejected[0]
