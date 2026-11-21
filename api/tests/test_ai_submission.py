import io
import zipfile

from fastapi.testclient import TestClient

from app.ai import submission
from app.main import app

client = TestClient(app)


def test_table_and_lines():
    assert submission.regeln("Rang;Bieter;Angebotssumme brutto\n1;Muster Bau GmbH;1.234.567,89\n2;\"Nord AG\";1.300.000,00") == [
        {"firma": "Muster Bau GmbH", "summe": 1234567.89}, {"firma": "Nord AG", "summe": 1300000.0}]
    text = "Niederschrift Kita Nord\n1. Muster Bau GmbH, Musterstadt   1.234.567,89 €\n2) Süd Hochbau KG – 1 310 000,00 EUR\nSumme 2.544.567,89"
    assert [b["firma"] for b in submission.regeln(text)] == ["Muster Bau GmbH, Musterstadt", "Süd Hochbau KG"]


def test_model_amounts_must_be_in_the_text(monkeypatch):
    class A:
        text = '{"bidders": [{"company": "Real GmbH", "total": 1250000}, {"company": "Made Up AG", "total": 999999}]}'
    monkeypatch.setattr(submission.llm, "complete", lambda *a, **k: A())
    assert submission.mit_modell("Real GmbH bietet 1.250.000,00 EUR") == [{"firma": "Real GmbH", "summe": 1250000.0}]


def test_offline_route_uses_rules_and_says_so(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    r = client.post("/api/submission/lesen", files={"datei": ("s.csv", "Bieter;Summe\nA GmbH;1.000.000\nB AG;1.100.000".encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["methode"] == "regeln" and len(r.json()["bieter"]) == 2
    r = client.post("/api/submission/lesen", files={"datei": ("s.txt", b"nothing here", "text/plain")})
    assert r.json()["bieter"] == [] and "model key" in r.json()["hinweis"]


def test_xlsx_first_sheet():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Bieter</t></si><si><t>Summe</t></si><si><t>Ost Bau</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row><row><c t="s"><v>2</v></c><c><v>1234567.5</v></c></row></sheetData></worksheet>')
    assert submission.lesen("s.xlsx", buf.getvalue())["bieter"] == [{"firma": "Ost Bau", "summe": 1234567.5}]
