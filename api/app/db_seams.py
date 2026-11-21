"""DB seams (#155): connect Reports 2 (`vergleich`) and 3 (`was_wenn`) to the history database.

`pruefung/berichte.py` reads history only through its seam `history_db` (protocol `HistoryDB`:
`tags()`, `records_by_tag(tag, limit)`, `records_latest(limit)`). This module provides an adapter
over the read actions of @Anatomik5's `db/client.py` (the same functions that serve
`GET /api/db/tags`, `/api/db/records/by-tag/{tag}` and `/api/db/records/latest`) and wires it at
start-up with `verbinde_history_db()`.

Nothing here writes to the database and nothing in `db/` is changed. If the database is missing
or cannot be read (e.g. a file written by a newer DuckDB), the adapter raises; `berichte` turns
that into `status="nicht_verbunden"` with a readable message and the rest of the review stays
complete. If `db/` cannot be imported at all, the seam stays None ("not connected").
"""
import logging
import sys
from pathlib import Path
from typing import Any

from .pruefung import berichte

log = logging.getLogger(__name__)


class HistoryDatabaseMissing(Exception):
    """The configured history database file does not exist."""


class HistoryDatabaseUnreadable(Exception):
    """The history database exists but a read action failed (version, lock, schema …)."""


def _client():
    # Imported lazily: db/ lives in the repository root (main.py puts it on sys.path) and needs duckdb.
    from db import client
    return client


def _als_dict(eintrag: Any) -> dict[str, Any]:
    return eintrag.model_dump(mode="json") if hasattr(eintrag, "model_dump") else dict(eintrag)


def _positionen(wert: Any) -> Any:
    """`POST /api/db/records` stores parsed bills as {"total_gp_calculated", "lv": {"positionen": […]}}.

    Reports 2/3 read objects from a top-level list or `positionen`; unwrap the `lv` level so records
    ingested by the DB service are comparable. Other shapes pass through unchanged."""
    if isinstance(wert, dict) and isinstance(wert.get("lv"), dict) and isinstance(wert["lv"].get("positionen"), list):
        return {"positionen": wert["lv"]["positionen"]}
    return wert


def _fall(eintrag: Any) -> dict[str, Any]:
    fall = _als_dict(eintrag)
    for spalte in ("expected_json", "actual_json"):
        fall[spalte] = _positionen(fall.get(spalte))
    return fall


class DuckDBHistory:
    """`berichte.HistoryDB` over `db/client.py` (read-only; path from `HISTORY_DB_PATH` or db/'s default)."""

    def _aktion(self, name: str, *args, **kwargs) -> list[Any]:
        client = _client()
        pfad = Path(client.get_history_db_path())
        if not pfad.exists():  # db/'s read path would create an empty file; a missing DB is "not connected"
            raise HistoryDatabaseMissing(str(pfad))
        try:
            return list(getattr(client, name)(*args, **kwargs))
        except Exception as exc:
            log.warning("History DB action %s failed: %s", name, exc)
            raise HistoryDatabaseUnreadable(type(exc).__name__) from exc

    def tags(self) -> list[dict[str, Any]]:
        return [_als_dict(t) for t in self._aktion("get_all_tags")]

    def records_by_tag(self, tag: str, limit: int) -> list[dict[str, Any]]:
        return [_fall(r) for r in self._aktion("get_latest_by_tag", tag, limit=limit)]

    def records_latest(self, limit: int) -> list[dict[str, Any]]:
        return [_fall(r) for r in self._aktion("get_latest_records", limit=limit)]


def verbinde_history_db(erzwingen: bool = False) -> bool:
    """Start-up wiring: set `berichte.history_db` to the DB adapter. True when connected.

    Under pytest the seam stays None unless `erzwingen` (offline tests use fakes or temporary DBs),
    matching the existing `step_api.history_service` wiring in main.py."""
    if "pytest" in sys.modules and not erzwingen:
        return False
    try:
        _client()
    except Exception as exc:  # no duckdb, no db/ package: the reports say "not connected"
        log.warning("History DB not connected for Reports 2/3: %s", exc)
        return False
    berichte.history_db = DuckDBHistory()
    return True
