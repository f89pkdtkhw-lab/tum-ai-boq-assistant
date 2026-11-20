"""Ausschließlich Offline-Mock; importiert und verwendet keinen Modellanbieter."""
from ..modelle import Finding, LV


def pruefe_mit_llm(lv: LV) -> list[Finding]:
    if not lv.positionen:
        return []
    return [Finding(
        id="mock-modell-1", oz=lv.positionen[0].oz, kategorie="risiko", schwere="niedrig",
        titel="Mock-Beispiel – keine fachliche Prüfung",
        begruendung="Offline-Mock zur Demonstration des Berichtsvertrags. Kein tatsächlicher Befund und keine Modellanfrage.",
        vorschlag="Feste Prüfregeln implementieren und fachlich prüfen; Mock nicht als Treffer zählen.",
        quelle="modell", regel_id="MOCK_LLM", euro_wirkung=None,
    )]
