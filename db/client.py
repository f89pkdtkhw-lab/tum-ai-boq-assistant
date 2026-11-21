import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import duckdb
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from api.app.lv.gaeb import importiere
from api.app.lv.pdf import import_with_blocks

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


def _extract_tags_from_filename(filename: Optional[str]) -> List[str]:
    """Extract normalized tags from a filename matching 'estimated_tag1_tag2_tag3.pdf'."""
    if not filename:
        return []

    stem = Path(filename).stem
    parts = stem.split("_")

    if parts and parts[0].lower() == "estimated":
        tags: List[str] = []
        for raw_tag in parts[1:]:
            if raw_tag.strip():
                tags.append(normalize_tag(raw_tag))
        return tags

    return []


def _parse_pdf_to_dict(filename: str, content: bytes) -> Dict[str, Any]:
    """Parse PDF content and return the output structure up to the warnings key."""
    result = import_with_blocks(filename, content)
    total_gp = round(sum(p.gp or 0.0 for p in result.lv.positionen), 2)
    lv_dict = result.lv.model_dump() if hasattr(result.lv, "model_dump") else result.lv.dict()

    return {
        "total_gp_calculated": total_gp,
        "lv": lv_dict,
    }


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
async def insert_record(
    estimated_file: UploadFile = File(..., description="Estimated PDF file (e.g., estimated_tag1_tag2.pdf)"),
    real_file: UploadFile = File(..., description="Ground-truth / real PDF file"),
    description: str = Form(default=""),
    note: str = Form(default=""),
):
    """Parse two PDF files, extract tags from the estimated filename, and insert a record."""
    record_id = int(time.time() * 1000)
    record_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        tags = _extract_tags_from_filename(estimated_file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        estimated_bytes = await estimated_file.read()
        real_bytes = await real_file.read()

        actual_data = _parse_pdf_to_dict(estimated_file.filename or "estimated.pdf", estimated_bytes)
        expected_data = _parse_pdf_to_dict(real_file.filename or "real.pdf", real_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF parsing error: {str(e)}")

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
                    description,
                    tags,
                    json.dumps(expected_data, ensure_ascii=False),
                    json.dumps(actual_data, ensure_ascii=False),
                    note,
                ],
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert error: {str(e)}")

    return RecordResponse(
        id=record_id,
        date=record_date,
        description=description,
        tags=tags,
        expected_json=expected_data,
        actual_json=actual_data,
        note=note,
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


@price_router.post("/prices/import-gaeb", response_model=List[PriceResponse], status_code=201)
async def import_prices_from_gaeb(
    file: UploadFile = File(..., description="GAEB file (e.g., .d86)"),
):
    """Parse a GAEB file (.d86) and insert priced items into the price database."""
    filename = file.filename or "upload.d86"
    try:
        content = await file.read()
        lv = importiere(filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"GAEB parsing error: {str(e)}")

    base_id = int(time.time() * 1000) * 10000
    created_items: List[PriceResponse] = []
    rows_to_insert: List[tuple] = []

    for idx, pos in enumerate(lv.positionen):
        if pos.ep is None or not pos.kurztext or not pos.einheit:
            continue

        item_id = base_id + idx
        name = pos.kurztext.strip()
        unit = pos.einheit.strip()
        price_per_unit = float(pos.ep)

        rows_to_insert.append((item_id, name, unit, price_per_unit))
        created_items.append(
            PriceResponse(
                id=item_id,
                name=name,
                unit=unit,
                price_per_unit=price_per_unit,
            )
        )

    if not rows_to_insert:
        raise HTTPException(
            status_code=422,
            detail="No valid positions with kurztext, einheit, and ep found in GAEB file.",
        )

    try:
        with _connect_price(read_only=False) as price_conn:
            price_conn.executemany(
                """
                INSERT INTO prices (id, name, unit, price_per_unit)
                VALUES (?, ?, ?, ?)
                """,
                rows_to_insert,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Price database insert error: {str(e)}")

    return created_items


app.include_router(router)
app.include_router(price_router)