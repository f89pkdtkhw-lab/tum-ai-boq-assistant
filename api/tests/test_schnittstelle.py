"""HTTP contract acceptance: no keys, no external services."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_synthetic_upload_then_report_keeps_all_positions_and_source():
    raw = (ROOT / "data/beispiel_lv.json").read_bytes()
    response = client.post("/api/lv/import", files={"datei": ("beispiel.json", raw, "application/json")})
    assert response.status_code == 200, response.text
    lv = response.json()
    assert len(lv["positionen"]) == 30
    assert len({tuple(p["titel_pfad"]) for p in lv["positionen"]}) == 3
    report = client.post("/api/lv/pruefen", json=lv)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["lv"] == lv
    assert body["kennzahlen"]["positionen"] == 30
    assert body["kennzahlen"]["modell_mock"] is True
    for finding in body["findings"]:
        assert finding["oz"] in {p["oz"] for p in lv["positionen"]}
        assert finding["quelle"] in ("regel", "modell")
        # The model mock must not invent euro impact; fixed rules may report a
        # directly evidenced value (e.g. an arithmetic error difference).
        if finding["quelle"] == "modell":
            assert finding["euro_wirkung"] is None
        else:
            assert finding["euro_wirkung"] is None or isinstance(finding["euro_wirkung"], (int, float))


def test_examples_include_the_same_typed_lv():
    response = client.get("/api/beispiele")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == "synthetisch-rohbau"
    assert item["lv"] == json.loads((ROOT / "data/beispiel_lv.json").read_text(encoding="utf-8"))


def test_import_errors_are_readable_and_do_not_include_uploaded_content():
    for filename, raw, expected in [
        ("kaputt.json", b'{"secret-document-text":', 422),
        ("leer.json", b"", 422), ("unbekannt.exe", b"abc", 422),
        ("angebot.x83", b"abc", {422, 501}), ("angebot.xlsx", b"abc", {422, 501}), ("angebot.pdf", b"abc", {422, 501}),
    ]:
        response = client.post("/api/lv/import", files={"datei": (filename, raw)})
        assert response.status_code in (expected if isinstance(expected, set) else {expected})
        assert isinstance(response.json()["detail"], str)
        assert "secret-document-text" not in response.text


def test_upload_limit_is_enforced():
    response = client.post("/api/lv/import", files={"datei": ("gross.json", b"x" * (10 * 1024 * 1024 + 1))})
    assert response.status_code == 413


def test_unknown_values_zero_duplicate_oz_and_missing_prices_survive_roundtrip():
    lv = {"name": "Unbepreist", "quelle": "synthetisch", "positionen": [
        {"oz": "01", "menge": None}, {"oz": "01", "menge": 0},
    ]}
    response = client.post("/api/lv/pruefen", json=lv)
    assert response.status_code == 200
    positions = response.json()["lv"]["positionen"]
    assert [p["menge"] for p in positions] == [None, 0]
    assert all(p["ep"] is None and p["gp"] is None for p in positions)


def test_public_routes_fall_back_to_mock_when_the_selected_provider_fails(monkeypatch):
    """#147: a configured provider is used; when its call fails, every route still answers (mock + reason)."""
    import httpx
    def no_network(*args, **kwargs):
        raise AssertionError("Offline route attempted a network request")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-value")
    monkeypatch.setattr(httpx, "post", no_network)
    health = client.get("/health").json()
    assert health["provider"] == "anthropic" and health["mock"] is False
    asked = client.post("/api/ask", json={"question": "Offline?"}).json()
    assert asked["provider"] == "mock" and asked["mock"] is True and asked["reason"]
    lv = json.loads((ROOT / "data/beispiel_lv.json").read_text(encoding="utf-8"))
    report = client.post("/api/lv/pruefen", json=lv)
    assert report.status_code == 200
    kennzahlen = report.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is True and "No AI findings in this run" in kennzahlen["modell_reason"]
    assert "synthetic-test-value" not in report.text


def test_invalid_position_and_nonfinite_numbers_are_rejected():
    for position in ({"oz": ""}, {"oz": "01", "menge": "NaN"}, {"oz": "01", "typ": "erfunden"}):
        response = client.post("/api/lv/pruefen", json={"name": "Test", "quelle": "synthetisch", "positionen": [position]})
        assert response.status_code == 422
