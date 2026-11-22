"""Price list upload, price DB adapter and the B9 price seam (#153). Offline; every test uses a temporary
price database (PRICE_DB_PATH), never the committed db/*.duckdb files."""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
pytest.importorskip("duckdb")

from fastapi.testclient import TestClient  # noqa: E402

from app import main, preis_api  # noqa: E402
from app.pruefung import preise  # noqa: E402

client = TestClient(main.app)
FIXTURES = Path(__file__).parent / "fixtures"
DEMO_LV = json.loads((ROOT / "data" / "beispiel_lv.json").read_text(encoding="utf-8"))

# Synthetic price list: semicolon separated, German decimal comma, mixed unit spellings.
CSV = ("kurztext;einheit;ep;waehrung\n"
       "Erdarbeiten Teilfläche 1;m3;21,50;EUR\n"
       "Betonarbeiten Teilfläche 2;m³;1.040,00;EUR\n"
       "Mauerarbeiten Teilfläche 3;qm;61,25;EUR\n"
       "Ohne Preis;m2;;EUR\n").encode("utf-8")


@pytest.fixture(autouse=True)
def temp_price_db(tmp_path, monkeypatch):
    db_file = tmp_path / "price.duckdb"
    monkeypatch.setenv("PRICE_DB_PATH", str(db_file))
    monkeypatch.setattr(preise, "preis_service", None)
    from db import client as db_client
    assert db_client.get_price_db_path() == db_file
    return db_file


def upload(name, inhalt):
    return client.post("/api/preisliste/import", files={"datei": (name, inhalt)})


def test_csv_import_returns_price_list_and_stores_it_in_the_price_db():
    r = upload("preise.csv", CSV)
    assert r.status_code == 200, r.text
    liste = r.json()
    assert liste["dateiname"] == "preise.csv" and liste["waehrung"] == "EUR"
    assert [(e["kurztext"], e["einheit"], e["ep"]) for e in liste["eintraege"]] == [
        ("Erdarbeiten Teilfläche 1", "m³", 21.5), ("Betonarbeiten Teilfläche 2", "m³", 1040.0),
        ("Mauerarbeiten Teilfläche 3", "m²", 61.25)]
    assert liste["eintraege"][0]["quelle"] == "preise.csv:2"
    assert liste["warnungen"] == ["Row 5: no valid unit price (empty), skipped."]

    db = client.get("/api/db/preise").json()
    assert sorted((e["item"], e["unit"], e["price_per_unit"]) for e in db) == sorted(
        (e["kurztext"], e["einheit"], e["ep"]) for e in liste["eintraege"])
    assert all(isinstance(e["id"], int) for e in db)


def test_reimport_updates_instead_of_duplicating():
    upload("preise.csv", CSV)
    upload("preise.csv", CSV.replace(b"21,50", b"22,00"))
    db = client.get("/api/db/preise", params={"item": "erdarbeiten"}).json()
    assert [(e["item"], e["price_per_unit"]) for e in db] == [("Erdarbeiten Teilfläche 1", 22.0)]


def test_post_preise_adds_and_same_item_and_unit_updates():
    r = client.post("/api/db/preise", json=[{"item": "Schalung Wand", "unit": "m2", "price_per_unit": 30.5}])
    assert r.status_code == 200, r.text
    erste = r.json()
    assert [(e["item"], e["unit"], e["price_per_unit"]) for e in erste] == [("Schalung Wand", "m²", 30.5)]
    zweite = client.post("/api/db/preise", json=[{"item": "schalung wand", "unit": "m²", "price_per_unit": 31}]).json()
    assert zweite[0]["id"] == erste[0]["id"]
    db = client.get("/api/db/preise").json()
    assert [(e["item"], e["price_per_unit"]) for e in db] == [("schalung wand", 31.0)]


def test_get_preise_filters_by_item_unit_and_limit():
    client.post("/api/db/preise", json=[{"item": "Beton C25", "unit": "m³", "price_per_unit": 100},
                                        {"item": "Beton C30", "unit": "m3", "price_per_unit": 110},
                                        {"item": "Betonstahl", "unit": "t", "price_per_unit": 900}])
    assert {e["item"] for e in client.get("/api/db/preise?item=beton&unit=m3").json()} == {"Beton C25", "Beton C30"}
    assert [e["item"] for e in client.get("/api/db/preise?unit=t").json()] == ["Betonstahl"]
    assert len(client.get("/api/db/preise?limit=1").json()) == 1


@pytest.mark.parametrize("field, value, message", [
    ("item", "string", "placeholder"),
    ("unit", " STRING ", "placeholder"),
    ("item", "", "must not be blank"),
    ("item", "  ", "must not be blank"),
    ("unit", "  ", "must not be blank"),
    ("price_per_unit", 0, "greater than 0"),
    ("price_per_unit", -1, "greater than 0"),
])
def test_post_preise_rejects_invalid_rows(field, value, message):
    valid = {"item": "Kies", "unit": "t", "price_per_unit": 25}
    r = client.post("/api/db/preise", json=[valid, {**valid, field: value}])
    assert r.status_code == 422, r.text
    error = r.json()["detail"][0]
    assert error["loc"] == ["body", 1, field] and message in error["msg"]
    assert client.get("/api/db/preise").json() == []


@pytest.mark.parametrize("row, warning", [
    ("string;t;25", "placeholder"),
    ("Kies; STRING ;25", "placeholder"),
    (" ;t;25", "no short text or OZ"),
    ("Kies; ;25", "no unit"),
    ("Kies;t;0", "greater than 0"),
    ("Kies;t;-1", "no valid unit price"),
])
def test_csv_import_warns_and_stores_only_valid_rows(row, warning):
    r = upload("preise.csv", f"item;unit;ep\nSand;t;12\n{row}\n".encode())
    assert r.status_code == 200, r.text
    warnings = r.json()["warnungen"]
    assert len(warnings) == 1 and warning in warnings[0] and "skipped" in warnings[0]
    assert [(e["item"], e["price_per_unit"]) for e in client.get("/api/db/preise").json()] == [("Sand", 12)]


def test_json_import_skips_placeholder_unit_when_storing_prices():
    entries = [
        {"id": "1", "kurztext": "Kies", "einheit": "string", "ep": 25},
        {"id": "2", "kurztext": "Sand", "einheit": "t", "ep": 12},
    ]
    r = upload("preise.json", json.dumps({"id": "prices", "eintraege": entries}).encode())
    assert r.status_code == 200, r.text
    warnings = r.json()["warnungen"]
    assert len(warnings) == 1 and "preise.json entry 1: unit" in warnings[0] and "placeholder" in warnings[0]
    assert [(e["item"], e["price_per_unit"]) for e in client.get("/api/db/preise").json()] == [("Sand", 12)]


@pytest.mark.parametrize("name, inhalt, status, text", [
    ("preise.csv", b"kurztext;ep\nA;1\n", 422, "einheit"),
    ("preise.csv", b"", 422, "empty"),
    ("preise.pdf", b"%PDF-1.4", 422, "PDF"),
    ("preise.docx", b"x", 422, "Unsupported"),
    ("preise.csv", b"x" * (preis_api.MAX_UPLOAD_BYTES + 1), 413, "too large"),
])
def test_import_errors_are_clear(name, inhalt, status, text):
    r = upload(name, inhalt)
    assert r.status_code == status and text in r.json()["detail"]
    assert client.get("/api/db/preise").json() == []


def test_json_round_trip():
    liste = upload("preise.csv", CSV).json()
    zurueck = upload("preise.json", json.dumps(liste).encode()).json()
    assert zurueck["eintraege"] == liste["eintraege"]


def _xlsx(zeilen):
    def zelle(ref, wert):
        if isinstance(wert, (int, float)):
            return f'<c r="{ref}"><v>{wert}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{wert}</t></is></c>'
    rows = "".join(f'<row r="{i}">' + "".join(zelle(f"{chr(65 + s)}{i}", w) for s, w in enumerate(z)) + "</row>"
                   for i, z in enumerate(zeilen, start=1))
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as mappe:
        mappe.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>{rows}</sheetData></worksheet>')
    return puffer.getvalue()


def test_xlsx_import():
    inhalt = _xlsx([
        ["OZ", "Kurztext", "Einheit", "EP"],
        ["01.0010", "Aushub", "m3", 18.5],
        ["", "Verfüllen", "m³", "7,25"],
        ["", "Ohne Einheit", "", 3],
        ["", "", "t", 4],
        ["01.0020", "", "t", 5],
    ])
    liste = upload("preise.xlsx", inhalt).json()
    assert [(e["oz"], e["kurztext"], e["einheit"], e["ep"]) for e in liste["eintraege"]] == [
        ("01.0010", "Aushub", "m³", 18.5), (None, "Verfüllen", "m³", 7.25), ("01.0020", "", "t", 5)]
    assert liste["warnungen"] == ["Row 4: no unit, skipped.", "Row 5: no short text or OZ, skipped."]
    assert {e["item"] for e in client.get("/api/db/preise").json()} == {"Aushub", "Verfüllen", "01.0020"}


def test_gaeb_x84_import_uses_priced_items():
    liste = upload("offer.x84", (FIXTURES / "gaeb" / "offer.x84").read_bytes()).json()
    assert liste["eintraege"] and all(e["ep"] >= 0 and e["einheit"] for e in liste["eintraege"])
    assert len(client.get("/api/db/preise").json()) == len({(e["kurztext"].casefold(), e["einheit"])
                                                            for e in liste["eintraege"]})


def test_import_still_returns_the_list_when_the_db_is_down(monkeypatch):
    def kaputt(read_only=False):
        raise preis_api.HTTPException(503, "Price database is not available: test")
    monkeypatch.setattr(preis_api, "_verbinde", kaputt)
    r = upload("preise.csv", CSV)
    assert r.status_code == 200 and len(r.json()["eintraege"]) == 3
    assert "not stored in the price database" in r.json()["warnungen"][-1]
    assert client.get("/api/db/preise").status_code == 503


def test_analyse_prices_from_the_db_when_no_list_is_uploaded(monkeypatch):
    upload("preise.csv", CSV)
    monkeypatch.setattr(preise, "preis_service", preis_api.als_preisliste)
    bericht = client.post("/api/lv/analyse", json={"lv": DEMO_LV, "regelwerk": None, "preisliste": None}).json()
    kalkulation = bericht["kalkulation"]
    assert kalkulation["preisliste_id"] == "preis-db"
    getroffen = {p["oz"]: p for p in kalkulation["positionen"] if p["treffer"] != "kein_treffer"}
    assert getroffen["01.00.0001"]["ep"] == 21.5 and getroffen["01.00.0001"]["gp"] == 236.5
    assert getroffen["01.00.0001"]["preisliste_id"] == "preis-db"
    assert bericht["geschaetztes_lv"]["positionen"]


def test_empty_db_keeps_the_analysis_without_pricing(monkeypatch):
    monkeypatch.setattr(preise, "preis_service", preis_api.als_preisliste)
    assert preis_api.als_preisliste() is None
    bericht = client.post("/api/lv/analyse", json={"lv": DEMO_LV, "regelwerk": None, "preisliste": None}).json()
    assert bericht.get("kalkulation") is None


def test_anatomik5_price_routes_are_mounted_under_api_db():
    assert client.get("/api/db/prices/all").json() == []
    r = client.post("/api/db/prices", json={"name": "Kies", "unit": "t", "price_per_unit": 25})
    assert r.status_code == 201
    assert [(e["item"], e["unit"]) for e in client.get("/api/db/preise").json()] == [("Kies", "t")]


def test_unreadable_db_gives_503_on_get(temp_price_db):
    temp_price_db.write_bytes(b"not a duckdb file")
    r = client.get("/api/db/preise")
    assert r.status_code == 503 and "cannot be read" in r.json()["detail"]


def _d86_bytes():
    def record(kind, fields):
        line = list(" " * 80)
        line[:2] = kind
        for start, text in fields:
            line[start:start + len(text)] = text
        return "".join(line)
    return "\r\n".join([
        record("00", [(10, "86"), (62, "1122PPPPI"), (72, "90")]),
        record("21", [(2, "01010001 "), (11, "NN"), (23, "00000002000"), (34, "m2")]),
        record("23", [(2, "01010001 "), (12, "00000012500"), (24, "000000002500")]),
        record("25", [(2, "Synthetic wall")]),
        record("99", []),
    ]).encode("cp850")


@pytest.mark.parametrize("name", ["preise.d86", "PREISE.D86"])
def test_priced_d86_import_returns_price_list(name):
    r = upload(name, _d86_bytes())
    assert r.status_code == 200, r.text
    liste = r.json()
    assert [(e["oz"], e["einheit"], e["ep"]) for e in liste["eintraege"]] == [("01.01.0001", "m²", 12.5)]


# Synthetic GAEB 90 tender (D83) and offer (D84): a DA84 offer carries OZ, unit and unit price, the texts are in the D83.
def _gaeb90(phase, records):
    def record(kind, fields):
        line = list(" " * 80)
        line[:2] = kind
        for start, text in fields:
            line[start:start + len(text)] = text
        return "".join(line)
    kopf = record("00", [(10, phase), (62, "1122PPPPI"), (72, "90")])
    return "\r\n".join([kopf, *(record(k, f) for k, f in records), record("99", [])]).encode("cp850")


def _d83():
    return _gaeb90("83", [
        ("21", [(2, "01010001 "), (11, "NN"), (23, "00000002000"), (34, "m2")]),
        ("25", [(2, "Synthetischer Schutzanstrich")]),
        ("21", [(2, "01010002 "), (11, "NN"), (23, "00000001000"), (34, "St")]),
        ("25", [(2, "Synthetische Tür")]),
    ])


def _d84_angebot():
    return _gaeb90("84", [
        ("21", [(2, "01010001 "), (11, "NN"), (23, "00000002000"), (34, "m2")]),
        ("23", [(2, "01010001 "), (12, "00000012500"), (24, "000000002500")]),
        ("21", [(2, "01010002 "), (11, "NN"), (23, "00000001000"), (34, "St")]),
        ("23", [(2, "01010002 "), (12, "00000300000"), (24, "000000030000")]),
    ])


def _d84_nur_preise():
    return _gaeb90("84", [
        ("23", [(2, "01010001 "), (12, "00000012500"), (24, "000000002500")]),
        ("23", [(2, "01010002 "), (12, "00000300000"), (24, "000000030000")]),
    ])


def upload_mit_lv(name, inhalt, lv_name, lv_inhalt):
    return client.post("/api/preisliste/import", files={"datei": (name, inhalt), "lv": (lv_name, lv_inhalt)})


@pytest.mark.parametrize("name", ["angebot.d84", "ANGEBOT.D84"])
def test_d84_offer_without_texts_is_read_but_not_stored_by_oz(name):
    r = upload(name, _d84_angebot())
    assert r.status_code == 200, r.text
    liste = r.json()
    assert [(e["oz"], e["kurztext"], e["einheit"], e["ep"]) for e in liste["eintraege"]] == [
        ("01.01.0001", "", "m²", 12.5), ("01.01.0002", "", "St", 300.0)]
    assert any("no item text" in w for w in liste["warnungen"])
    assert client.get("/api/db/preise").json() == []


def test_d84_offer_with_matching_d83_gets_texts_and_is_stored():
    r = upload_mit_lv("angebot.D84", _d84_angebot(), "ausschreibung.D83", _d83())
    assert r.status_code == 200, r.text
    liste = r.json()
    assert [(e["kurztext"], e["einheit"], e["ep"]) for e in liste["eintraege"]] == [
        ("Synthetischer Schutzanstrich", "m²", 12.5), ("Synthetische Tür", "St", 300.0)]
    assert liste["warnungen"] == []
    gespeichert = {(e["item"], e["unit"], e["price_per_unit"]) for e in client.get("/api/db/preise").json()}
    assert gespeichert == {("Synthetischer Schutzanstrich", "m²", 12.5), ("Synthetische Tür", "St", 300.0)}


def test_price_only_d84_needs_the_matching_bill():
    r = upload("preise.d84", _d84_nur_preise())
    assert r.status_code == 422 and "matching bill" in r.json()["detail"]
    r = upload_mit_lv("preise.d84", _d84_nur_preise(), "lv.d83", _d83())
    assert r.status_code == 200, r.text
    assert [(e["kurztext"], e["einheit"]) for e in r.json()["eintraege"]] == [
        ("Synthetischer Schutzanstrich", "m²"), ("Synthetische Tür", "St")]


def test_matching_bill_errors_are_readable():
    r = upload_mit_lv("preise.csv", CSV, "lv.d83", _d83())
    assert r.status_code == 422 and "only applies to GAEB" in r.json()["detail"]
    r = upload_mit_lv("angebot.d84", _d84_angebot(), "lv.pdf", b"%PDF")
    assert r.status_code == 422 and "must be a GAEB file" in r.json()["detail"]
    r = upload_mit_lv("angebot.d84", _d84_angebot(), "lv.d83", b"kaputt")
    assert r.status_code == 422 and "Could not read the matching bill" in r.json()["detail"]
    r = upload_mit_lv("angebot.d84", _d84_angebot(), "lv.d83", b"")
    assert r.status_code == 422


def test_oz_key_ignores_padding():
    assert preis_api._oz_schluessel("01.01.0010") == preis_api._oz_schluessel("1.1.10") == "1.1.10"
