"""#155: Reports 2/3 read the history DB through `db_seams.DuckDBHistory`.

Synthetic records only (invented quantities and notes) in a temporary DuckDB file chosen with
HISTORY_DB_PATH; the committed db/*.duckdb files are never opened. No network, no model.
"""
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

duckdb = pytest.importorskip("duckdb")

from app import db_seams, main  # noqa: E402
from app.pruefung import berichte  # noqa: E402
from app.pruefung.berichte import erstelle_berichte  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = [ROOT / "db" / "database.duckdb", ROOT / "db" / "price.duckdb"]
client = TestClient(main.app)


def _bill(mengen):
    """The shape `POST /api/db/records` stores: parsed bill under `lv.positionen`."""
    return {"total_gp_calculated": 0.0, "lv": {"name": "Synthetic", "positionen": [
        {"oz": f"9.{i}", "kurztext": f"Erdarbeiten Teilfläche {i}", "menge": m, "einheit": "m³"}
        for i, m in mengen.items()]}}


RECORDS = [
    (1, "2026-03-01 10:00:00", "Synthetic earthworks A", ["erdarbeiten", "rohbau"],
     _bill({1: 10, 2: 10}), _bill({1: 13, 2: 11}), "Erdarbeiten Teilfläche quantities underestimated"),
    (2, "2026-04-01 10:00:00", "Synthetic earthworks B", ["erdarbeiten"],
     _bill({1: 10}), _bill({1: 12}), ""),
    (4, "2026-04-15 10:00:00", "Synthetic earthworks C", ["erdarbeiten"],
     _bill({1: 10}), _bill({1: 11}), ""),
    # list shape of db/history_adapter.py (metric/value), also accepted
    (3, "2026-05-01 10:00:00", "Synthetic road", ["strasse"],
     [{"oz": "1", "metric": "menge", "value": 5, "unit": "m²"}],
     [{"oz": "1", "metric": "menge", "value": 5, "unit": "m²"}], "Asphalt milling delayed by frost"),
]


def seed(path: Path, records=RECORDS) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute("""CREATE TABLE database (id UBIGINT, date TIMESTAMP, description VARCHAR,
                        tags VARCHAR[], expected_json JSON, actual_json JSON, note VARCHAR)""")
        conn.executemany("INSERT INTO database VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(i, d, desc, t, json.dumps(e), json.dumps(a), n) for i, d, desc, t, e, a, n in records])
    return path


@pytest.fixture(scope="module", autouse=True)
def committed_db_files_untouched():
    vorher = {p: p.read_bytes() if p.exists() else None for p in COMMITTED}
    yield
    for p, inhalt in vorher.items():
        nachher = p.read_bytes() if p.exists() else None
        assert hashlib.sha256(nachher or b"").digest() == hashlib.sha256(inhalt or b"").digest(), p


@pytest.fixture
def history(tmp_path, monkeypatch):
    pfad = seed(tmp_path / "history.duckdb")
    monkeypatch.setenv("HISTORY_DB_PATH", str(pfad))
    return db_seams.DuckDBHistory()


def demo_lv():
    return main.load_examples()[0].lv


def test_adapter_exposes_the_three_db_actions(history):
    assert history.tags() == [{"tag": "erdarbeiten", "count": 3}, {"tag": "rohbau", "count": 1},
                              {"tag": "strasse", "count": 1}]
    by_tag = history.records_by_tag("erdarbeiten", 20)
    assert [r["id"] for r in by_tag] == [4, 2, 1]  # newest first
    # the DB service's {"lv": {"positionen": …}} level is unwrapped for the reports
    assert by_tag[2]["expected_json"]["positionen"][0]["kurztext"] == "Erdarbeiten Teilfläche 1"
    assert [r["id"] for r in history.records_latest(2)] == [3, 4]


def test_reports_2_and_3_are_connected_with_a_seeded_db(history):
    teile = erstelle_berichte(demo_lv(), [], db=history)
    regelwerk, vergleich, was_wenn = teile["berichte"]
    assert [b.status for b in teile["berichte"]] == ["ok", "ok", "ok"]
    assert vergleich.tags == ["erdarbeiten", "rohbau"]
    by_oz = {n.oz: n for n in vergleich.naeherungen}
    # Teilfläche 1: ratios 1.3, 1.2, 1.1 → median 1.2 on the bill quantity 11 m³
    assert by_oz["01.00.0001"].faktor == 1.2 and by_oz["01.00.0001"].geschaetzt == 13.2
    assert by_oz["01.00.0001"].case_ids == ["4", "2", "1"]
    assert {w.problem for w in was_wenn.probleme} >= {"Erdarbeiten Teilfläche quantities underestimated",
                                                      "Asphalt milling delayed by frost"}


def test_missing_db_stays_not_connected_and_creates_no_file(tmp_path, monkeypatch):
    pfad = tmp_path / "absent.duckdb"
    monkeypatch.setenv("HISTORY_DB_PATH", str(pfad))
    teile = erstelle_berichte(demo_lv(), [], db=db_seams.DuckDBHistory())
    assert [b.status for b in teile["berichte"]] == ["ok", "nicht_verbunden", "nicht_verbunden"]
    assert "not reachable (HistoryDatabaseMissing)" in teile["berichte"][1].meldung
    assert teile["schlussbericht"] is not None and not pfad.exists()


def test_unreadable_db_stays_not_connected(tmp_path, monkeypatch):
    pfad = tmp_path / "broken.duckdb"
    pfad.write_bytes(b"not a duckdb file" * 100)
    monkeypatch.setenv("HISTORY_DB_PATH", str(pfad))
    teile = erstelle_berichte(demo_lv(), [], db=db_seams.DuckDBHistory())
    assert [b.status for b in teile["berichte"]][1:] == ["nicht_verbunden", "nicht_verbunden"]
    assert "HistoryDatabaseUnreadable" in teile["berichte"][2].meldung


def test_startup_wiring(monkeypatch):
    monkeypatch.setattr(berichte, "history_db", None)
    assert db_seams.verbinde_history_db() is False and berichte.history_db is None  # pytest: offline
    assert db_seams.verbinde_history_db(erzwingen=True) is True
    assert isinstance(berichte.history_db, db_seams.DuckDBHistory)


def test_startup_wiring_without_db_package_leaves_seam_unset(monkeypatch):
    monkeypatch.setattr(berichte, "history_db", None)

    def kein_db():
        raise ModuleNotFoundError("No module named 'duckdb'")

    monkeypatch.setattr(db_seams, "_client", kein_db)
    assert db_seams.verbinde_history_db(erzwingen=True) is False and berichte.history_db is None


def test_analyse_route_returns_three_connected_reports(history, monkeypatch):
    monkeypatch.setattr(berichte, "history_db", history)
    response = client.post("/api/lv/analyse", json={"lv": demo_lv().model_dump(mode="json")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(b["id"], b["status"]) for b in body["berichte"]] == [
        ("regelwerk", "ok"), ("vergleich", "ok"), ("was_wenn", "ok")]
    assert body["berichte"][1]["naeherungen"] and body["was_wenn"]
