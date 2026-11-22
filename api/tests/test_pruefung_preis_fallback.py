"""t237: fallback prices (index price, then web research) for items without a list/DB match."""
import json

from app import main
from app.ai import llm
from app.modelle import LV, Position, Preisliste, PreislistenEintrag
from app.pruefung import preis_fallback, preise, recherche
from app.pruefung.preis_fallback import ergaenze_indexpreise, ergaenze_recherchepreise, index_preis
from app.pruefung.preise import kalkuliere, kalkuliere_mit_preis_db
from app.pruefung.recherche import Antwort

URL = "https://example.org/marktpreise"
LV15 = LV(name="LV15 synthetisch", quelle="test", positionen=[
    Position(oz="1.1.10", kurztext="Bituminöser Schutzanstrich", menge=181, einheit="m²"),
    Position(oz="1.1.20", kurztext="Aussenwanddämmung 14cm, einbauen", menge=181, einheit="m²"),
])
LISTE = Preisliste(id="liste", eintraege=[PreislistenEintrag(id="x", kurztext="Mutterboden andecken", einheit="m²", ep=5)])


def _mit_db(monkeypatch, liste=None):
    monkeypatch.setattr(preise, "preis_service", lambda: liste or Preisliste(id="preis-db", eintraege=[]))


def test_index_fallback_prices_lv15_and_marks_estimates(monkeypatch):
    _mit_db(monkeypatch)
    k = kalkuliere_mit_preis_db(LV15, LISTE)
    a, b = k.positionen
    assert [a.treffer, b.treffer] == ["index", "index"] and a.geschaetzt and b.geschaetzt
    # bitumen: 8–18 €/m² (2021) × Abdichtungsarbeiten 132.8 → 10.62–23.90, midpoint 17.26
    assert (a.ep_von, a.ep_bis, a.ep) == (10.62, 23.9, 17.26) and a.gp == round(17.26 * 181, 2)
    assert "Abdichtungsarbeiten" in a.preis_quellen[0].titel and a.preis_quellen[0].url.startswith("https://")
    assert "kein amtlicher Wert" in a.preis_quellen[1].titel
    assert "Wärmedämm" in b.preis_quellen[0].titel
    assert k.enthaelt_schaetzungen and k.geschaetzt_anzahl == 2 and k.ohne_preis == 0 and k.vollstaendig
    assert k.summe_netto == round(a.gp + b.gp, 2)


def test_list_and_db_prices_win_over_index(monkeypatch):
    _mit_db(monkeypatch, Preisliste(id="preis-db", eintraege=[
        PreislistenEintrag(id="d1", kurztext="Bituminöser Schutzanstrich", einheit="m²", ep=12.0)]))
    k = kalkuliere_mit_preis_db(LV15, LISTE)
    assert k.positionen[0].treffer == "text" and k.positionen[0].ep == 12.0 and not k.positionen[0].geschaetzt
    assert k.positionen[1].treffer == "index" and k.geschaetzt_anzahl == 1
    dump = k.positionen[0].model_dump()
    assert "geschaetzt" not in dump and "preis_quellen" not in dump  # unchanged payload for real prices


def test_no_raw_material_or_unit_stays_without_index_price():
    assert index_preis("Baustelleneinrichtung vorhalten", "psch") is None
    assert index_preis("Bituminöser Schutzanstrich", None) is None
    assert index_preis("Bituminöser Schutzanstrich", "St") is None  # unit mismatch never matches
    assert index_preis("Betonstahl BSt 500 liefern und verlegen", "t")["ep_von"] > 1000


def test_index_failure_becomes_warning(monkeypatch):
    k = kalkuliere(LV15, LISTE)
    monkeypatch.setattr(preis_fallback, "index_preis", lambda *a: 1 / 0)
    neu = ergaenze_indexpreise(k)
    assert neu.positionen == k.positionen and "Index price fallback failed" in neu.warnungen[-1]


class Stub:
    def __init__(self, gesehen=(URL,)):
        self.gesehen, self.calls = gesehen, []

    def __call__(self, prompt, *, system, max_uses, max_tokens, timeout):
        self.calls.append(prompt)
        eingabe = json.loads(prompt.split("Input:\n", 1)[1])
        out = [{"oz": e["oz"], "einschaetzung": "unklar", "text": "Range from a price survey.", "quellen": [URL],
                "marktpreis_von": 40, "marktpreis_bis": 61} for e in eingabe]
        return Antwort(json.dumps({"ergebnisse": out}), {u: "Price survey" for u in self.gesehen}, 1)


LV_OHNE = LV(name="ohne Rohstoff", quelle="test", positionen=[
    Position(oz="2.1", kurztext="Baustelleneinrichtung vorhalten", menge=3, einheit="Wo"),
    Position(oz="2.2", kurztext="Bituminöser Schutzanstrich", menge=10, einheit="m²"),
])


def test_research_fills_items_without_index_price():
    k = ergaenze_indexpreise(kalkuliere(LV_OHNE, LISTE))
    stub = Stub()
    neu = ergaenze_recherchepreise(k, LV_OHNE, aufruf=stub)
    a, b = neu.positionen
    assert len(stub.calls) == 1 and "2.2" not in stub.calls[0]  # index item is not researched again
    assert a.treffer == "recherche" and a.geschaetzt and (a.ep_von, a.ep_bis, a.ep) == (40, 61, 50.5)
    assert a.preis_quellen[0].url == URL and a.gp == 151.5
    assert b.treffer == "index" and neu.geschaetzt_anzahl == 2 and neu.ohne_preis == 0


def test_research_without_seen_source_is_dropped():
    k = kalkuliere(LV_OHNE, LISTE)
    neu = ergaenze_recherchepreise(k, LV_OHNE, aufruf=Stub(gesehen=()))
    assert neu.positionen[0].treffer == "kein_treffer" and neu.positionen[0].ep is None


def test_research_error_becomes_warning():
    def kaputt(*a, **k):
        raise llm.LLMError("anthropic is unreachable.")
    k = kalkuliere(LV_OHNE, LISTE)
    neu = ergaenze_recherchepreise(k, LV_OHNE, aufruf=kaputt)
    assert neu.positionen[0].ep is None and any("unreachable" in w for w in neu.warnungen)


def test_mock_is_deterministic_and_skips_research(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    k = kalkuliere(LV_OHNE, LISTE)
    assert ergaenze_recherchepreise(k, LV_OHNE) == k
    _mit_db(monkeypatch)
    eins = main.analyse(main.AnalyseAnfrage(lv=LV15, preisliste=LISTE)).kalkulation
    zwei = main.analyse(main.AnalyseAnfrage(lv=LV15, preisliste=LISTE)).kalkulation
    assert eins == zwei and eins.enthaelt_schaetzungen and eins.summe_netto > 0


def test_deep_research_treats_estimates_like_no_match():
    lv = LV(name="x", quelle="t", positionen=[Position(oz="1", kurztext="Bituminöser Schutzanstrich", menge=10,
                                                        einheit="m²", ep=17.0)])
    k = ergaenze_indexpreise(kalkuliere(lv, LISTE))
    from app.modelle import Kennzahlen, Pruefbericht
    b = Pruefbericht(lv=lv, findings=[], kennzahlen=Kennzahlen(positionen=1, findings=0, kritisch=0, modell_mock=True),
                     kalkulation=k)
    gruppen = recherche.gruppen_preise(b, 8)
    assert gruppen and gruppen[0].eingabe[0]["ep_preisquelle"] is None
