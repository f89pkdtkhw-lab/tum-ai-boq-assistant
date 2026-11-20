"""Offline mock only; does not import or use a model provider."""
from ..modelle import Finding, LV


def pruefe_mit_llm(lv: LV) -> list[Finding]:
    if not lv.positionen:
        return []
    return [Finding(
        id="mock-modell-1", oz=lv.positionen[0].oz, kategorie="risiko", schwere="niedrig",
        titel="Mock example – no domain review",
        begruendung="Offline mock demonstrating the report contract. No actual finding or model request.",
        vorschlag="Implement and validate fixed review rules; do not count the mock as a finding.",
        quelle="modell", regel_id="MOCK_LLM", euro_wirkung=None,
    )]
