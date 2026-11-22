"""POST /api/db/abschluss (#154): two synthetic files → one history record on a temporary DB file."""
import hashlib
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
API_DIR = ROOT_DIR / "api"
for p in (str(ROOT_DIR), str(API_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pruefung.berichte import _messwerte

COMMITTED_DBS = [ROOT_DIR / "db" / "database.duckdb", ROOT_DIR / "db" / "price.duckdb"]
FIXTURE_X84 = (API_DIR / "tests" / "fixtures" / "gaeb" / "offer.x84").read_bytes()
# Synthetic final bill (GAEB X86): the fixture's single item 01.0010A, qty 2 m², EP 12.50, GP 25.00.
FINAL_X86 = FIXTURE_X84.replace(b"DA84", b"DA86").replace(b"<DP>84", b"<DP>86")

ESTIMATE_LV = {
    "name": "Synthetic estimate", "quelle": "estimate.json",
    "positionen": [
        {"oz": "01.0010A", "kurztext": "Überbau", "menge": 1.5, "einheit": "m²", "ep": 12.5, "gp": 18.75},
        {"oz": "01.0020", "kurztext": "Synthetic extra wall", "menge": 4.0, "einheit": "m²", "ep": 10.0, "gp": 40.0},
    ],
}


def _hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "history.duckdb"))
    vorher = [_hash(p) for p in COMMITTED_DBS]
    yield TestClient(app)
    assert [_hash(p) for p in COMMITTED_DBS] == vorher, "the committed .duckdb files must never be written"


def _post(client, bericht=("estimate.json", json.dumps(ESTIMATE_LV).encode()),
          abrechnung=("final.x86", FINAL_X86), **felder):
    files = {}
    if bericht is not None:
        files["bericht"] = (bericht[0], bericht[1], "application/octet-stream")
    if abrechnung is not None:
        files["abrechnung"] = (abrechnung[0], abrechnung[1], "application/octet-stream")
    return client.post("/api/db/abschluss", files=files, data=felder)


def test_two_files_become_one_record_visible_through_db_actions(client):
    r = _post(client, description="Synthetic house", tags="roof, Timber,roof", note="Late delivery")
    assert r.status_code == 200, r.text
    rec = r.json()
    assert isinstance(rec["id"], int) and rec["date"]
    assert rec["description"] == "Synthetic house"
    assert rec["tags"] == ["roof", "timber"]
    assert rec["note"] == "Late delivery"

    soll = {z["oz"]: z for z in rec["expected_json"]["positionen"]}
    ist = {z["oz"]: z for z in rec["actual_json"]["positionen"]}
    assert soll["01.0010A"]["menge"] == 1.5 and ist["01.0010A"]["menge"] == 2.0
    assert ist["01.0010A"]["menge_delta"] == 0.5 and ist["01.0010A"]["gp_delta"] == 6.25
    assert ist["01.0020"]["fehlt"] is True and ist["01.0020"]["menge"] is None
    assert any("01.0020" in w and "final bill" in w for w in rec["warnungen"])
    assert rec["expected_json"]["quelle"] == "estimate.json" and rec["actual_json"]["quelle"] == "final.x86"
    assert rec["expected_json"]["summe_gp"] == 58.75 and rec["actual_json"]["summe_gp"] == 25.0

    latest = client.get("/api/db/records/latest?limit=5").json()
    assert [x["id"] for x in latest] == [rec["id"]]
    assert {t["tag"]: t["count"] for t in client.get("/api/db/tags").json()} == {"roof": 1, "timber": 1}
    assert [x["id"] for x in client.get("/api/db/records/by-tag/timber").json()] == [rec["id"]]


def test_record_shape_is_read_by_report_2_and_the_history_adapter(client):
    from db.history_adapter import row_to_history_record

    rec = _post(client, tags="roof").json()
    # Report 2/3 (pruefung/berichte.py) reads `positionen`.
    werte = {w["oz"]: w for w in _messwerte(rec["expected_json"])}
    assert werte["01.0010A"] == {"oz": "01.0010A", "kurztext": "Überbau", "menge": 1.5, "einheit": "m²"}
    # The step API history seam (db/history_adapter.py) reads `measurements`.
    hist = row_to_history_record((rec["id"], rec["date"], rec["description"], rec["tags"],
                                  rec["expected_json"], rec["actual_json"], rec["note"]))
    assert [(m.oz, m.metric, m.value, m.unit) for m in hist.real_values] == [("01.0010A", "menge", 2.0, "m²")]
    assert {m.oz for m in hist.estimated_values} == {"01.0010A", "01.0020"}


def test_exported_report_json_uses_the_estimated_bill(client):
    bericht = {"lv": ESTIMATE_LV, "findings": [], "geschaetztes_lv": {"positionen": [
        {"oz": "01.0010A", "status": "updated", "kurztext": "Überbau", "einheit": "m²",
         "menge_alt": 1.5, "menge_neu": 2.5, "ep": 12.5, "gp_alt": 18.75, "gp_neu": 31.25},
    ]}}
    r = _post(client, bericht=("report.json", json.dumps(bericht).encode()), tags="roof")
    assert r.status_code == 200, r.text
    soll = r.json()["expected_json"]["positionen"]
    assert soll == [{"oz": "01.0010A", "kurztext": "Überbau", "menge": 2.5, "einheit": "m²", "ep": 12.5,
                     "gp": 31.25, "status": "updated"}]
    assert r.json()["warnungen"] == []


def test_without_description_and_tags_metadata_is_generated(client):
    r = _post(client)
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["description"].startswith(("Parsed case", "Bridge repair"))
    assert rec["tags"] == []
    assert any("No tags" in w for w in rec["warnungen"])
    assert [x["id"] for x in client.get("/api/db/records/latest").json()] == [rec["id"]]


def test_filename_tags_are_used_when_no_tags_are_given(client):
    r = _post(client, bericht=("estimated_roof_timber.json", json.dumps(ESTIMATE_LV).encode()))
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["roof", "timber"]


@pytest.mark.parametrize("kwargs, status, text", [
    ({"bericht": None}, 422, "bericht"),
    ({"abrechnung": None}, 422, "abrechnung"),
    ({"bericht": ("empty.json", b"")}, 422, "empty.json"),
    ({"abrechnung": ("big.x86", b"x" * (10 * 1024 * 1024 + 1))}, 413, "big.x86"),
    ({"bericht": ("notes.txt", b"hello")}, 422, "notes.txt"),
    ({"bericht": ("broken.json", b"{not json")}, 422, "broken.json"),
    ({"abrechnung": ("broken.x86", b"<GAEB><oops")}, 422, "broken.x86"),
    ({"tags": "two words"}, 422, "two words"),
])
def test_invalid_input_gives_a_readable_error_and_stores_nothing(client, kwargs, status, text):
    r = _post(client, **kwargs)
    assert r.status_code == status, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, str) and text in detail
    assert client.get("/api/db/records/latest").json() == []
