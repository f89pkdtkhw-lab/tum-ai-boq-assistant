"""Local document vault (t243/t247/t248): upload, list, download, rename/tag, delete, dedupe and auto-filing."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)
ROOT = Path(__file__).resolve().parents[2]


def _hoch(name="lv.json", inhalt=b'{"a": 1}', typ="lv", **kopf):
    return client.post("/api/vault", files={"datei": (name, inhalt)}, data={"typ": typ, "tags": "demo, rohbau"}, headers=kopf)


def test_upload_list_download_delete(vault_tmp):
    antwort = _hoch(**{"X-LV-Scout-User": "Sparsh@Example.com"})
    assert antwort.status_code == 201
    e = antwort.json()
    assert e["typ"] == "lv" and e["dateiname"] == "lv.json" and e["groesse"] == 8
    assert e["tags"] == ["demo", "rohbau"] and e["besitzer"] == "sparsh@example.com"
    assert (vault_tmp / "index.json").exists()
    assert [x["id"] for x in client.get("/api/vault?typ=lv").json()] == [e["id"]]
    assert client.get("/api/vault?typ=regelwerk").json() == []
    datei = client.get(f"/api/vault/{e['id']}/datei")
    assert datei.status_code == 200 and datei.content == b'{"a": 1}'
    assert client.delete(f"/api/vault/{e['id']}").status_code == 204
    assert client.get("/api/vault").json() == []
    assert client.get(f"/api/vault/{e['id']}/datei").status_code == 404
    assert list((vault_tmp / "dateien").iterdir()) == []


def test_dedupe_per_type():
    a = _hoch().json()
    b = _hoch(name="anderer-name.json").json()
    assert a["id"] == b["id"]
    c = _hoch(typ="preisliste").json()  # same bytes, other type: own entry
    assert c["id"] != a["id"]
    assert len(client.get("/api/vault").json()) == 2


def test_rename_and_tag_keep_file():
    e = _hoch(name="alt.x83", inhalt=b"<GAEB/>").json()
    neu = client.patch(f"/api/vault/{e['id']}", json={"dateiname": "neu.x83", "tags": ["a"], "projekt": "Schule"}).json()
    assert neu["dateiname"] == "neu.x83" and neu["tags"] == ["a"] and neu["projekt"] == "Schule"
    assert client.get(f"/api/vault/{e['id']}/datei").content == b"<GAEB/>"


def test_rejects_empty_unknown_type_and_bad_owner():
    assert _hoch(inhalt=b"").status_code == 422
    assert _hoch(typ="geheim").status_code == 422
    assert _hoch(**{"X-LV-Scout-User": "kein-mail"}).json()["besitzer"] is None
    assert client.delete("/api/vault/unbekannt").status_code == 404


def test_lv_import_files_bill_once():
    inhalt = (ROOT / "data" / "beispiel_lv.json").read_bytes()
    for _ in range(2):
        assert client.post("/api/lv/import", files={"datei": ("beispiel_lv.json", inhalt)}).status_code == 200
    lvs = client.get("/api/vault?typ=lv").json()
    assert len(lvs) == 1 and lvs[0]["quelle"] == "analyse" and lvs[0]["lv_schluessel"]


def test_every_analysis_is_a_new_report_version():
    lv = json.loads((ROOT / "data" / "beispiel_lv.json").read_text("utf-8"))
    for _ in range(2):
        assert client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": None}).status_code == 200
    berichte = client.get("/api/vault?typ=bericht").json()
    assert len(berichte) == 2  # no dedupe and no cache for results
    assert sorted(b["version"] for b in berichte) == [1, 2]
    imp = client.post("/api/lv/import", files={"datei": ("beispiel_lv.json", (ROOT / "data" / "beispiel_lv.json").read_bytes())}).json()
    schluessel = client.get("/api/vault?typ=lv").json()[0]["lv_schluessel"]
    assert imp["name"] and len(client.get(f"/api/vault?typ=bericht&lv={schluessel}").json()) == 2
    roh = json.loads(client.get(f"/api/vault/{berichte[0]['id']}/datei").content)
    assert roh["lv"]["name"] == lv["name"]


def test_ai_evaluation_is_archived_each_time():
    evidence = {"name": "LV15", "items": 2, "score": 65, "traffic_light": "gelb", "serious_items": 0, "findings_by_rule": {},
                "change_order_findings": 1, "price_outliers": [], "unusual_prices": 0, "trades": [], "past_overrun_share": None, "language": "de"}
    for _ in range(2):
        assert client.post("/api/lv/ai-evaluation", json=evidence).status_code == 200
    eintraege = client.get("/api/vault?typ=auswertung").json()
    assert len(eintraege) == 2 and all(e["lv_name"] == "LV15" for e in eintraege)


def test_wettbewerb_manual_upload_is_deduped_ki_versions_are_not():
    a = _hoch(name="a.xlsx", inhalt=b"xlsx-bytes", typ="wettbewerb").json()
    b = _hoch(name="b.xlsx", inhalt=b"xlsx-bytes", typ="wettbewerb").json()
    assert a["id"] == b["id"]
    from app import vault
    erste, neu1 = vault.speichere(b"xlsx-bytes", "ki-1.xlsx", "wettbewerb", quelle="ki", projekt="angebot.pdf")
    zweite, neu2 = vault.speichere(b"xlsx-bytes", "ki-2.xlsx", "wettbewerb", quelle="ki", projekt="angebot.pdf")
    assert neu1 and neu2 and erste.id != zweite.id
    assert erste.version == 1 and zweite.version == 2
    assert len(client.get("/api/vault?typ=wettbewerb").json()) == 3  # one manual + two KI versions
