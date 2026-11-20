import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path
import duckdb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "database.duckdb")
conn: Optional[duckdb.DuckDBPyConnection] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conn
    # Connect to a persistent local DuckDB file
    conn = duckdb.connect(DB_PATH)
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
    yield
    if conn:
        conn.close()


app = FastAPI(title="DuckDB Test Results API", lifespan=lifespan)


# --- Pydantic Models ---

class RecordCreate(BaseModel):
    id: Optional[int] = Field(default=None, description="Auto-generated if omitted")
    date: Optional[str] = Field(default=None, description="Format: YYYY-MM-DD HH:MM:SS. Auto-generated if omitted")
    description: str
    tags: List[str] = []
    expected_json: Dict[str, Any]
    actual_json: Dict[str, Any]
    note: str = ""


class RecordResponse(BaseModel):
    id: int
    date: str
    description: str
    tags: List[str]
    expected_json: Dict[str, Any]
    actual_json: Dict[str, Any]
    note: str


# --- Helper Function ---

def format_rows(rows: List[tuple]) -> List[RecordResponse]:
    """Maps raw database tuples into typed Pydantic response models."""
    results = []
    for r in rows:
        results.append(
            RecordResponse(
                id=int(r[0]),
                date=r[1].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[1], datetime) else str(r[1]),
                description=r[2],
                tags=r[3] if r[3] is not None else [],
                expected_json=json.loads(r[4]) if isinstance(r[4], str) else r[4],
                actual_json=json.loads(r[5]) if isinstance(r[5], str) else r[5],
                note=r[6] or "",
            )
        )
    return results


# --- Endpoints ---

@app.post("/records", response_model=RecordResponse, status_code=201)
def insert_record(record: RecordCreate):
    """Insert a new test result record into the database."""
    record_id = record.id if record.id is not None else int(time.time() * 1000)
    record_date = record.date if record.date else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.execute(
            """
            INSERT INTO database (id, date, description, tags, expected_json, actual_json, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record_id,
                record_date,
                record.description,
                record.tags,
                json.dumps(record.expected_json),
                json.dumps(record.actual_json),
                record.note,
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert error: {str(e)}")

    return RecordResponse(
        id=record_id,
        date=record_date,
        description=record.description,
        tags=record.tags,
        expected_json=record.expected_json,
        actual_json=record.actual_json,
        note=record.note,
    )


@app.get("/records/latest", response_model=List[RecordResponse])
def get_latest_records(limit: int = Query(10, ge=1, le=1000, description="Number of records to return")):
    """Get the latest records regardless of tags."""
    rows = conn.execute(
        """
        SELECT id, date, description, tags, expected_json, actual_json, note
        FROM database
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return format_rows(rows)


@app.get("/records/by-tag/{tag}", response_model=List[RecordResponse])
def get_latest_by_tag(
    tag: str,
    limit: int = Query(10, ge=1, le=1000, description="Number of records to return"),
):
    """Get the latest records filtered by a specific tag."""
    rows = conn.execute(
        """
        SELECT id, date, description, tags, expected_json, actual_json, note
        FROM database
        WHERE list_contains(tags, ?)
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        [tag, limit],
    ).fetchall()
    return format_rows(rows)