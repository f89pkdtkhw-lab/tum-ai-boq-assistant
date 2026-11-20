"""Platzhaltervertrag; beim Format-Issue durch echte Import-Abnahmen ergänzen."""
import pytest
from app.lv.importer import importiere


def test_gaeb_placeholder_is_explicit_instead_of_fabricating_positions():
    with pytest.raises(NotImplementedError, match="noch nicht implementiert"):
        importiere("beispiel.x83", b"not-a-real-file")
