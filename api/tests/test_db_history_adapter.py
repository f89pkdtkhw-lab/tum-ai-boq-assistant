import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
API_DIR = ROOT_DIR / "api"
for p in (str(ROOT_DIR), str(API_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import duckdb
import pytest
from fastapi.testclient import TestClient

from app.ai import step_api
from app.ai.step_api import (
    Assumptions,
    Baseline,
    EstimatePosition,
    EstimateTarget,
    StepRequest,
)
from app.main import app
from db.history_adapter import get_history_records, row_to_history_record


@pytest.fixture()
def temp_duckdb(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_history.duckdb"
    with duckdb.connect(str(db_file)) as conn:
        conn.execute("""
            CREATE TABLE database (
                id UBIGINT,
                date TIMESTAMP,
                description VARCHAR,
                tags VARCHAR[],
                expected_json JSON,
                actual_json JSON,
                note VARCHAR
            )
        """)
        records = [
            (
                101,
                "2026-05-01 10:00:00",
                "Synthetic bridge pier A",
                ["bridge", "concrete"],
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 100.0, "unit": "h"}]),
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 120.0, "unit": "h"}]),
                "pumping delay",
            ),
            (
                102,
                "2026-05-02 10:00:00",
                "Synthetic bridge pier B",
                ["bridge"],
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 50.0, "unit": "h"}]),
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 60.0, "unit": "h"}]),
                "formwork adjustment",
            ),
            (
                103,
                "2026-05-03 10:00:00",
                "Synthetic bridge pier C",
                ["bridge", "repair"],
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 200.0, "unit": "h"}]),
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 240.0, "unit": "h"}]),
                "weather delay",
            ),
            (
                201,
                "2026-05-04 10:00:00",
                "Synthetic road asphalt D",
                ["road", "asphalt"],
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 100.0, "unit": "h"}]),
                json.dumps([{"oz": "01.001", "metric": "hours", "value": 140.0, "unit": "h"}]),
                "traffic detour",
            ),
        ]
        conn.executemany("INSERT INTO database VALUES (?, ?, ?, ?, ?, ?, ?)", records)
    return db_file


def test_mapping_round_trip():
    raw_row = (
        42,
        "2026-06-15 12:30:00",
        "Synthetic culvert repair",
        ["bridge", "drainage"],
        json.dumps([{"oz": "01.001", "metric": "hours", "value": 10.0, "unit": "h"}]),
        json.dumps([{"oz": "01.001", "metric": "hours", "value": 12.5, "unit": "h"}]),
        "synthetic note",
    )
    record = row_to_history_record(raw_row)
    assert record.case_id == "42"
    assert record.date == date(2026, 6, 15)
    assert record.tags == ["bridge", "drainage"]
    assert record.estimated_values[0].value == 10.0
    assert record.real_values[0].value == 12.5


def test_adapter_comparable_vs_what_if(temp_duckdb: Path):
    pos = EstimatePosition(oz="01.001", work_tags=["bridge"], metric="hours", unit="h")

    comparable = get_history_records(pos, "comparable", db_path=temp_duckdb)
    assert [r.case_id for r in comparable] == ["103", "102", "101"]

    what_if = get_history_records(pos, "what_if", db_path=temp_duckdb)
    assert [r.case_id for r in what_if] == ["201", "103", "102", "101"]


def test_missing_db_keeps_seam_none_and_returns_history_unavailable(monkeypatch, tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.duckdb"
    monkeypatch.setattr(step_api, "history_service", None if not missing_path.exists() else get_history_records)
    assert step_api.history_service is None

    client = TestClient(app)
    payload = {
        "step": "historical_adjustment",
        "lv": {"name": "Synthetic bridge repair", "quelle": "synthetic:test", "positionen": [{"oz": "01.001"}]},
        "estimates": [
            {
                "position": {"oz": "01.001", "work_tags": ["bridge"], "metric": "hours", "unit": "h"},
                "assumptions": {
                    "ratio_method": "median",
                    "selected_by": "estimator",
                    "baseline": {"value": 50, "unit": "h", "source": "synthetic"},
                },
            }
        ],
    }
    response = client.post("/api/comparison/steps", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["errors"][0]["code"] == "history_unavailable"


def test_estimate_step_returns_case_ids_when_seeded(monkeypatch, temp_duckdb: Path):
    monkeypatch.setattr(step_api, "history_service", lambda pos, mode: get_history_records(pos, mode, db_path=temp_duckdb))

    req = StepRequest(
        step="historical_adjustment",
        lv={"name": "Synthetic bridge repair", "quelle": "synthetic:test", "positionen": [{"oz": "01.001"}]},
        estimates=[
            EstimateTarget(
                position=EstimatePosition(oz="01.001", work_tags=["bridge"], metric="hours", unit="h"),
                assumptions=Assumptions(
                    ratio_method="median",
                    selected_by="estimator",
                    baseline=Baseline(value=50, unit="h", source="synthetic"),
                ),
            )
        ],
    )
    res = step_api.comparison_step(req)
    assert res.status == "complete"
    assert len(res.notes) == 1
    assert set(res.notes[0].case_ids) == {"101", "102", "103"}