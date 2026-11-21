import json
from pathlib import Path
import sys

# Ensure project root is on sys.path when running `python tools/seed_history.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb
from db.client import DB_PATH

SYNTHETIC_CASES = [
    {
        "id": 900001,
        "date": "2026-03-14 10:00:00",
        "description": "Synthetic bridge abutment concrete repair",
        "tags": ["bridge", "concrete", "repair"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 100.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 122.0, "unit": "h"}],
        "note": "groundwater pumping underestimated",
    },
    {
        "id": 900002,
        "date": "2026-04-02 14:30:00",
        "description": "Synthetic highway overpass joint sealing",
        "tags": ["bridge", "repair", "sealing"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 80.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 96.0, "unit": "h"}],
        "note": "night traffic diversion extended setup time",
    },
    {
        "id": 900003,
        "date": "2026-05-19 09:15:00",
        "description": "Synthetic river bridge pier formwork",
        "tags": ["bridge", "concrete", "formwork"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 150.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 172.5, "unit": "h"}],
        "note": "river level surge delayed cofferdam inspection",
    },
    {
        "id": 900004,
        "date": "2026-06-11 11:00:00",
        "description": "Synthetic pedestrian bridge deck resurfacing",
        "tags": ["bridge", "asphalt", "repair"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 60.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 69.0, "unit": "h"}],
        "note": "substrate moisture required extra drying cycle",
    },
    {
        "id": 900005,
        "date": "2026-07-08 08:45:00",
        "description": "Synthetic municipal road base compaction",
        "tags": ["road", "earthworks", "asphalt"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 120.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 156.0, "unit": "h"}],
        "note": "unmapped utility trench discovered during grading",
    },
    {
        "id": 900006,
        "date": "2026-08-21 16:00:00",
        "description": "Synthetic rural road drainage culvert installation",
        "tags": ["road", "drainage", "earthworks"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 90.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 117.0, "unit": "h"}],
        "note": "groundwater pumping underestimated in clay layer",
    },
    {
        "id": 900007,
        "date": "2026-09-12 13:20:00",
        "description": "Synthetic retaining wall reinforcement steel",
        "tags": ["structural", "concrete", "rebar"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 200.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 250.0, "unit": "h"}],
        "note": "crane access restricted by adjacent slope",
    },
    {
        "id": 900008,
        "date": "2026-10-05 15:10:00",
        "description": "Synthetic industrial foundation slab pouring",
        "tags": ["structural", "concrete"],
        "expected_json": [{"oz": "01.001", "metric": "hours", "value": 110.0, "unit": "h"}],
        "actual_json": [{"oz": "01.001", "metric": "hours", "value": 137.5, "unit": "h"}],
        "note": "cold weather curing blankets added labor hours",
    },
]


def seed(db_path: str | Path = DB_PATH) -> int:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS database (
                id UBIGINT,
                date TIMESTAMP,
                description VARCHAR,
                tags VARCHAR[],
                expected_json JSON,
                actual_json JSON,
                note VARCHAR
            )
        """)
        seed_ids = [c["id"] for c in SYNTHETIC_CASES]
        placeholders = ", ".join(["?"] * len(seed_ids))
        conn.execute(f"DELETE FROM database WHERE id IN ({placeholders})", seed_ids)

        for case in SYNTHETIC_CASES:
            conn.execute(
                """
                INSERT INTO database (id, date, description, tags, expected_json, actual_json, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    case["id"],
                    case["date"],
                    case["description"],
                    case["tags"],
                    json.dumps(case["expected_json"]),
                    json.dumps(case["actual_json"]),
                    case["note"],
                ],
            )
    return len(SYNTHETIC_CASES)


if __name__ == "__main__":
    count = seed()
    print(f"Seeded {count} synthetic history cases into {DB_PATH}")