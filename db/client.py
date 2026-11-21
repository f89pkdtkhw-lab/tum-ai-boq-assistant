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
PRICE_DB_PATH = str(BASE_DIR / "price.duckdb")

conn: Optional[duckdb.DuckDBPyConnection] = None
price_conn: Optional[duckdb.DuckDBPyConnection] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conn, price_conn
    # Connect to the first database (records)
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

    # Connect to the second database (price)
    price_conn = duckdb.connect(PRICE_DB_PATH)
    price_conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id UBIGINT,
            name VARCHAR,
            unit VARCHAR,
            price_per_unit DOUBLE
        )
    """)

    yield

    if conn:
        conn.close()
    if price_conn:
        price_conn.close()


app = FastAPI(title="DuckDB Test Results & Price API", lifespan=lifespan)


# --- Pydantic Models (Database 1: Records) ---

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


# --- Pydantic Models (Database 2: Price) ---

class PriceCreate(BaseModel):
    id: Optional[int] = Field(default=None, description="Auto-generated if omitted")
    name: str
    unit: str
    price_per_unit: float


class PriceResponse(BaseModel):
    id: int
    name: str
    unit: str
    price_per_unit: float


# --- Helper Functions ---

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


def format_price_rows(rows: List[tuple]) -> List[PriceResponse]:
    """Maps raw price database tuples into typed Pydantic response models."""
    return [
        PriceResponse(
            id=int(r[0]),
            name=r[1],
            unit=r[2],
            price_per_unit=float(r[3]),
        )
        for r in rows
    ]


# --- Endpoints (Database 1: Records) ---

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


# --- Endpoints (Database 2: Price) ---

@app.post("/prices", response_model=PriceResponse, status_code=201)
def insert_price(item: PriceCreate):
    """Insert a new price item into the price database."""
    item_id = item.id if item.id is not None else int(time.time() * 1000)

    try:
        price_conn.execute(
            """
            INSERT INTO prices (id, name, unit, price_per_unit)
            VALUES (?, ?, ?, ?)
            """,
            [
                item_id,
                item.name,
                item.unit,
                item.price_per_unit,
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Price database insert error: {str(e)}")

    return PriceResponse(
        id=item_id,
        name=item.name,
        unit=item.unit,
        price_per_unit=item.price_per_unit,
    )


@app.get("/prices", response_model=List[PriceResponse])
def get_prices(
    name: Optional[str] = Query(default=None, description="Filter by item name (optional)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
):
    """Get a list of prices, optionally filtered by name."""
    if name:
        rows = price_conn.execute(
            """
            SELECT id, name, unit, price_per_unit
            FROM prices
            WHERE name ILIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            [f"%{name}%", limit],
        ).fetchall()
    else:
        rows = price_conn.execute(
            """
            SELECT id, name, unit, price_per_unit
            FROM prices
            ORDER BY id DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

    return format_price_rows(rows)