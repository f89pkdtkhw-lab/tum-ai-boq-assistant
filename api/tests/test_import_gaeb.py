"""GAEB acceptance through the public import and HTTP boundaries."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.lv.importer import importiere
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures/gaeb"


def test_synthetic_offer_preserves_original_values_and_readable_text():
    raw = (FIXTURES / "offer.x84").read_bytes()
    lv = importiere("offer.x84", raw)
    p, = lv.positionen
    assert (p.oz, p.menge, p.einheit, p.ep, p.gp) == ("01.0010A", 2, "m²", 12.5, 25)
    assert p.kurztext == "Überbau"
    assert p.langtext == "First wall.\nSecond\nline."
    assert p.titel_pfad == ["01 Walls"]
    assert lv.summen == {"01 Walls": 25}
    client = TestClient(app)
    result = client.post("/api/lv/import", files={"datei": ("offer.x84", raw)})
    assert result.status_code == 200
    report = client.post("/api/lv/pruefen", json=result.json())
    assert report.status_code == 200
    assert report.json()["lv"] == result.json()


def test_partner_xml_acceptance_in_place():
    dataset = Path(__file__).resolve().parents[2] / "data/datensatz"
    expected = {"501-24-01_GAEB-XML_sas.x83": 296, "[NUMMER_001]_leer.X83": 248,
                "8209.003_Leistungsverzeichnis_leer.X83": 159, "GAEB-[PROJEKT_004].X83": 50}
    client = TestClient(app)
    for name, count in expected.items():
        raw = (dataset / name).read_bytes()
        result = client.post("/api/lv/import", files={"datei": (name, raw)})
        assert result.status_code == 200
        lv = result.json()
        assert len(lv["positionen"]) == count
        assert all(p["ep"] is None and p["gp"] is None for p in lv["positionen"])
        assert all(p["oz"] and p["titel_pfad"] and p["kurztext"] and p["langtext"] for p in lv["positionen"])
        report = client.post("/api/lv/pruefen", json=lv)
        assert report.status_code == 200
        # Do not expose partner fields in failing assertion diffs.
        assert report.json()["lv"] == lv, "Review must preserve imported LV"


def test_duplicate_oz_missing_and_zero_values_are_not_repaired():
    xml = b'<GAEB><Award><DP>83</DP><BoQ><BoQBody><Itemlist><Item RNoPart="7"><Qty>0</Qty></Item><Item RNoPart="7"/></Itemlist></BoQBody></BoQ></Award></GAEB>'
    lv = importiere("empty.x83", xml)
    assert [p.oz for p in lv.positionen] == ["7", "7"]
    assert [p.menge for p in lv.positionen] == [0, None]
    assert all(p.ep is None and p.gp is None and p.einheit is None for p in lv.positionen)


def test_invalid_xml_and_numbers_return_safe_http_errors():
    import pytest
    bad = [b"secret-document-text", b"<wrong/>", b"<GAEB/>",
           b'<!DOCTYPE GAEB [<!ENTITY x "secret-document-text">]><GAEB>&x;</GAEB>']
    raw = (FIXTURES / "offer.x84").read_bytes()
    bad += [raw.replace(b"2.000", value) for value in (b"NaN", b"Infinity", b"bad")]
    for content in bad:
        with pytest.raises(ValueError) as error:
            importiere("broken.x83", content)
        assert "secret-document-text" not in str(error.value)
        result = TestClient(app).post("/api/lv/import", files={"datei": ("broken.x83", content)})
        assert result.status_code == 422
        assert "secret-document-text" not in result.text
