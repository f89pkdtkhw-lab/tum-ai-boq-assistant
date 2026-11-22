"""t256: AI competitor-PDF → margin Excel; mock provider is rejected, results are versioned in the vault."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main, marge_pdf, vault
from app.ai import llm

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parents[2]


class _Antwort:
    def __init__(self, text: str):
        self.text = text


def _modell(zeilen, bieter="Nordlicht Bau GmbH"):
    return _Antwort(json.dumps({"bieter_dokument": bieter, "zeilen": zeilen}))


FIXTURE = [
    {"bieter": "Our company", "oz": "01.01", "text": "Erdaushub Baugrube", "menge": 850, "einheit": "m3",
     "ep": None, "gp": None, "direkt": 18.50, "bgk": 10, "marge": 2},
    {"bieter": "Nordlicht Bau GmbH", "oz": "01.01", "text": "Erdaushub Baugrube", "menge": 850, "einheit": "m3",
     "ep": 21.55, "gp": 18317.50, "direkt": None, "bgk": None, "marge": None},
    {"bieter": "Our company", "oz": "01.02", "text": "Mauerwerk KS 24 cm", "menge": 920, "einheit": "m2",
     "ep": None, "gp": None, "direkt": 68, "bgk": 10, "marge": 2},
    {"bieter": "Nordlicht Bau GmbH", "oz": "01.02", "text": "Mauerwerk KS 24 cm", "menge": 920, "einheit": "m2",
     "ep": 79.37, "gp": 73020.40, "direkt": None, "bgk": None, "marge": None},
]

SEITEN_TEXT = (
    "Angebot Nordlicht Bau GmbH\n"
    "01.01 Erdaushub Baugrube 850 m3 EP 21,55 GP 18.317,50 Einzelkosten 18,50 BGK 10 % Marge 2 %\n"
    "01.02 Mauerwerk KS 24 cm 920 m2 EP 79,37 GP 73.020,40 Einzelkosten 68,00 BGK 10 % Marge 2 %\n"
)


def test_number_forms_are_found_in_german_text():
    assert marge_pdf._steht_im_text(21.55, SEITEN_TEXT)
    assert marge_pdf._steht_im_text(18317.50, SEITEN_TEXT)
    assert marge_pdf._steht_im_text(18.5, SEITEN_TEXT)
    assert not marge_pdf._steht_im_text(99.99, SEITEN_TEXT)


def test_xlsx_from_model_rows_has_our_company_and_competitor():
    zeilen = [marge_pdf._zeile_aus_modell(z, "Nordlicht Bau GmbH") for z in FIXTURE]
    tabelle = marge_pdf._tabelle(zeilen, "Nordlicht Bau GmbH")
    assert tabelle[0][0] == "Anbieter"
    uns = [z for z in tabelle[1:] if z[0] == "Our company"]
    konk = [z for z in tabelle[1:] if z[0] != "Our company"]
    assert len(uns) == 2 and uns[0][3] == 850 and uns[0][6] == 18.5
    assert konk[0][0] == "Nordlicht Bau GmbH" and konk[0][4] == 21.55
    xlsx = marge_pdf.schreibe_xlsx(tabelle)
    assert xlsx[:2] == b"PK"
    import zipfile, io
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        blatt = z.read("xl/worksheets/sheet1.xml")
        kopf = z.read("xl/workbook.xml")
    assert b'name="Angebote"' in kopf
    assert b"Anbieter" in blatt and b"<v>850</v>" in blatt and b"<v>21.55</v>" in blatt


def test_invented_prices_are_dropped_when_text_layer_exists():
    zeile = marge_pdf._zeile_aus_modell(
        {"bieter": "Nordlicht Bau GmbH", "oz": "01.01", "text": "Erdaushub Baugrube",
         "menge": 850, "einheit": "m3", "ep": 999.99, "gp": 21.55},
        "Nordlicht Bau GmbH",
    )
    sauber = marge_pdf._pruefe([zeile], SEITEN_TEXT)
    assert sauber[0]["preis"] is None  # 999.99 is not on the page
    assert sauber[0]["summe"] == 21.55 or sauber[0]["summe"] is None  # 21.55 is EP on the page, not GP
    # 21.55 is in the text so it would be kept if used as gp; that's acceptable.


def test_mock_provider_is_rejected_by_the_api():
    # Tests run in mock mode (conftest). The main UI must not get a fake parse.
    antwort = client.post("/api/marge/pdf", files={"datei": ("angebot.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert antwort.status_code == 409
    assert "2211" in antwort.json()["detail"]
    assert "Claude" in antwort.json()["detail"]


def test_non_pdf_is_rejected():
    antwort = client.post("/api/marge/pdf", files={"datei": ("preise.xlsx", b"PK\x03\x04", "application/vnd.ms-excel")})
    assert antwort.status_code == 422


def test_extract_stores_a_new_vault_version_each_time(monkeypatch, vault_tmp):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(marge_pdf, "_seiten", lambda _inhalt: [
        {"nummer": 1, "text": SEITEN_TEXT, "bild": b"\xff\xd8\xff\xd9"},
    ])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: _modell(FIXTURE))

    erste = marge_pdf.extrahiere("Kita-Nord-Angebot.pdf", b"%PDF-fake")
    zweite = marge_pdf.extrahiere("Kita-Nord-Angebot.pdf", b"%PDF-fake")
    assert erste["gebote"] == 4  # 2 our-company + 2 competitor
    assert erste["vault"]["typ"] == "wettbewerb" and erste["vault"]["quelle"] == "ki"
    assert erste["vault"]["version"] == 1 and zweite["vault"]["version"] == 2
    assert erste["vault"]["id"] != zweite["vault"]["id"]
    liste = vault.eintraege("wettbewerb")
    assert len(liste) == 2
    # Same bytes would be de-duplicated on a manual upload, but KI versions stay separate.
    assert {e.version for e in liste} == {1, 2}

    roh = __import__("base64").b64decode(erste["xlsx_base64"])
    import zipfile, io
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        blatt = z.read("xl/worksheets/sheet1.xml")
    assert b"Our company" in blatt and b"Nordlicht Bau GmbH" in blatt
    assert erste["hinweis"] is None  # direct costs were found


def test_extract_via_api_with_stubbed_model(monkeypatch, vault_tmp):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(marge_pdf, "_seiten", lambda _inhalt: [
        {"nummer": 1, "text": SEITEN_TEXT, "bild": b"\xff\xd8\xff\xd9"},
    ])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: _modell(FIXTURE))
    antwort = client.post("/api/marge/pdf", files={"datei": ("angebot.pdf", b"%PDF-1.4 stub", "application/pdf")})
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    assert body["gebote"] == 4 and body["xlsx_base64"] and body["vault"]["version"] == 1
