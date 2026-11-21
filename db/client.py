import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import duckdb
from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "database.duckdb"
DEFAULT_PRICE_DB_PATH = BASE_DIR / "price.duckdb"
DB_PATH = str(DEFAULT_DB_PATH)
PRICE_DB_PATH = str(DEFAULT_PRICE_DB_PATH)


def get_history_db_path() -> Path:
    env_path = os.environ.get("HISTORY_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


def get_price_db_path() -> Path:
    env_path = os.environ.get("PRICE_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_PRICE_DB_PATH


def _ensure_history_schema(conn: duckdb.DuckDBPyConnection) -> None:
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


def _ensure_price_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id UBIGINT,
            name VARCHAR,
            unit VARCHAR,
            price_per_unit DOUBLE
        )
    """)


def _connect_history(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = get_history_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and not db_path.exists():
        with duckdb.connect(str(db_path)) as init_conn:
            _ensure_history_schema(init_conn)
    conn = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        _ensure_history_schema(conn)
    return conn


def _connect_price(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = get_price_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and not db_path.exists():
        with duckdb.connect(str(db_path)) as init_conn:
            _ensure_price_schema(init_conn)
    conn = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        _ensure_price_schema(conn)
    return conn


def normalize_tag(raw: str) -> str:
    tag = raw.strip().lower()
    if not tag or any(ch.isspace() for ch in tag):
        raise ValueError("Each tag must be a single non-empty word without whitespace")
    return tag


@asynccontextmanager
async def lifespan(app: FastAPI):
    with _connect_history(read_only=False):
        pass
    with _connect_price(read_only=False):
        pass
    yield


router = APIRouter(prefix="/api/db", tags=["history-db"])
price_router = APIRouter(tags=["prices"])
app = FastAPI(title="DuckDB Test Results & Price API", lifespan=lifespan)


# --- Pydantic Models (Database 1: Records) ---

class RecordCreate(BaseModel):
    id: Optional[int] = Field(default=None, description="Auto-generated if omitted")
    date: Optional[str] = Field(default=None, description="Format: YYYY-MM-DD HH:MM:SS. Auto-generated if omitted")
    description: str
    tags: List[str] = []
    expected_json: Union[Dict[str, Any], List[Any]]
    actual_json: Union[Dict[str, Any], List[Any]]
    note: str = ""

    @field_validator("tags")
    @classmethod
    def validate_and_normalize_tags(cls, values: List[str]) -> List[str]:
        return [normalize_tag(v) for v in values]


class RecordResponse(BaseModel):
    id: int
    date: str
    description: str
    tags: List[str]
    expected_json: Optional[Union[Dict[str, Any], List[Any]]] = None
    actual_json: Optional[Union[Dict[str, Any], List[Any]]] = None
    note: str


class TagCount(BaseModel):
    tag: str
    count: int


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
                description=r[2] or "",
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


# --- Endpoints (Database 1: Records - /api/db/...) ---

@router.get("/tags", response_model=List[TagCount])
def get_all_tags():
    """Return all currently available tags with counts."""
    with _connect_history(read_only=True) as conn:
        rows = conn.execute("""
            SELECT tag, COUNT(*) AS cnt
            FROM (
                SELECT UNNEST(tags) AS tag
                FROM database
            )
            GROUP BY tag
            ORDER BY cnt DESC, tag ASC
        """).fetchall()
    return [TagCount(tag=str(r[0]), count=int(r[1])) for r in rows]


@router.post("/records", response_model=RecordResponse, status_code=201)
def insert_record(record: RecordCreate):
    """Insert a new test result record into the database."""
    record_id = record.id if record.id is not None else int(time.time() * 1000)
    record_date = record.date if record.date else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with _connect_history(read_only=False) as conn:
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


@router.get("/records/latest", response_model=List[RecordResponse])
def get_latest_records(limit: int = Query(10, ge=1, le=1000, description="Number of records to return")):
    """Get the latest records regardless of tags."""
    with _connect_history(read_only=True) as conn:
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


@router.get("/records/by-tag/{tag}", response_model=List[RecordResponse])
def get_latest_by_tag(
    tag: str,
    limit: int = Query(10, ge=1, le=1000, description="Number of records to return"),
):
    """Get the latest records filtered by a specific tag."""
    try:
        clean_tag = normalize_tag(tag)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with _connect_history(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT id, date, description, tags, expected_json, actual_json, note
            FROM database
            WHERE list_contains(tags, ?)
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            [clean_tag, limit],
        ).fetchall()
    return format_rows(rows)


# --- Endpoints (Database 2: Price) ---

@price_router.get("/prices/all", response_model=List[PriceResponse])
def get_all_prices():
    """Return all rows from the prices table."""
    with _connect_price(read_only=True) as price_conn:
        rows = price_conn.execute(
            """
            SELECT id, name, unit, price_per_unit
            FROM prices
            ORDER BY id DESC
            """
        ).fetchall()
    return format_price_rows(rows)


@price_router.post("/prices", response_model=PriceResponse, status_code=201)
def insert_price(item: PriceCreate):
    """Insert a new price item into the price database."""
    item_id = item.id if item.id is not None else int(time.time() * 1000)

    try:
        with _connect_price(read_only=False) as price_conn:
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


@price_router.get("/prices", response_model=List[PriceResponse])
def get_prices(
    name: Optional[str] = Query(default=None, description="Filter by item name (optional)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
):
    """Get a list of prices, optionally filtered by name."""
    with _connect_price(read_only=True) as price_conn:
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


app.include_router(router)
app.include_router(price_router)