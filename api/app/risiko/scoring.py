"""Placeholder: preserves existing findings; does not invent scores or prices."""
from ..modelle import Finding, LV


def bewerte(lv: LV, findings: list[Finding]) -> list[Finding]:
    return list(findings)
