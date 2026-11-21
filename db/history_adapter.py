import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Sequence

import duckdb

from db.client import DB_PATH

try:
    from app.ai.step_api import (
        EstimatePosition,
        HistoryRecord,
        HistoryUnavailable,
        Measurement,
        Mode,
    )
except ModuleNotFoundError:
    from api.app.ai.step_api import (
        EstimatePosition,
        HistoryRecord,
        HistoryUnavailable,
        Measurement,
        Mode,
    )


def _parse_measurements(raw_json: Any, fallback_oz: str = "01.001") -> List[Measurement]:
    """Converts expected_json / actual_json from DuckDB into a list of Measurement objects."""
    if raw_json is None:
        return []
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json

    # Support either a list of measurement dicts or a single dict / {"measurements": [...]}
    if isinstance(data, dict):
        items = data.get("measurements") if "measurements" in data else [data]
    elif isinstance(data, list):
        items = data
    else:
        return []

    measurements: List[Measurement] = []
    for item in items:
        if not isinstance(item, dict) or "metric" not in item or "unit" not in item:
            continue
        measurements.append(
            Measurement(
                oz=str(item.get("oz") or fallback_oz),
                title_path=list(item.get("title_path") or []),
                metric=str(item["metric"]),
                value=float(item["value"]) if item.get("value") is not None else None,
                unit=str(item["unit"]),
            )
        )
    return measurements


def row_to_history_record(row: tuple) -> HistoryRecord:
    """Maps a DuckDB row (id, date, description, tags, expected_json, actual_json, note) to HistoryRecord."""
    raw_id, raw_date, description, tags, expected_json, actual_json, _note = row

    if isinstance(raw_date, datetime):
        parsed_date = raw_date.date()
    elif isinstance(raw_date, date):
        parsed_date = raw_date
    else:
        parsed_date = date.fromisoformat(str(raw_date)[:10])

    return HistoryRecord(
        case_id=str(raw_id),
        date=parsed_date,
        description=description or "",
        tags=list(tags) if tags is not None else [],
        estimated_values=_parse_measurements(expected_json),
        real_values=_parse_measurements(actual_json),
    )


def get_history_records(
    position: EstimatePosition,
    mode: Mode,
    db_path: str | Path = DB_PATH,
) -> Sequence[HistoryRecord]:
    """Adapter for step_api.history_service: fetches comparable (by tags) or what_if (all recent) cases."""
    path = Path(db_path)
    if not path.exists():
        raise HistoryUnavailable(f"History database not found at {path}")

    try:
        with duckdb.connect(str(path), read_only=True) as local_conn:
            work_tags = [t.strip() for t in position.work_tags if t.strip()]

            if mode == "comparable" and work_tags:
                rows = local_conn.execute(
                    """
                    SELECT id, date, description, tags, expected_json, actual_json, note
                    FROM database
                    WHERE list_has_any(tags, ?)
                    ORDER BY date DESC, id DESC
                    LIMIT 50
                    """,
                    [work_tags],
                ).fetchall()
            else:
                rows = local_conn.execute(
                    """
                    SELECT id, date, description, tags, expected_json, actual_json, note
                    FROM database
                    ORDER BY date DESC, id DESC
                    LIMIT 50
                    """
                ).fetchall()
    except Exception as exc:
        raise HistoryUnavailable(f"Failed to query history database: {exc}") from exc

    return [row_to_history_record(r) for r in rows]