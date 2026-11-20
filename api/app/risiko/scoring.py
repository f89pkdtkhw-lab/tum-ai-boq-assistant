"""Platzhalter: erhält vorhandene Findings; erfindet keine Scores oder Preise."""
from ..modelle import Finding, LV


def bewerte(lv: LV, findings: list[Finding]) -> list[Finding]:
    return list(findings)
